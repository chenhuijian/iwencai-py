# iwencai-py 本地 API 接入说明

本文档面向其他本地项目接入 `iwencai-py`。推荐其他项目通过 HTTP API 调用问财服务，不直接操作 Chrome、Cookie 或 Playwright。

## 1. 启动服务

在 `iwencai-py` 项目根目录双击：

```text
start_iwencai_server.bat
```

或在命令行启动：

```bash
iwencai-server
```

服务启动时只加载账号配置，不会自动打开可见 Chrome，也不会要求扫码登录。首次使用如果还没有任何账号，服务会直接启动管理台；请在管理台点击“添加并登录”。已有账号登录态失效时，点击账号表格中的“登录”按钮即可重新扫码。

默认服务地址：

```text
http://127.0.0.1:8765
```

打开下面的地址可以进入本地账号管理台：

```text
http://127.0.0.1:8765/
```

管理台以表格展示每个账号的名称、备注、登录状态、今日已用/剩余次数、最近查询和最近状态检查。点击“添加并登录”后会先创建账号，再自动打开该账号独立的 Chrome 窗口，扫码完成后保存登录态；第一个添加并登录的账号会自动成为主账号和默认账号。表格中的其他操作支持登录、退出、检查、设为默认和删除账号。

本机其他项目可以直接访问这个地址。浏览器前端项目从 `localhost`、`127.0.0.1` 或 `[::1]` 的任意端口调用时，服务会自动允许跨端口请求。

服务启动参数还可以配置查询保护：

```bash
iwencai-server --min-query-interval 5 --max-query-queue 50
```

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--min-query-interval` | `5` | 上一次查询结束后，下一次查询开始前至少等待的秒数 |
| `--max-query-queue` | `50` | 正在等待的查询数量上限，超过后返回 `429` |

默认值是保守的本地保护措施，不是问财官方公布的安全频率，也不能保证一定不会触发问财的风控。建议不要把间隔设置为 `0`，并避免在多个服务进程中重复启动本服务。

停止服务：在启动窗口按 `Ctrl+C`。如果 Windows 提示 `Terminate batch job (Y/N)?`，输入 `Y`。

## 2. 首次登录

服务需要问财登录态。首次使用或登录过期时，调用登录接口：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8765/api/auth/login
```

服务会打开浏览器窗口，请在窗口中完成扫码或短信登录。登录成功后，登录态会保存到全局目录：

```text
Windows: %APPDATA%\iwencai-py\auth
其他系统: ~/.iwencai-auth
```

其中 `storage-state.json` 保存 cookies 和 localStorage。其他项目不建议直接修改这些文件，只通过 API 查询和管理登录态。

多账号数据默认保存在：

```text
Windows: %APPDATA%\iwencai-py\
其他系统: ~/.iwencai-auth/
```

`accounts.json` 是账号注册表；新增账号的登录态、浏览器 profile 和每日额度分别保存在 `accounts/<account-id>/` 下。首次通过管理台添加的账号会自动成为默认账号，主账号和后续账号使用相同的添加、扫码和额度管理流程。旧版本自动生成的 `%APPDATA%\iwencai-py\auth` 目录会保留，但不会继续作为隐藏账号使用；升级后请通过管理台重新添加主账号。

如果注册表中还没有任何账号，服务不会自动创建一个隐藏的“主账号”，而是直接启动管理台。请先调用新增账号接口，再调用该账号的登录接口；Web 管理台的“添加并登录”会自动完成这两步。

## 3. 接口列表

### 账号列表

```http
GET /api/accounts
```

示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/accounts
```

返回示例：

```json
{
  "success": true,
  "accounts": [
    {
      "id": "default",
      "name": "主账号",
      "notes": "",
      "is_default": true,
      "authenticated": true,
      "has_saved_auth": true,
      "auth_state": "已登录",
      "quota": {
        "date": "2026-09-22",
        "limit": 100,
        "used": 12,
        "remaining": 88,
        "reset_at": "2026-09-23T00:00:00+08:00"
      }
    }
  ]
}
```

### 新增账号

```http
POST /api/accounts
Content-Type: application/json
```

请求体：

```json
{
  "name": "策略账号 A",
  "notes": "用于策略项目",
  "quota_limit": 100
}
```

新增后调用下面的接口打开该账号的登录窗口。Web 管理台的“添加并登录”按钮会自动完成这两步：

```http
POST /api/accounts/{account_id}/login
```

### 账号操作

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/accounts/{account_id}/login` | 打开该账号的 Chrome 登录窗口 |
| `POST` | `/api/accounts/{account_id}/check` | 检查并刷新该账号登录状态，不消耗查询次数 |
| `POST` | `/api/accounts/{account_id}/test-query` | 使用“上证50”执行一次真实查询，验证查询链路，会消耗 1 次额度 |
| `POST` | `/api/accounts/{account_id}/logout` | 清理该账号登录态 |
| `POST` | `/api/accounts/{account_id}/default` | 设为默认账号 |
| `GET` | `/api/accounts/{account_id}/quota` | 查看该账号今日额度 |
| `PATCH` | `/api/accounts/{account_id}/quota` | 设置该账号今日剩余次数 |
| `PATCH` | `/api/accounts/{account_id}` | 修改名称、备注或额度 |
| `DELETE` | `/api/accounts/{account_id}?delete_auth=true` | 删除账号及其独立登录态；删除默认账号时自动切换到其他账号 |

默认账号可以直接删除；如果还有其他账号，服务会自动把第一个剩余账号设为默认。删除最后一个账号后，服务进入无账号状态，需要通过管理台重新添加并登录。

### 查询账号额度

```http
GET /api/accounts/{account_id}/quota
```

手动设置当天剩余次数：

```http
PATCH /api/accounts/{account_id}/quota
Content-Type: application/json
```

```json
{
  "remaining": 80
}
```

`remaining` 必须在 `0` 到该账号每日额度上限之间。设置剩余次数会同步调整当天已用次数，不会修改每日额度上限。如果把当前默认账号设置为 `0`，服务会自动选择其他已确认登录且有剩余额度的账号作为新的默认账号；响应中的 `account_switched`、`default_account_id` 和 `default_account_name` 会说明切换结果。设置非默认账号为 `0` 不会改变当前默认账号。

默认账号也可以直接查询：

```http
GET /api/quota
GET /api/quota?account_id=account-abc123
```

一次真正开始执行的自然语言查询扣除该账号 `1` 次额度；自动翻页不额外扣除。登录、状态检查、健康检查和文档接口不扣额度。查询在队列满或参数错误时不会扣额度；已经开始执行但失败的查询仍按一次计数。

如果需要验证问财查询链路，而不只是验证 Cookie，可以调用：

```http
POST /api/accounts/{account_id}/test-query
```

该接口固定查询“上证50”，只抓取 1 页，成功或失败都表示真实走过问财查询流程，并按一次查询计入额度；登录态检查仍使用 `/api/accounts/{account_id}/check`，不消耗额度。

查询结果不做缓存。即使两次请求的 `question` 完全相同，服务也会分别访问问财结果页并返回当时的实时结果，同时分别消耗查询额度。`/api/query` 响应带有 `Cache-Control: no-store`，调用方也不应在自己的项目中缓存问财结果。

未指定 `account_id` 时，服务先使用当前默认账号；如果该账号额度已经用完或登录态失效，会自动从其他“已确认登录且有剩余额度”的账号中选择一个继续执行。调用方也可以在请求中指定 `account_id` 作为优先账号。仅有保存登录态但尚未确认登录的账号不会参与自动切换；查询过程中也不会自动弹出扫码窗口。返回结果中的 `account_id` 和 `account_name` 表示实际执行本次查询的账号，`requested_account_id` 表示优先账号，`account_switched` 表示是否发生了自动切换。

查询执行期间可以查看当前实际使用的账号：

```http
GET /api/query/status
```

查询执行时返回 `active=true`、`active_account_id`、`active_account_name`、`question` 和 `elapsed_seconds`；没有查询执行时返回 `active=false`。管理台会自动刷新这个状态。

### 文档列表

```http
GET /api/docs
```

示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/docs
```

返回：

```json
{
  "success": true,
  "docs": [
    {
      "name": "local-api",
      "format": "markdown",
      "json_url": "/api/docs/local-api",
      "raw_url": "/api/docs/local-api.md"
    }
  ]
}
```

### 读取接入文档

JSON 格式：

```http
GET /api/docs/local-api
```

Markdown 原文：

```http
GET /api/docs/local-api.md
```

示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/docs/local-api
Invoke-WebRequest http://127.0.0.1:8765/api/docs/local-api.md
```

如果其他项目需要在页面中展示文档，推荐调用 JSON 接口并读取 `content` 字段；如果只是同步或保存文档原文，使用 `.md` 接口即可。

### 健康检查

```http
GET /api/health
```

示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health
```

返回：

```json
{
  "success": true,
  "service": "iwencai-py",
  "status": "ok"
}
```

### 查询登录状态

```http
GET /api/auth/status
```

多账号场景可以指定账号：

```http
GET /api/auth/status?account_id=account-abc123
```

示例：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/auth/status
```

返回：

```json
{
  "account_id": "default",
  "success": true,
  "authenticated": false,
  "has_saved_auth": true,
  "auth_dir": "C:\\Users\\admin\\AppData\\Roaming\\iwencai-py\\auth",
  "browser_profile_dir": "C:\\Users\\admin\\AppData\\Roaming\\iwencai-py\\auth\\browser-profile",
  "storage_state_file": "C:\\Users\\admin\\AppData\\Roaming\\iwencai-py\\auth\\storage-state.json",
  "metadata_file": "C:\\Users\\admin\\AppData\\Roaming\\iwencai-py\\auth\\metadata.json"
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `authenticated` | 当前登录态是否可用 |
| `has_saved_auth` | 本地是否存在保存过的登录态/profile |
| `auth_dir` | 登录态目录 |
| `storage_state_file` | 共享登录态文件路径 |

### 打开登录窗口

```http
POST /api/auth/login
```

无请求体也可以：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8765/api/auth/login
```

可选请求体：

```json
{
  "account_id": "default",
  "login_timeout": 900,
  "auth_dir": "D:\\iwencai-auth",
  "profile_dir": "D:\\iwencai-auth\\browser-profile"
}
```

字段说明：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `login_timeout` | number | `600` | 等待扫码或短信登录的秒数 |
| `account_id` | string/null | 默认账号 | 指定要登录的账号 |
| `auth_dir` | string/null | 全局默认目录 | 登录态目录 |
| `profile_dir` | string/null | `auth_dir/browser-profile` | 浏览器 profile 目录 |

### 清理登录态

```http
POST /api/auth/logout
```

示例：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8765/api/auth/logout
```

返回：

```json
{
  "account_id": "default",
  "success": true,
  "auth_dir": "C:\\Users\\admin\\AppData\\Roaming\\iwencai-py\\auth"
}
```

### 查询问财

```http
POST /api/query
Content-Type: application/json
```

请求体：

```json
{
  "account_id": "default",
  "question": "上证50"
}
```

完整请求体：

```json
{
  "account_id": "account-abc123",
  "question": "市盈率小于20，市值大于100亿",
  "headless": true,
  "wait_ms": 4000,
  "max_pages": 1,
  "login_timeout": 600,
  "auth_dir": null,
  "profile_dir": null
}
```

字段说明：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `question` | string | 必填 | 问财自然语言查询语句 |
| `account_id` | string/null | 默认账号 | 指定使用哪个问财账号 |
| `headless` | boolean | `true` | 查询时是否无头运行浏览器 |
| `wait_ms` | number | `4000` | 页面加载后等待毫秒 |
| `max_pages` | number/null | `null` | 最大翻页数，`null` 表示不限制 |
| `login_timeout` | number | `600` | 自动触发登录时的等待秒数 |
| `auth_dir` | string/null | 全局默认目录 | 指定登录态目录 |
| `profile_dir` | string/null | `auth_dir/browser-profile` | 指定浏览器 profile |

PowerShell 示例：

```powershell
$body = @{
  account_id = "default"
  question = "上证50"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/api/query `
  -ContentType "application/json" `
  -Body $body
```

返回：

```json
{
  "success": true,
  "requested_account_id": "default",
  "account_switched": false,
  "account_id": "default",
  "account_name": "主账号",
  "quota": {
    "date": "2026-09-22",
    "limit": 100,
    "used": 13,
    "remaining": 87,
    "reset_at": "2026-09-23T00:00:00+08:00"
  },
  "question": "上证50",
  "count": 50,
  "headers": ["股票代码", "股票简称"],
  "pages": 1,
  "rows": [
    {
      "股票代码": "600000",
      "股票简称": "浦发银行"
    }
  ]
}
```

## 4. 其他项目调用示例

### Python

```python
import requests

BASE_URL = "http://127.0.0.1:8765"


def query_iwencai(question: str, account_id: str = "default") -> list[dict]:
    response = requests.post(
        f"{BASE_URL}/api/query",
        json={"account_id": account_id, "question": question},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(data)
    return data["rows"]


rows = query_iwencai("上证50")
print(len(rows), rows[:3])
```

如果不想增加 `requests` 依赖，可以用标准库：

```python
import json
import urllib.request

payload = json.dumps({"question": "上证50"}).encode("utf-8")
request = urllib.request.Request(
    "http://127.0.0.1:8765/api/query",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(request, timeout=120) as response:
    data = json.loads(response.read().decode("utf-8"))

print(data["rows"])
```

### JavaScript / Node.js

```javascript
const response = await fetch("http://127.0.0.1:8765/api/query", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question: "上证50" }),
});

if (!response.ok) {
  throw new Error(await response.text());
}

const data = await response.json();
console.log(data.rows);
```

## 5. 错误处理

常见 HTTP 状态：

| 状态码 | 场景 | 处理建议 |
|---|---|---|
| `400` | 请求参数错误，如 `question` 为空 | 检查请求体 |
| `429` | 查询队列已满，或所有账号今日额度已用尽 | 队列满时按 `Retry-After` 重试；额度用尽时等待 `X-Quota-Reset-At` 后再试 |
| `409` | 登录窗口关闭、登录超时、登录态失效等业务错误 | 重新调用 `/api/auth/login` |
| `500` | 本地依赖缺失或服务内部异常 | 查看启动窗口日志 |

典型错误返回：

```json
{
  "detail": "所有可用问财账号今日查询额度已用尽，请明日再试"
}
```

额度耗尽时响应头包含：

```http
X-Quota-Reset-At: 2026-09-23T00:00:00+08:00
```

## 6. 并发和限制

服务内部会串行执行登录和查询请求，避免多个项目同时抢占同一个浏览器 profile。

查询接口还有两层保护：

1. 同一时间只运行一个问财查询。
2. 查询完成后默认冷却 `5` 秒，再开始下一个查询。

如果等待队列已经达到 `50` 个请求，新的请求会返回：

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
```

调用方收到 `429` 时应等待后重试，不要立即循环重试。一个简单的 Python 处理方式：

```python
import time
import requests

response = requests.post(
    "http://127.0.0.1:8765/api/query",
    json={"question": "上证50"},
    timeout=120,
)
if response.status_code == 429:
    time.sleep(int(response.headers.get("Retry-After", "5")))
    response = requests.post(
        "http://127.0.0.1:8765/api/query",
        json={"question": "上证50"},
        timeout=120,
    )
response.raise_for_status()
```

上述间隔只控制本地查询任务的启动时间；单个查询内部还会访问结果页并自动翻页，因此页数越多，实际访问量和耗时越大。目前在同花顺公开的[法律声明](https://www.10jqka.com.cn/statement.html)中没有看到问财固定的安全频率阈值，不能据此保证账号或 IP 一定不会被限制。建议调用方避免重复查询、控制总量，并保留对 `429`、登录失效和服务异常的处理。

第一版服务只建议绑定本机地址 `127.0.0.1`。如果后续需要开放给局域网或远程机器，需要再增加 API Token、访问控制和日志审计。
