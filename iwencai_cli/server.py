from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager, contextmanager
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, PlainTextResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - only hit when server deps are missing.
    raise RuntimeError("启动服务需要安装 fastapi 和 uvicorn") from exc

from .accounts import (
    AccountUnavailableError,
    AccountNotFoundError,
    AccountStore,
    QuotaExceededError,
)
from .auth import get_auth_status, login, logout
from .query import parse_results, query_iwencai
from .web import ACCOUNT_MANAGER_HTML


@asynccontextmanager
async def lifespan(application: FastAPI):
    await asyncio.to_thread(_prepare_startup, application)
    print(
        "服务启动成功，接口地址："
        f"http://{application.state.host}:{application.state.port}",
        file=sys.stderr,
        flush=True,
    )
    yield


app = FastAPI(
    title="iwencai-py local server",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
    allow_methods=["DELETE", "GET", "PATCH", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prevent_query_response_caching(request: Request, call_next):
    response = await call_next(request)
    if request.method == "POST" and (
        request.url.path == "/api/query"
        or request.url.path.endswith("/test-query")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


_browser_lock = threading.Lock()
_account_store = AccountStore()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DOCS = {
    "local-api": _PROJECT_ROOT / "docs" / "local-api.md",
}
app.state.auth_dir = None
app.state.profile_dir = None
app.state.host = "127.0.0.1"
app.state.port = 8765
app.state.min_query_interval = 5.0
app.state.max_query_queue = 50
TEST_QUERY = "上证50"


class QueryQueueFullError(RuntimeError):
    pass


class QueryActivity:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: Optional[dict[str, Any]] = None

    def begin(self, account_id: str, account_name: str, question: str) -> None:
        with self._lock:
            self._active = {
                "active": True,
                "active_account_id": account_id,
                "active_account_name": account_name,
                "question": question,
                "started_at": time.time(),
                "attempt": 1,
            }

    def switch_account(self, account_id: str, account_name: str) -> None:
        with self._lock:
            if not self._active:
                return
            self._active["active_account_id"] = account_id
            self._active["active_account_name"] = account_name
            self._active["attempt"] = int(self._active["attempt"]) + 1

    def finish(self) -> None:
        with self._lock:
            self._active = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if not self._active:
                return {
                    "active": False,
                    "active_account_id": None,
                    "active_account_name": None,
                    "question": None,
                    "started_at": None,
                    "elapsed_seconds": 0,
                    "attempt": 0,
                }
            snapshot = dict(self._active)
            snapshot["elapsed_seconds"] = round(
                max(0.0, time.time() - float(snapshot["started_at"])),
                1,
            )
            return snapshot


class QueryThrottle:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active = False
        self._waiting = 0
        self._next_allowed_at = 0.0
        self._min_interval = 5.0
        self._max_queue = 50

    def configure(self, *, min_interval: float, max_queue: int) -> None:
        with self._condition:
            self._min_interval = min_interval
            self._max_queue = max_queue
            self._condition.notify_all()

    @contextmanager
    def slot(self):
        with self._condition:
            is_busy = self._active or self._next_allowed_at > time.monotonic()
            if is_busy and self._waiting >= self._max_queue:
                raise QueryQueueFullError("问财查询队列已满，请稍后重试")
            self._waiting += 1
            try:
                while True:
                    if self._active:
                        self._condition.wait()
                        continue
                    wait_seconds = self._next_allowed_at - time.monotonic()
                    if wait_seconds <= 0:
                        break
                    self._condition.wait(timeout=wait_seconds)

                self._waiting -= 1
                self._active = True
            except Exception:
                self._waiting -= 1
                self._condition.notify_all()
                raise

        try:
            yield
        finally:
            with self._condition:
                self._active = False
                self._next_allowed_at = time.monotonic() + self._min_interval
                self._condition.notify_all()


_query_throttle = QueryThrottle()
_query_activity = QueryActivity()


class AuthRequest(BaseModel):
    account_id: Optional[str] = None
    auth_dir: Optional[str] = None
    profile_dir: Optional[str] = None
    login_timeout: int = Field(default=600, ge=1)


class QueryRequest(AuthRequest):
    question: str = Field(min_length=1)
    headless: bool = True
    wait_ms: int = Field(default=4000, ge=0)
    max_pages: Optional[int] = Field(default=None, ge=1)


class AccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    notes: str = Field(default="", max_length=500)
    quota_limit: int = Field(default=100, ge=1)


class AccountUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=500)
    quota_limit: Optional[int] = Field(default=None, ge=1)


class AccountQuotaUpdateRequest(BaseModel):
    remaining: int = Field(ge=0)


def _prepare_startup(application: FastAPI) -> None:
    """服务启动时只加载账号配置，不自动打开浏览器登录窗口。"""
    try:
        account = _account_store.ensure_default(
            auth_dir=application.state.auth_dir,
            profile_dir=application.state.profile_dir,
        )
    except AccountNotFoundError:
        print(
            "尚未添加问财账号，服务即将启动。请打开管理台，点击“添加并登录”完成首次扫码。",
            file=sys.stderr,
        )
        return

    print(
        f"已加载默认账号（{account.name}），服务启动时不会自动打开登录窗口。",
        file=sys.stderr,
    )


@app.get("/", response_class=HTMLResponse)
def account_manager() -> str:
    return ACCOUNT_MANAGER_HTML


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"success": True, "service": "iwencai-py", "status": "ok"}


@app.get("/api/query/status")
def query_status() -> dict[str, Any]:
    return {"success": True, **_query_activity.snapshot()}


@app.get("/api/docs")
def docs_index() -> dict[str, Any]:
    return {
        "success": True,
        "docs": [
            {
                "name": name,
                "format": "markdown",
                "json_url": f"/api/docs/{name}",
                "raw_url": f"/api/docs/{name}.md",
            }
            for name in _DOCS
        ],
    }


@app.get("/api/docs/local-api")
def local_api_doc() -> dict[str, Any]:
    content = _read_doc("local-api")
    return {
        "success": True,
        "name": "local-api",
        "format": "markdown",
        "content": content,
    }


@app.get("/api/docs/local-api.md", response_class=PlainTextResponse)
def local_api_doc_markdown() -> str:
    return _read_doc("local-api")


@app.get("/api/accounts")
def accounts() -> dict[str, Any]:
    return {"success": True, "accounts": _account_store.list_views()}


@app.post("/api/accounts")
def create_account(request: AccountCreateRequest) -> dict[str, Any]:
    try:
        account = _account_store.create(
            request.name,
            notes=request.notes,
            quota_limit=request.quota_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "account": _account_store.get(account.id).__dict__}


@app.patch("/api/accounts/{account_id}")
def update_account(account_id: str, request: AccountUpdateRequest) -> dict[str, Any]:
    try:
        account = _account_store.update(
            account_id,
            name=request.name,
            notes=request.notes,
            quota_limit=request.quota_limit,
        )
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="账号不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "account": account.__dict__}


@app.post("/api/accounts/{account_id}/default")
def set_default_account(account_id: str) -> dict[str, Any]:
    with _browser_lock:
        try:
            account = _account_store.set_default(account_id)
        except AccountNotFoundError as exc:
            raise HTTPException(status_code=404, detail="账号不存在") from exc
    return {"success": True, "account": account.__dict__}


@app.get("/api/accounts/{account_id}/quota")
def account_quota(account_id: str) -> dict[str, Any]:
    try:
        quota = _account_store.get_quota(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="账号不存在") from exc
    return {"success": True, "account_id": account_id, "quota": quota}


@app.patch("/api/accounts/{account_id}/quota")
def update_account_quota(
    account_id: str,
    request: AccountQuotaUpdateRequest,
) -> dict[str, Any]:
    with _browser_lock:
        try:
            quota, default_account, switched = _account_store.set_quota_remaining(
                account_id,
                request.remaining,
            )
        except AccountNotFoundError as exc:
            raise HTTPException(status_code=404, detail="账号不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "account_id": account_id,
        "quota": quota,
        "account_switched": switched,
        "default_account_id": default_account.id,
        "default_account_name": default_account.name,
    }


@app.get("/api/quota")
def default_quota(account_id: Optional[str] = None) -> dict[str, Any]:
    account = _resolve_account(account_id, None, None)
    return {
        "success": True,
        "account_id": account.id,
        "quota": _account_store.get_quota(account.id),
    }


@app.post("/api/accounts/{account_id}/login")
def account_login(account_id: str, request: Optional[AuthRequest] = None) -> dict[str, Any]:
    request = request or AuthRequest()
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Playwright 未安装") from exc

    with _browser_lock:
        account = _get_account_or_404(account_id)
        try:
            with sync_playwright() as playwright:
                paths = login(
                    playwright,
                    auth_dir=account.auth_dir,
                    profile_dir=account.profile_dir,
                    timeout=request.login_timeout,
                )
        except RuntimeError as exc:
            _account_store.mark_auth(account.id, False)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _account_store.mark_auth(account.id, True)
    return {
        "success": True,
        "account_id": account.id,
        "auth_dir": str(paths.auth_dir),
        "storage_state_file": str(paths.storage_state_file),
    }


@app.post("/api/accounts/{account_id}/check")
def check_account(account_id: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Playwright 未安装") from exc

    with _browser_lock:
        account = _get_account_or_404(account_id)
        with sync_playwright() as playwright:
            status = get_auth_status(
                playwright,
                auth_dir=account.auth_dir,
                profile_dir=account.profile_dir,
            )
        _account_store.mark_auth(account.id, bool(status["authenticated"]))
    return {"success": True, "account_id": account.id, **status}


@app.post("/api/accounts/{account_id}/test-query")
def test_account_query(account_id: str) -> dict[str, Any]:
    """Run a small real query to verify the account's iWenCai query path."""
    try:
        with _query_throttle.slot():
            with _browser_lock:
                account = _get_account_or_404(account_id)
                try:
                    account, quota = _account_store.reserve_query_with_fallback(
                        account.id,
                        allow_fallback=False,
                    )
                except QuotaExceededError as exc:
                    raise HTTPException(
                        status_code=429,
                        detail=str(exc),
                        headers={"X-Quota-Reset-At": exc.reset_at},
                    ) from exc
                except AccountUnavailableError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc

                _query_activity.begin(account.id, account.name, TEST_QUERY)
                try:
                    raw = query_iwencai(
                        TEST_QUERY,
                        headless=True,
                        profile_dir=account.profile_dir,
                        auth_dir=account.auth_dir,
                        login_timeout=600,
                        wait_ms=2500,
                        max_pages=1,
                        allow_login=False,
                    )
                except RuntimeError as exc:
                    if _is_login_failure(str(exc)):
                        _account_store.mark_auth(account.id, False)
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                else:
                    _account_store.mark_auth(account.id, True)
                    if raw.get("pages", 0) < 1:
                        raise HTTPException(
                            status_code=409,
                            detail="问财查询页面未返回结果表格",
                        )
                    rows = parse_results(raw)
                    return {
                        "success": True,
                        "account_id": account.id,
                        "account_name": account.name,
                        "question": TEST_QUERY,
                        "count": len(rows),
                        "headers": raw.get("headers", []),
                        "pages": raw.get("pages", 0),
                        "quota": quota,
                    }
                finally:
                    _query_activity.finish()
    except QueryQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(max(1, round(app.state.min_query_interval)))},
        ) from exc


@app.post("/api/accounts/{account_id}/logout")
def logout_account(account_id: str) -> dict[str, Any]:
    with _browser_lock:
        account = _get_account_or_404(account_id)
        paths = logout(
            auth_dir=account.auth_dir,
            profile_dir=account.profile_dir,
        )
        _account_store.mark_auth(account.id, False)
    return {"success": True, "account_id": account.id, "auth_dir": str(paths.auth_dir)}


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str, delete_auth: bool = False) -> dict[str, Any]:
    with _browser_lock:
        try:
            account = _account_store.delete(account_id, delete_auth=delete_auth)
        except AccountNotFoundError as exc:
            raise HTTPException(status_code=404, detail="账号不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "account_id": account.id}


@app.get("/api/auth/status")
def auth_status(
    account_id: Optional[str] = None,
    auth_dir: Optional[str] = None,
    profile_dir: Optional[str] = None,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Playwright 未安装") from exc

    with _browser_lock:
        account = _resolve_account(account_id, auth_dir, profile_dir)
        with sync_playwright() as playwright:
            status = get_auth_status(
                playwright,
                auth_dir=account.auth_dir,
                profile_dir=account.profile_dir,
            )
        _account_store.mark_auth(account.id, bool(status["authenticated"]))
    return {"success": True, "account_id": account.id, **status}


@app.post("/api/auth/login")
def auth_login(request: Optional[AuthRequest] = None) -> dict[str, Any]:
    request = request or AuthRequest()
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Playwright 未安装") from exc

    with _browser_lock:
        account = _resolve_account(request.account_id, request.auth_dir, request.profile_dir)
        try:
            with sync_playwright() as playwright:
                paths = login(
                    playwright,
                    auth_dir=account.auth_dir,
                    profile_dir=account.profile_dir,
                    timeout=request.login_timeout,
                )
        except RuntimeError as exc:
            _account_store.mark_auth(account.id, False)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _account_store.mark_auth(account.id, True)
    return {
        "success": True,
        "account_id": account.id,
        "auth_dir": str(paths.auth_dir),
        "storage_state_file": str(paths.storage_state_file),
    }


@app.post("/api/auth/logout")
def auth_logout(request: Optional[AuthRequest] = None) -> dict[str, Any]:
    request = request or AuthRequest()
    with _browser_lock:
        account = _resolve_account(request.account_id, request.auth_dir, request.profile_dir)
        paths = logout(
            auth_dir=account.auth_dir,
            profile_dir=account.profile_dir,
        )
        _account_store.mark_auth(account.id, False)
    return {"success": True, "account_id": account.id, "auth_dir": str(paths.auth_dir)}


@app.post("/api/query")
def query(request: QueryRequest) -> dict[str, Any]:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")
    preferred_account = None
    account = None
    quota = None
    raw = None

    try:
        with _query_throttle.slot():
            with _browser_lock:
                try:
                    preferred_account = _resolve_account(
                        request.account_id,
                        request.auth_dir,
                        request.profile_dir,
                    )
                    excluded_account_ids: set[str] = set()
                    first_attempt = True
                    while True:
                        try:
                            account, quota = _account_store.reserve_query_with_fallback(
                                preferred_account.id,
                                excluded_account_ids=excluded_account_ids,
                            )
                        except QuotaExceededError as exc:
                            raise HTTPException(
                                status_code=429,
                                detail=str(exc),
                                headers={"X-Quota-Reset-At": exc.reset_at},
                            ) from exc
                        except AccountUnavailableError as exc:
                            raise HTTPException(status_code=409, detail=str(exc)) from exc

                        if first_attempt:
                            _query_activity.begin(account.id, account.name, question)
                            first_attempt = False
                        else:
                            _query_activity.switch_account(account.id, account.name)

                        try:
                            raw = query_iwencai(
                                question,
                                headless=request.headless,
                                profile_dir=account.profile_dir,
                                auth_dir=account.auth_dir,
                                login_timeout=request.login_timeout,
                                wait_ms=request.wait_ms,
                                max_pages=request.max_pages,
                                allow_login=False,
                            )
                        except RuntimeError as exc:
                            if not _is_login_failure(str(exc)):
                                raise HTTPException(status_code=409, detail=str(exc)) from exc
                            _account_store.mark_auth(account.id, False)
                            excluded_account_ids.add(account.id)
                            continue
                        _account_store.mark_auth(account.id, True)
                        break
                finally:
                    _query_activity.finish()
    except QueryQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(max(1, round(app.state.min_query_interval)))},
        ) from exc

    assert preferred_account is not None
    assert account is not None
    assert quota is not None
    assert raw is not None
    rows = parse_results(raw)
    return {
        "success": True,
        "requested_account_id": preferred_account.id,
        "account_switched": account.id != preferred_account.id,
        "account_id": account.id,
        "account_name": account.name,
        "quota": quota,
        "question": question,
        "count": len(rows),
        "headers": raw.get("headers", []),
        "pages": raw.get("pages", 0),
        "rows": rows,
    }


def _read_doc(name: str) -> str:
    doc_path = _DOCS.get(name)
    if not doc_path or not doc_path.exists():
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc_path.read_text(encoding="utf-8")


def _is_login_failure(message: str) -> bool:
    return any(marker in message for marker in ("未登录", "登录态", "登录窗口"))


def _get_account_or_404(account_id: str):
    try:
        return _account_store.get(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="账号不存在") from exc


def _resolve_account(
    account_id: Optional[str],
    auth_dir: Optional[str],
    profile_dir: Optional[str],
):
    if account_id:
        return _get_account_or_404(account_id)

    try:
        return _account_store.ensure_default(
            auth_dir=auth_dir,
            profile_dir=profile_dir,
        )
    except AccountNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail="尚未添加问财账号，请先打开管理台并点击“添加并登录”",
        ) from exc


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="iwencai-server",
        description="iWenCai 本地 HTTP API 服务",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--auth-dir", default=None, help="全局问财登录态目录")
    parser.add_argument("--profile-dir", default=None, help="浏览器 profile 目录")
    parser.add_argument(
        "--min-query-interval",
        type=float,
        default=5.0,
        help="上一次查询完成后到下一次查询开始前的最小间隔秒数（默认 5）",
    )
    parser.add_argument(
        "--max-query-queue",
        type=int,
        default=50,
        help="最多允许等待的问财查询数量（默认 50）",
    )
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("启动服务需要安装 uvicorn") from exc

    app.state.auth_dir = args.auth_dir
    app.state.profile_dir = args.profile_dir
    app.state.host = args.host
    app.state.port = args.port
    if args.min_query_interval < 0:
        parser.error("--min-query-interval 不能小于 0")
    if args.max_query_queue < 0:
        parser.error("--max-query-queue 不能小于 0")
    app.state.min_query_interval = args.min_query_interval
    app.state.max_query_queue = args.max_query_queue
    _query_throttle.configure(
        min_interval=args.min_query_interval,
        max_queue=args.max_query_queue,
    )

    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
