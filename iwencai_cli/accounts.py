from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import DEFAULT_AUTH_DIR
from .auth import has_saved_auth


DEFAULT_QUOTA_LIMIT = 100
BEIJING_TZ = timezone(timedelta(hours=8))
APP_DATA_DIR = DEFAULT_AUTH_DIR.parent
ACCOUNT_ROOT = APP_DATA_DIR / "accounts"
ACCOUNT_REGISTRY_FILE = APP_DATA_DIR / "accounts.json"


class AccountNotFoundError(KeyError):
    pass


class QuotaExceededError(RuntimeError):
    def __init__(self, reset_at: str) -> None:
        super().__init__("所有可用问财账号今日查询额度已用尽，请明日再试")
        self.reset_at = reset_at


class AccountUnavailableError(RuntimeError):
    pass


@dataclass
class AccountRecord:
    id: str
    name: str
    notes: str
    auth_dir: str
    profile_dir: str
    created_at: float
    quota_limit: int = DEFAULT_QUOTA_LIMIT
    last_query_at: Optional[float] = None
    last_auth_check_at: Optional[float] = None
    authenticated: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountRecord":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            notes=str(data.get("notes") or ""),
            auth_dir=str(data["auth_dir"]),
            profile_dir=str(data["profile_dir"]),
            created_at=float(data.get("created_at") or time.time()),
            quota_limit=max(1, int(data.get("quota_limit") or DEFAULT_QUOTA_LIMIT)),
            last_query_at=_optional_float(data.get("last_query_at")),
            last_auth_check_at=_optional_float(data.get("last_auth_check_at")),
            authenticated=_optional_bool(data.get("authenticated")),
        )


class AccountStore:
    def __init__(
        self,
        registry_path: Path = ACCOUNT_REGISTRY_FILE,
        account_root: Path = ACCOUNT_ROOT,
    ) -> None:
        self.registry_path = registry_path
        self.account_root = account_root
        self._lock = threading.RLock()

    def ensure_default(
        self,
        *,
        auth_dir: Optional[str] = None,
        profile_dir: Optional[str] = None,
    ) -> AccountRecord:
        with self._lock:
            accounts, default_id = self._load_unlocked()
            if not accounts:
                raise AccountNotFoundError("default")

            changed = False
            if default_id not in {account.id for account in accounts}:
                default_id = accounts[0].id
                changed = True

            default = next(account for account in accounts if account.id == default_id)
            if auth_dir or profile_dir:
                new_auth_dir = str(Path(auth_dir).expanduser()) if auth_dir else default.auth_dir
                new_profile_dir = (
                    str(Path(profile_dir).expanduser())
                    if profile_dir
                    else str(Path(new_auth_dir) / "browser-profile")
                )
                if default.auth_dir != new_auth_dir or default.profile_dir != new_profile_dir:
                    default.auth_dir = new_auth_dir
                    default.profile_dir = new_profile_dir
                    changed = True

            if changed:
                self._save_unlocked(accounts, default_id)
            return _copy_account(default)

    def list_accounts(self) -> list[AccountRecord]:
        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            self._save_if_needed_unlocked(accounts, default_id)
            return [_copy_account(account) for account in accounts]

    def list_views(self) -> list[dict[str, Any]]:
        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            changed = False
            views = []
            for account in accounts:
                saved = has_saved_auth(account.auth_dir, account.profile_dir)
                if not saved and account.authenticated is not False:
                    account.authenticated = False
                    changed = True
                quota = self._quota_status_unlocked(account)
                views.append(
                    {
                        "id": account.id,
                        "name": account.name,
                        "notes": account.notes,
                        "is_default": account.id == default_id,
                        "authenticated": account.authenticated is True and saved,
                        "has_saved_auth": saved,
                        "auth_state": _auth_state(account.authenticated, saved),
                        "auth_dir": account.auth_dir,
                        "profile_dir": account.profile_dir,
                        "created_at": account.created_at,
                        "last_query_at": account.last_query_at,
                        "last_auth_check_at": account.last_auth_check_at,
                        "quota": quota,
                    }
                )
            if changed:
                self._save_unlocked(accounts, default_id)
            else:
                self._save_if_needed_unlocked(accounts, default_id)
            return views

    def get(self, account_id: Optional[str] = None) -> AccountRecord:
        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            wanted_id = account_id or default_id
            for account in accounts:
                if account.id == wanted_id:
                    self._save_if_needed_unlocked(accounts, default_id)
                    return _copy_account(account)
        raise AccountNotFoundError(wanted_id)

    def create(
        self,
        name: str,
        *,
        notes: str = "",
        quota_limit: int = DEFAULT_QUOTA_LIMIT,
    ) -> AccountRecord:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("账号名称不能为空")
        if len(normalized_name) > 80:
            raise ValueError("账号名称不能超过 80 个字符")
        if quota_limit < 1:
            raise ValueError("quota_limit 必须大于 0")

        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            account_id = f"account-{uuid.uuid4().hex[:12]}"
            auth_dir = self.account_root / account_id
            account = AccountRecord(
                id=account_id,
                name=normalized_name,
                notes=notes.strip(),
                auth_dir=str(auth_dir),
                profile_dir=str(auth_dir / "browser-profile"),
                created_at=time.time(),
                quota_limit=quota_limit,
            )
            accounts.append(account)
            if not default_id:
                default_id = account.id
            self._save_unlocked(accounts, default_id)
            return _copy_account(account)

    def update(
        self,
        account_id: str,
        *,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        quota_limit: Optional[int] = None,
    ) -> AccountRecord:
        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            account = self._find_unlocked(accounts, account_id)
            if name is not None:
                normalized_name = name.strip()
                if not normalized_name:
                    raise ValueError("账号名称不能为空")
                if len(normalized_name) > 80:
                    raise ValueError("账号名称不能超过 80 个字符")
                account.name = normalized_name
            if notes is not None:
                account.notes = notes.strip()
            if quota_limit is not None:
                if quota_limit < 1:
                    raise ValueError("quota_limit 必须大于 0")
                account.quota_limit = quota_limit
            self._save_unlocked(accounts, default_id)
            return _copy_account(account)

    def set_default(self, account_id: str) -> AccountRecord:
        with self._lock:
            accounts, _ = self._load_with_default_unlocked()
            account = self._find_unlocked(accounts, account_id)
            self._save_unlocked(accounts, account.id)
            return _copy_account(account)

    def mark_auth(self, account_id: str, authenticated: bool) -> None:
        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            account = self._find_unlocked(accounts, account_id)
            account.authenticated = authenticated
            account.last_auth_check_at = time.time()
            self._save_unlocked(accounts, default_id)

    def reserve_query(self, account_id: str) -> dict[str, Any]:
        _, quota = self.reserve_query_with_fallback(
            account_id,
            allow_fallback=False,
        )
        return quota

    def reserve_query_with_fallback(
        self,
        preferred_account_id: str,
        *,
        allow_fallback: bool = True,
        excluded_account_ids: Optional[set[str]] = None,
    ) -> tuple[AccountRecord, dict[str, Any]]:
        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            preferred = self._find_unlocked(accounts, preferred_account_id)
            excluded = excluded_account_ids or set()
            candidates = [] if preferred.id in excluded else [preferred]
            if allow_fallback:
                candidates.extend(
                    sorted(
                        (
                            account
                            for account in accounts
                            if account.id != preferred.id and account.id not in excluded
                        ),
                        key=_last_query_sort_key,
                    )
                )

            if not candidates:
                raise AccountUnavailableError(
                    "没有其他已登录的问财账号可用于继续查询，请先登录备用账号"
                )

            reset_at = ""
            has_remaining = False
            for account in candidates:
                quota = self._quota_status_unlocked(account)
                reset_at = reset_at or quota["reset_at"]
                if quota["remaining"] <= 0:
                    continue
                has_remaining = True
                if not _is_query_ready(account):
                    continue

                quota["used"] += 1
                quota["remaining"] = quota["limit"] - quota["used"]
                self._write_quota_unlocked(account, quota)
                account.last_query_at = time.time()
                self._save_unlocked(accounts, default_id)
                return _copy_account(account), quota

            if not has_remaining:
                raise QuotaExceededError(reset_at)
            raise AccountUnavailableError(
                "没有已登录且有剩余次数的问财账号，请先登录备用账号"
            )

    def get_quota(self, account_id: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            account = self._find_unlocked(accounts, account_id or default_id)
            quota = self._quota_status_unlocked(account)
            self._save_if_needed_unlocked(accounts, default_id)
            return quota

    def set_quota_remaining(
        self,
        account_id: str,
        remaining: int,
    ) -> tuple[dict[str, Any], AccountRecord, bool]:
        if remaining < 0:
            raise ValueError("remaining 不能小于 0")

        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            account = self._find_unlocked(accounts, account_id)
            quota = self._quota_status_unlocked(account)
            if remaining > quota["limit"]:
                raise ValueError(f"remaining 不能超过每日额度 {quota['limit']}")
            quota["used"] = quota["limit"] - remaining
            quota["remaining"] = remaining
            self._write_quota_unlocked(account, quota)
            switched = False
            if remaining == 0 and account.id == default_id:
                candidates = sorted(
                    (
                        item
                        for item in accounts
                        if item.id != account.id
                        and self._quota_status_unlocked(item)["remaining"] > 0
                        and _is_query_ready(item)
                    ),
                    key=_last_query_sort_key,
                )
                if candidates:
                    default_id = candidates[0].id
                    switched = True
            self._save_unlocked(accounts, default_id)
            default_account = self._find_unlocked(accounts, default_id)
            return quota, _copy_account(default_account), switched

    def delete(self, account_id: str, *, delete_auth: bool = False) -> AccountRecord:
        with self._lock:
            accounts, default_id = self._load_with_default_unlocked()
            account = self._find_unlocked(accounts, account_id)
            accounts = [item for item in accounts if item.id != account_id]
            if account_id == default_id:
                default_id = accounts[0].id if accounts else ""
            self._save_unlocked(accounts, default_id)

        if delete_auth:
            auth_dir = Path(account.auth_dir).expanduser().resolve()
            root = self.account_root.expanduser().resolve()
            if _is_relative_to(auth_dir, root):
                shutil.rmtree(auth_dir, ignore_errors=True)
        return account

    def _load_with_default_unlocked(self) -> tuple[list[AccountRecord], str]:
        accounts, default_id = self._load_unlocked()
        if accounts and default_id not in {account.id for account in accounts}:
            default_id = accounts[0].id
            self._save_unlocked(accounts, default_id)
        return accounts, default_id

    def _load_unlocked(self) -> tuple[list[AccountRecord], str]:
        if not self.registry_path.exists():
            return [], ""
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            accounts = [AccountRecord.from_dict(item) for item in data.get("accounts", [])]
            default_id = str(data.get("default_account_id") or "")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"账号注册表无法读取：{self.registry_path}") from exc
        if _is_legacy_default_registry(accounts, default_id):
            # 上一版会自动生成 default/主账号；保留其 auth 目录，但要求新版本重新通过管理台登记。
            return [], ""
        return accounts, default_id

    def _save_if_needed_unlocked(
        self,
        accounts: list[AccountRecord],
        default_id: str,
    ) -> None:
        if not self.registry_path.exists():
            self._save_unlocked(accounts, default_id)

    def _save_unlocked(self, accounts: list[AccountRecord], default_id: str) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "default_account_id": default_id,
            "accounts": [asdict(account) for account in accounts],
        }
        temp_path = self.registry_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, self.registry_path)

    def _find_unlocked(
        self,
        accounts: list[AccountRecord],
        account_id: str,
    ) -> AccountRecord:
        for account in accounts:
            if account.id == account_id:
                return account
        raise AccountNotFoundError(account_id)

    def _quota_status_unlocked(self, account: AccountRecord) -> dict[str, Any]:
        now = datetime.now(BEIJING_TZ)
        today = now.date().isoformat()
        quota_path = Path(account.auth_dir) / "quota.json"
        data: dict[str, Any] = {}
        if quota_path.exists():
            try:
                loaded = json.loads(quota_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                data = {}

        used = int(data.get("used") or 0) if data.get("date") == today else 0
        used = max(0, used)
        reset_at = (now + timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return {
            "date": today,
            "limit": account.quota_limit,
            "used": used,
            "remaining": max(0, account.quota_limit - used),
            "reset_at": reset_at.isoformat(),
        }

    def _write_quota_unlocked(self, account: AccountRecord, quota: dict[str, Any]) -> None:
        quota_path = Path(account.auth_dir) / "quota.json"
        quota_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = quota_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(
                {
                    "date": quota["date"],
                    "used": quota["used"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temp_path, quota_path)


def _copy_account(account: AccountRecord) -> AccountRecord:
    return AccountRecord.from_dict(asdict(account))


def _is_legacy_default_registry(
    accounts: list[AccountRecord],
    default_id: str,
) -> bool:
    if len(accounts) != 1 or default_id != "default":
        return False
    account = accounts[0]
    return (
        account.id == "default"
        and account.name == "主账号"
        and Path(account.auth_dir).expanduser().resolve()
        == DEFAULT_AUTH_DIR.expanduser().resolve()
        and Path(account.profile_dir).expanduser().resolve()
        == (DEFAULT_AUTH_DIR / "browser-profile").expanduser().resolve()
    )


def _optional_float(value: Any) -> Optional[float]:
    return float(value) if value is not None else None


def _optional_bool(value: Any) -> Optional[bool]:
    return bool(value) if value is not None else None


def _auth_state(authenticated: Optional[bool], saved: bool) -> str:
    if authenticated is True and saved:
        return "已登录"
    if not saved:
        return "未登录"
    if authenticated is False:
        return "已失效"
    return "待检查"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _last_query_sort_key(account: AccountRecord) -> tuple[int, float, float]:
    return (
        _auth_priority(account),
        account.last_query_at if account.last_query_at is not None else 0.0,
        account.created_at,
    )


def _auth_priority(account: AccountRecord) -> int:
    saved = has_saved_auth(account.auth_dir, account.profile_dir)
    if saved and account.authenticated is True:
        return 0
    if saved:
        return 1
    return 2


def _is_query_ready(account: AccountRecord) -> bool:
    return account.authenticated is True and has_saved_auth(
        account.auth_dir,
        account.profile_dir,
    )
