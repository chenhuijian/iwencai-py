import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iwencai_cli import server
from iwencai_cli.accounts import AccountStore, AccountUnavailableError


class StageOneAccountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="iwencai-stage1-"))
        self.store = AccountStore(
            self.temp_dir / "accounts.json",
            self.temp_dir / "accounts",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _ready(self, account) -> None:
        auth_dir = Path(account.auth_dir)
        auth_dir.mkdir(parents=True, exist_ok=True)
        (auth_dir / "storage-state.json").write_text("{}", encoding="utf-8")
        self.store.mark_auth(account.id, True)

    def test_fallback_only_uses_confirmed_logged_in_accounts(self) -> None:
        preferred = self.store.create("主账号", quota_limit=1)
        ready_backup = self.store.create("已登录备用", quota_limit=1)
        unconfirmed_backup = self.store.create("未确认备用", quota_limit=1)
        self._ready(preferred)
        self._ready(ready_backup)

        self.store.reserve_query_with_fallback(preferred.id)
        selected, _ = self.store.reserve_query_with_fallback(preferred.id)
        self.assertEqual(selected.id, ready_backup.id)

        unconfirmed_auth_dir = Path(unconfirmed_backup.auth_dir)
        unconfirmed_auth_dir.mkdir(parents=True, exist_ok=True)
        (unconfirmed_auth_dir / "storage-state.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(AccountUnavailableError):
            self.store.reserve_query_with_fallback(preferred.id)

    def test_query_retries_with_another_account_after_auth_failure(self) -> None:
        preferred = self.store.create("主账号", quota_limit=2)
        backup = self.store.create("备用账号", quota_limit=2)
        self._ready(preferred)
        self._ready(backup)
        calls = []

        def fake_query(_question, **kwargs):
            calls.append(kwargs["auth_dir"])
            if len(calls) == 1:
                raise RuntimeError("问财登录态已失效，请切换账号或重新登录")
            return {"rows": [{"股票代码": "600000"}], "headers": ["股票代码"], "pages": 1}

        server._query_activity.finish()
        server._query_throttle.configure(min_interval=0, max_queue=50)
        try:
            with patch.object(server, "_account_store", self.store):
                with patch.object(server, "query_iwencai", side_effect=fake_query):
                    result = server.query(server.QueryRequest(question="测试查询"))
        finally:
            server._query_throttle.configure(min_interval=5, max_queue=50)

        self.assertTrue(result["account_switched"])
        self.assertEqual(result["account_id"], backup.id)
        self.assertEqual(len(calls), 2)
        self.assertFalse(self.store.get(preferred.id).authenticated)
        self.assertFalse(server._query_activity.snapshot()["active"])

    def test_same_question_is_queried_again_without_cache(self) -> None:
        account = self.store.create("主账号", quota_limit=3)
        self._ready(account)
        questions = []

        def fake_query(question, **kwargs):
            questions.append(question)
            return {
                "rows": [{"股票代码": str(len(questions))}],
                "headers": ["股票代码"],
                "pages": 1,
            }

        server._query_activity.finish()
        server._query_throttle.configure(min_interval=0, max_queue=50)
        try:
            with patch.object(server, "_account_store", self.store):
                with patch.object(server, "query_iwencai", side_effect=fake_query):
                    first = server.query(server.QueryRequest(question="实时查询"))
                    second = server.query(server.QueryRequest(question="实时查询"))
        finally:
            server._query_throttle.configure(min_interval=5, max_queue=50)

        self.assertEqual(questions, ["实时查询", "实时查询"])
        self.assertEqual(first["rows"], [{"股票代码": "1"}])
        self.assertEqual(second["rows"], [{"股票代码": "2"}])
        self.assertEqual(self.store.get_quota(account.id)["used"], 2)

    def test_zeroing_default_switches_to_ready_account_only(self) -> None:
        preferred = self.store.create("主账号", quota_limit=10)
        ready_backup = self.store.create("已登录备用", quota_limit=10)
        unconfirmed_backup = self.store.create("未确认备用", quota_limit=10)
        self._ready(ready_backup)

        _, default_account, switched = self.store.set_quota_remaining(preferred.id, 0)
        self.assertTrue(switched)
        self.assertEqual(default_account.id, ready_backup.id)

        _, default_account, switched = self.store.set_quota_remaining(
            ready_backup.id,
            0,
        )
        self.assertFalse(switched)
        self.assertEqual(default_account.id, ready_backup.id)
        self.assertEqual(unconfirmed_backup.name, "未确认备用")


if __name__ == "__main__":
    unittest.main()
