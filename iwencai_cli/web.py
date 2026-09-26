from __future__ import annotations


ACCOUNT_MANAGER_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>问财账号管理</title>
  <style>
    :root {
      color-scheme: dark;
      --ink: #e6edf3;
      --muted: #9ca9b5;
      --line: #30363d;
      --panel: #161b22;
      --canvas: #0d1117;
      --accent: #2f81f7;
      --accent-dark: #58a6ff;
      --green: #3fb950;
      --yellow: #d29922;
      --red: #f85149;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font: 14px/1.5 "Segoe UI", "Microsoft YaHei", sans-serif;
    }

    .shell {
      width: min(1440px, calc(100% - 40px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }

    header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 22px;
    }

    h1, h2, p { margin: 0; }
    h1 { font-size: 24px; letter-spacing: 0; }
    h2 { font-size: 16px; }
    .subtitle { color: var(--muted); margin-top: 5px; }

    .service-state {
      color: var(--green);
      border-left: 3px solid var(--green);
      padding: 4px 0 4px 10px;
      white-space: nowrap;
    }
    .header-status { display: grid; gap: 8px; justify-items: end; }
    .current-account { color: var(--muted); font-size: 12px; text-align: right; }
    .current-query { color: var(--accent-dark); font-size: 12px; max-width: 420px; text-align: right; }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 18px;
      margin-bottom: 16px;
    }

    .toolbar {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
    }

    .form-grid {
      display: grid;
      grid-template-columns: minmax(150px, 1.1fr) minmax(180px, 1.5fr) 110px auto;
      gap: 10px;
      flex: 1;
      min-width: min(100%, 700px);
    }

    label { display: grid; gap: 5px; color: var(--muted); font-size: 12px; }
    input {
      width: 100%;
      height: 36px;
      border: 1px solid #3d444d;
      border-radius: 4px;
      padding: 0 10px;
      color: var(--ink);
      background: #0d1117;
      font: inherit;
    }

    button {
      height: 36px;
      border: 1px solid #3d444d;
      border-radius: 4px;
      padding: 0 12px;
      background: #21262d;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      white-space: nowrap;
    }

    button:hover { border-color: var(--accent); color: var(--accent-dark); }
    button:disabled { opacity: .55; cursor: wait; }
    button.primary { border-color: var(--accent); background: var(--accent); color: #fff; }
    button.primary:hover { background: var(--accent-dark); color: #fff; }
    button.danger:hover { border-color: var(--red); color: var(--red); }

    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr));
      gap: 1px;
      background: var(--line);
      border: 1px solid var(--line);
      margin-bottom: 16px;
    }

    .metric { background: var(--panel); padding: 13px 16px; }
    .metric-label { color: var(--muted); font-size: 12px; }
    .metric-value { font-size: 20px; font-weight: 600; margin-top: 2px; }

    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; min-width: 980px; }
    th, td { border-bottom: 1px solid var(--line); padding: 12px 10px; text-align: left; vertical-align: middle; }
    th { color: var(--muted); font-size: 12px; font-weight: 600; background: #21262d; white-space: nowrap; }
    tbody tr:last-child td { border-bottom: 0; }
    tbody tr:hover { background: #1c2128; }
    .account-name { font-weight: 600; }
    .account-notes, .secondary { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .status { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
    .status::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: #6e7681; }
    .status.ok { color: var(--green); }
    .status.ok::before { background: var(--green); }
    .status.warn { color: var(--yellow); }
    .status.warn::before { background: var(--yellow); }
    .status.bad { color: var(--red); }
    .status.bad::before { background: var(--red); }
    .quota { min-width: 160px; }
    .quota-line { display: flex; justify-content: space-between; gap: 12px; }
    .quota-bar { height: 5px; background: #30363d; margin-top: 7px; border-radius: 3px; overflow: hidden; }
    .quota-fill { height: 100%; background: var(--accent); }
    .quota-fill.low { background: var(--yellow); }
    .quota-fill.empty { background: var(--red); }
    .tag { display: inline-block; border: 1px solid #388bfd; color: var(--accent-dark); padding: 2px 7px; border-radius: 3px; font-size: 12px; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; min-width: 360px; }
    .actions button { height: 30px; padding: 0 9px; font-size: 12px; }
    .empty { color: var(--muted); text-align: center; padding: 34px 10px; }
    .message { min-height: 22px; color: var(--muted); margin-top: 10px; }
    .message.error { color: var(--red); }
    .footnote { color: var(--muted); font-size: 12px; margin-top: 12px; }

    @media (max-width: 760px) {
      .shell { width: min(100% - 24px, 1440px); padding-top: 18px; }
      header { display: block; }
      .service-state { display: inline-block; margin-top: 14px; }
      .header-status { justify-items: start; }
      .current-account { text-align: left; }
      .current-query { text-align: left; }
      .form-grid { grid-template-columns: 1fr 1fr; min-width: 100%; }
      .form-grid label:nth-child(2) { grid-column: span 2; }
      .form-grid button { width: 100%; }
      .summary { grid-template-columns: 1fr 1fr; }
      .panel { padding: 12px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <h1>问财账号管理</h1>
        <p class="subtitle">所有账号都通过浏览器扫码添加，第一个账号会自动成为主账号。</p>
      </div>
      <div class="header-status">
        <div class="service-state" id="service-state">服务连接中...</div>
        <div class="current-account" id="current-account">当前默认账号：未设置</div>
        <div class="current-query" id="current-query">当前查询：无</div>
      </div>
    </header>

    <section class="panel toolbar">
      <form id="account-form" class="form-grid">
        <label>账号名称
          <input name="name" required maxlength="80" placeholder="例如：主账号 / 策略账号 A">
        </label>
        <label>备注
          <input name="notes" maxlength="500" placeholder="可选">
        </label>
        <label>每日额度
          <input name="quota_limit" type="number" min="1" value="100" required>
        </label>
        <button class="primary" type="submit">添加并登录</button>
      </form>
      <button id="refresh-button" type="button">刷新列表</button>
      <div class="message" id="message" role="status"></div>
    </section>

    <section class="summary" aria-label="账号汇总">
      <div class="metric"><div class="metric-label">账号总数</div><div class="metric-value" id="total-count">0</div></div>
      <div class="metric"><div class="metric-label">已登录</div><div class="metric-value" id="logged-count">0</div></div>
      <div class="metric"><div class="metric-label">今日已用</div><div class="metric-value" id="used-count">0</div></div>
      <div class="metric"><div class="metric-label">今日剩余</div><div class="metric-value" id="remaining-count">0</div></div>
    </section>

    <section class="panel">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>账号</th>
              <th>登录状态</th>
              <th>今日额度</th>
              <th>最近查询</th>
              <th>最近检查</th>
              <th>默认账号</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody id="account-rows">
            <tr><td class="empty" colspan="7">正在读取账号...</td></tr>
          </tbody>
        </table>
      </div>
      <p class="footnote">每个账号使用独立的浏览器 profile 和登录态。第一个添加并登录的账号会自动成为默认主账号；登录、检查和查询操作会排队执行，请等待操作完成。</p>
    </section>
  </main>

  <script>
    const rows = document.getElementById("account-rows");
    const message = document.getElementById("message");
    const serviceState = document.getElementById("service-state");
    const currentAccount = document.getElementById("current-account");
    const currentQuery = document.getElementById("current-query");
    let accounts = [];

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
      }[char]));
    }

    function formatTime(value) {
      if (!value) return "未记录";
      return new Intl.DateTimeFormat("zh-CN", {
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit"
      }).format(new Date(value * 1000));
    }

    function statusClass(account) {
      if (account.auth_state === "已登录") return "ok";
      if (account.auth_state === "待检查") return "warn";
      return "bad";
    }

    function renderAccounts() {
      const total = accounts.length;
      const logged = accounts.filter((account) => account.auth_state === "已登录").length;
      const used = accounts.reduce((sum, account) => sum + account.quota.used, 0);
      const remaining = accounts.reduce((sum, account) => sum + account.quota.remaining, 0);
      document.getElementById("total-count").textContent = total;
      document.getElementById("logged-count").textContent = logged;
      document.getElementById("used-count").textContent = used;
      document.getElementById("remaining-count").textContent = remaining;
      const defaultAccount = accounts.find((account) => account.is_default);
      const lastUsedAccount = accounts
        .filter((account) => account.last_query_at)
        .sort((left, right) => right.last_query_at - left.last_query_at)[0];
      if (!defaultAccount) {
        currentAccount.textContent = "当前默认账号：未设置";
      } else if (lastUsedAccount && lastUsedAccount.id !== defaultAccount.id) {
        currentAccount.textContent =
          `当前默认账号：${defaultAccount.name}；最近实际使用：${lastUsedAccount.name}`;
      } else {
        currentAccount.textContent = `当前默认账号：${defaultAccount.name}`;
      }

      if (!accounts.length) {
        rows.innerHTML = '<tr><td class="empty" colspan="7">还没有账号</td></tr>';
        return;
      }

      rows.innerHTML = accounts.map((account) => {
        const quota = account.quota;
        const percent = quota.limit ? Math.min(100, Math.round(quota.used / quota.limit * 100)) : 0;
        const fillClass = quota.remaining === 0 ? "empty" : (percent >= 80 ? "low" : "");
        return `<tr>
          <td>
            <div class="account-name">${escapeHtml(account.name)}</div>
            <div class="account-notes">${escapeHtml(account.notes || "无备注")}</div>
            <div class="secondary">${escapeHtml(account.id)}</div>
          </td>
          <td><span class="status ${statusClass(account)}">${escapeHtml(account.auth_state)}</span></td>
          <td class="quota">
            <div class="quota-line"><span>${quota.used} / ${quota.limit}</span><span>${quota.remaining} 次</span></div>
            <div class="quota-bar"><div class="quota-fill ${fillClass}" style="width:${percent}%"></div></div>
          </td>
          <td>${formatTime(account.last_query_at)}</td>
          <td>${formatTime(account.last_auth_check_at)}</td>
          <td>${account.is_default ? '<span class="tag">当前默认</span>' : ""}</td>
          <td>
            <div class="actions">
              <button data-action="login" data-id="${escapeHtml(account.id)}">登录</button>
              <button data-action="check" data-id="${escapeHtml(account.id)}">检查</button>
              <button data-action="logout" data-id="${escapeHtml(account.id)}">退出</button>
              <button data-action="quota" data-id="${escapeHtml(account.id)}">设置剩余</button>
              ${account.is_default ? "" : `<button data-action="default" data-id="${escapeHtml(account.id)}">切换到此账号</button>`}
              <button class="danger" data-action="delete" data-id="${escapeHtml(account.id)}">删除</button>
            </div>
          </td>
        </tr>`;
      }).join("");
    }

    function showMessage(text, isError = false) {
      message.textContent = text;
      message.className = isError ? "message error" : "message";
    }

    async function request(url, options = {}) {
      const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `请求失败（${response.status}）`);
      return data;
    }

    async function loadAccounts() {
      serviceState.textContent = "服务连接中...";
      try {
        const data = await request("/api/accounts");
        accounts = data.accounts || [];
        renderAccounts();
        serviceState.textContent = "服务已连接";
      } catch (error) {
        serviceState.textContent = "服务连接失败";
        showMessage(error.message, true);
        rows.innerHTML = '<tr><td class="empty" colspan="7">无法读取账号信息</td></tr>';
      }
    }

    async function loadQueryStatus() {
      try {
        const data = await request("/api/query/status");
        if (!data.active) {
          currentQuery.textContent = "当前查询：无";
          return;
        }
        currentQuery.textContent =
          `当前查询：${data.active_account_name}｜${data.question}（已运行 ${data.elapsed_seconds} 秒）`;
      } catch (error) {
        currentQuery.textContent = "当前查询：状态未知";
      }
    }

    async function accountAction(action, id) {
      const account = accounts.find((item) => item.id === id);
      if (!account) return;
      const button = document.querySelector(`[data-action="${action}"][data-id="${CSS.escape(id)}"]`);
      const originalText = button ? button.textContent : "";
      if (button) { button.disabled = true; button.textContent = "处理中..."; }
      try {
        if (action === "login") {
          await request(`/api/accounts/${encodeURIComponent(id)}/login`, { method: "POST", body: "{}" });
          showMessage(`${account.name} 登录成功`);
        } else if (action === "check") {
          await request(`/api/accounts/${encodeURIComponent(id)}/check`, { method: "POST", body: "{}" });
          showMessage(`${account.name} 登录状态已更新`);
        } else if (action === "logout") {
          if (!confirm(`确定清理账号“${account.name}”的登录态吗？`)) return;
          await request(`/api/accounts/${encodeURIComponent(id)}/logout`, { method: "POST", body: "{}" });
          showMessage(`${account.name} 已退出登录`);
        } else if (action === "quota") {
          const raw = window.prompt(
            `请输入“${account.name}”今天的剩余次数（0-${account.quota.limit}）`,
            String(account.quota.remaining),
          );
          if (raw === null) return;
          const remaining = Number(raw.trim());
          if (!Number.isInteger(remaining) || remaining < 0 || remaining > account.quota.limit) {
            throw new Error(`剩余次数必须是 0-${account.quota.limit} 的整数`);
          }
          const updated = await request(`/api/accounts/${encodeURIComponent(id)}/quota`, {
            method: "PATCH",
            body: JSON.stringify({ remaining }),
          });
          const defaultMessage = updated.account_switched
            ? `，已自动切换到“${updated.default_account_name}”`
            : "";
          showMessage(`${account.name} 的今日剩余次数已设置为 ${remaining}${defaultMessage}`);
        } else if (action === "default") {
          await request(`/api/accounts/${encodeURIComponent(id)}/default`, { method: "POST", body: "{}" });
          showMessage(`${account.name} 已切换为当前默认账号`);
        } else if (action === "delete") {
          if (!confirm(`确定删除账号“${account.name}”及其登录态吗？`)) return;
          await request(`/api/accounts/${encodeURIComponent(id)}?delete_auth=true`, { method: "DELETE" });
          showMessage(`${account.name} 已删除`);
        }
        await loadAccounts();
      } catch (error) {
        showMessage(error.message, true);
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = originalText;
        }
      }
    }

    document.getElementById("account-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      const button = formElement.querySelector("button");
      button.disabled = true;
      try {
        const created = await request("/api/accounts", {
          method: "POST",
          body: JSON.stringify({
            name: form.get("name"),
            notes: form.get("notes"),
            quota_limit: Number(form.get("quota_limit")),
          }),
        });
        const account = created.account;
        formElement.reset();
        formElement.querySelector('[name="quota_limit"]').value = "100";
        await loadAccounts();
        showMessage(`账号已创建，正在打开“${account.name}”的登录窗口，请扫码登录...`);
        await request(`/api/accounts/${encodeURIComponent(account.id)}/login`, {
          method: "POST",
          body: "{}",
        });
        showMessage(`${account.name} 登录成功，账号已准备好使用`);
        await loadAccounts();
      } catch (error) {
        showMessage(error.message, true);
      } finally {
        button.disabled = false;
      }
    });

    document.getElementById("refresh-button").addEventListener("click", loadAccounts);
    rows.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (button) accountAction(button.dataset.action, button.dataset.id);
    });
    loadAccounts();
    loadQueryStatus();
    window.setInterval(loadQueryStatus, 2000);
  </script>
</body>
</html>'''
