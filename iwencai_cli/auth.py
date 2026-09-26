from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import (
    DEFAULT_AUTH_DIR,
    DEFAULT_AUTH_METADATA_FILE,
    DEFAULT_PROFILE_DIR,
    DEFAULT_STORAGE_STATE_FILE,
    ENV_AUTH_DIR,
)

IWENCAI_HOME_URL = "https://www.iwencai.com/"
LOGIN_CHECK_URL = (
    "https://www.iwencai.com/screener/result"
    "?w=%E4%B8%8A%E8%AF%8150&querytype=stock"
)
DEFAULT_LOGIN_TIMEOUT = 10 * 60
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)
AUTOMATION_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
]
IGNORE_DEFAULT_ARGS = ["--enable-automation"]
INIT_SCRIPT = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    "window.chrome = window.chrome || { runtime: {} };"
)


@dataclass(frozen=True)
class AuthPaths:
    auth_dir: Path
    browser_profile_dir: Path
    storage_state_file: Path
    metadata_file: Path


def resolve_auth_paths(
    auth_dir: Optional[str] = None,
    profile_dir: Optional[str] = None,
) -> AuthPaths:
    if not auth_dir and not profile_dir:
        return AuthPaths(
            auth_dir=DEFAULT_AUTH_DIR,
            browser_profile_dir=DEFAULT_PROFILE_DIR,
            storage_state_file=DEFAULT_STORAGE_STATE_FILE,
            metadata_file=DEFAULT_AUTH_METADATA_FILE,
        )

    base_dir = Path(auth_dir).expanduser() if auth_dir else DEFAULT_AUTH_DIR
    browser_profile_dir = (
        Path(profile_dir).expanduser()
        if profile_dir
        else base_dir / "browser-profile"
    )
    return AuthPaths(
        auth_dir=base_dir,
        browser_profile_dir=browser_profile_dir,
        storage_state_file=base_dir / "storage-state.json",
        metadata_file=base_dir / "metadata.json",
    )


def launch_persistent_context(
    browser_type: Any,
    paths: AuthPaths,
    *,
    headless: bool,
) -> Any:
    paths.auth_dir.mkdir(parents=True, exist_ok=True)
    paths.browser_profile_dir.mkdir(parents=True, exist_ok=True)
    launch_kwargs = {
        "user_data_dir": str(paths.browser_profile_dir),
        "headless": headless,
        "viewport": {"width": 1400, "height": 900},
        "user_agent": USER_AGENT,
        "args": AUTOMATION_ARGS,
        "ignore_default_args": IGNORE_DEFAULT_ARGS,
    }
    try:
        context = browser_type.launch_persistent_context(
            channel="chrome",
            **launch_kwargs,
        )
    except Exception:
        context = browser_type.launch_persistent_context(**launch_kwargs)
    context.add_init_script(INIT_SCRIPT)
    if paths.storage_state_file.exists():
        _load_storage_state(context, paths.storage_state_file)
    return context


def has_saved_auth(
    auth_dir: Optional[str] = None,
    profile_dir: Optional[str] = None,
) -> bool:
    paths = resolve_auth_paths(auth_dir, profile_dir)
    return (
        paths.storage_state_file.exists()
        or (paths.browser_profile_dir / "Default" / "Network" / "Cookies").exists()
        or (paths.browser_profile_dir / "Default" / "Cookies").exists()
        or (paths.browser_profile_dir / "Cookies").exists()
    )


def get_auth_status(
    playwright: Any,
    *,
    auth_dir: Optional[str] = None,
    profile_dir: Optional[str] = None,
) -> dict[str, Any]:
    paths = resolve_auth_paths(auth_dir, profile_dir)
    saved = has_saved_auth(auth_dir, profile_dir)
    authenticated = saved and _is_auth_valid(playwright, paths)
    return {
        "authenticated": authenticated,
        "has_saved_auth": saved,
        "auth_dir": str(paths.auth_dir),
        "browser_profile_dir": str(paths.browser_profile_dir),
        "storage_state_file": str(paths.storage_state_file),
        "metadata_file": str(paths.metadata_file),
    }


def ensure_login(
    playwright: Any,
    *,
    auth_dir: Optional[str] = None,
    profile_dir: Optional[str] = None,
    login_timeout: int = DEFAULT_LOGIN_TIMEOUT,
) -> AuthPaths:
    paths = resolve_auth_paths(auth_dir, profile_dir)
    if has_saved_auth(auth_dir, profile_dir):
        if _is_auth_valid(playwright, paths):
            return paths
        print("检测到问财登录态已失效，需要重新登录。", file=sys.stderr)

    login(
        playwright,
        auth_dir=auth_dir,
        profile_dir=profile_dir,
        timeout=login_timeout,
    )
    return paths


def login(
    playwright: Any,
    *,
    auth_dir: Optional[str] = None,
    profile_dir: Optional[str] = None,
    timeout: int = DEFAULT_LOGIN_TIMEOUT,
) -> AuthPaths:
    paths = resolve_auth_paths(auth_dir, profile_dir)
    paths.auth_dir.mkdir(parents=True, exist_ok=True)
    print("正在打开问财，请在浏览器中完成扫码或短信登录。", file=sys.stderr)
    print(f"登录态目录：{paths.auth_dir}", file=sys.stderr)

    context = launch_persistent_context(
        playwright.chromium,
        paths,
        headless=False,
    )
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_CHECK_URL, wait_until="load", timeout=30000)
        _wait_for_login(page, timeout)
        save_auth_state(context, paths)
        print("问财登录态已保存。", file=sys.stderr)
    except Exception as exc:
        if type(exc).__name__ == "TargetClosedError":
            raise RuntimeError("登录窗口已关闭，未保存问财登录态") from exc
        raise
    finally:
        try:
            context.close()
        except Exception:
            pass
    return paths


def logout(
    auth_dir: Optional[str] = None,
    profile_dir: Optional[str] = None,
) -> AuthPaths:
    paths = resolve_auth_paths(auth_dir, profile_dir)
    for file_path in (paths.storage_state_file, paths.metadata_file):
        if file_path.exists():
            file_path.unlink()
    if paths.browser_profile_dir.exists():
        shutil.rmtree(paths.browser_profile_dir)
    return paths


def save_auth_state(context: Any, paths: AuthPaths) -> None:
    paths.auth_dir.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(paths.storage_state_file))
    metadata = {
        "saved_at": int(time.time()),
        "browser_profile_dir": str(paths.browser_profile_dir),
        "storage_state_file": str(paths.storage_state_file),
        "user_agent": USER_AGENT,
        "env_override": ENV_AUTH_DIR,
    }
    paths.metadata_file.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def login_required(page: Any) -> bool:
    try:
        if _is_visible(page.locator('iframe[title*="问财登录"]')):
            return True
        if _is_visible(page.locator('iframe[src*="login"]')):
            return True
        if any("login" in frame.url.lower() for frame in page.frames):
            return True
        body = page.inner_text("body", timeout=3000)
    except Exception:
        return False

    markers = (
        "短信登录",
        "密码登录",
        "请输入手机号",
        "请输入短信验证码",
        "获取验证码",
    )
    return any(marker in body for marker in markers)


def _is_auth_valid(playwright: Any, paths: AuthPaths) -> bool:
    context = launch_persistent_context(
        playwright.chromium,
        paths,
        headless=True,
    )
    try:
        page = context.new_page()
        page.goto(LOGIN_CHECK_URL, wait_until="load", timeout=30000)
        page.wait_for_timeout(3000)
        if login_required(page):
            return False
        save_auth_state(context, paths)
        return True
    except Exception:
        return False
    finally:
        try:
            context.close()
        except Exception:
            pass


def _wait_for_login(page: Any, timeout: int) -> None:
    deadline = time.time() + timeout
    page.wait_for_timeout(2500)
    saw_login = login_required(page)
    if not saw_login:
        return

    while time.time() < deadline:
        page.wait_for_timeout(1500)
        if not login_required(page):
            return
    raise RuntimeError("等待登录超时，请重新运行 --login 完成扫码或短信登录")


def _is_visible(locator: Any) -> bool:
    try:
        return locator.count() > 0 and locator.first.is_visible()
    except Exception:
        return False


def _load_storage_state(context: Any, storage_state_file: Path) -> None:
    try:
        state = json.loads(storage_state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    cookies = state.get("cookies", [])
    if cookies:
        try:
            context.add_cookies(cookies)
        except Exception:
            return

    origins = {
        origin.get("origin"): origin.get("localStorage", [])
        for origin in state.get("origins", [])
        if origin.get("origin")
    }
    if not origins:
        return

    serialized_origins = json.dumps(origins, ensure_ascii=False)
    context.add_init_script(
        f"""
        (() => {{
            const origins = {serialized_origins};
            const entries = origins[window.location.origin];
            if (!entries) return;
            for (const entry of entries) {{
                window.localStorage.setItem(entry.name, entry.value);
            }}
        }})();
        """
    )
