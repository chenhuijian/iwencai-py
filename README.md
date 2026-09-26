# iwencai-cli

**同花顺问财（iWenCai）** 命令行工具 — 用自然语言选股，返回结构化结果。

[问财（iwencai.com）](https://www.iwencai.com/) 是同花顺（Hithink RoyalFlush）旗下的 AI 选股平台，支持用中文自然语言描述筛选条件（如"市盈率小于20"、"连续三天涨停"、"日线 MACD 金叉"等），后端自动解析为量化条件。本工具把问财的网页查询能力封装为本地 CLI，可作为问财 CLI、同花顺问财命令行工具，用于 A 股选股、股票筛选、量化选股和脚本化查询。

## 特性

- **自然语言查询**：直接用中文描述筛选条件，等同于在问财网页/App 的搜索框输入
- **本地运行**：通过 Playwright 驱动你本机的 Chrome，首次使用时扫码登录
- **无反爬问题**：使用真 Chrome + 去掉自动化指纹，和手动打开浏览器行为一致
- **表格 / JSON 输出**：便于管道处理或配合脚本使用
- **多账号管理**：每个账号独立保存 profile、登录态和每日查询额度

## 安装

安装最新发布版：

```bash
pip install git+https://github.com/chenhuijian/iwencai-py.git@v1.0.0
```

安装 main 分支最新版：

```bash
pip install git+https://github.com/chenhuijian/iwencai-py.git
```

查看所有版本：[Releases](https://github.com/chenhuijian/iwencai-py/releases)。

第一次运行时如果没有 Playwright，加 `--install-playwright -y` 自动安装：

```bash
iwencai-query -q "上证50" --install-playwright -y
```

**前置要求**：系统已安装 Google Chrome（工具会通过 Playwright 的 `channel="chrome"` 调用）。如果系统没有 Chrome，会退回到 Playwright 自带 Chromium（可能被问财的反爬拦截）。

## 使用

```bash
# 基本查询
iwencai-query -q "市盈率小于20，市值大于100亿"

# JSON 输出
iwencai-query -q "连续涨停3天" --json

# 调试：显示浏览器窗口
iwencai-query -q "..." --headful

# 初始化或刷新问财登录态
iwencai-query --login

# 清理全局问财登录态
iwencai-query --logout

# 查询无结果时输出原始响应（调试用）
iwencai-query -q "..." --raw
```

## 本地服务

启动本机 HTTP API 服务：

```bash
iwencai-server
```

服务启动时只加载账号配置，不会自动打开 Chrome 或要求扫码登录。首次使用如果还没有任何账号，服务会直接启动管理台；请在管理台点击“添加并登录”创建主账号并完成扫码。已有账号登录态失效时，也可以在账号表格中点击对应的“登录”按钮。

Windows 也可以直接双击项目根目录的：

```text
start_iwencai_server.bat
```

停止服务时在启动窗口按 `Ctrl+C`；如果 Windows 提示 `Terminate batch job (Y/N)?`，输入 `Y`。

默认监听：

```text
http://127.0.0.1:8765
```

启动后用浏览器打开下面的地址，可以通过表格管理多个问财账号：

```text
http://127.0.0.1:8765/
```

管理台的“添加并登录”会创建账号并自动打开独立的 Chrome 窗口，扫码完成后自动保存登录态。第一个添加并登录的账号会自动成为主账号和默认账号，后续账号可以继续通过相同流程添加。管理台会显示当前默认账号、最近实际使用的账号和当前正在执行的查询账号，并支持检查登录状态、退出登录、切换默认账号、设置当天剩余次数和查看每个账号的每日额度。将当前默认账号的剩余次数设置为 `0` 时，会自动切换到其他已确认登录且有额度的账号。每个账号默认每天 `100` 次查询，自动翻页仍按一次自然语言查询计数。

本机其他项目可以直接调用；浏览器前端从 `localhost`、`127.0.0.1` 或 `[::1]` 的任意端口访问时，服务会允许跨端口请求。

查询时优先使用指定账号；如果指定账号没有剩余额度或登录态失效，会自动切换到其他“已确认登录且有剩余额度”的账号。未指定 `account_id` 时，优先使用默认账号。查询返回中的 `account_id` 是本次实际使用的账号；服务不会在后台查询过程中自动弹出扫码窗口。

查询结果不会按关键词缓存。相同关键词的每次请求都会重新访问问财并获取实时结果，也会分别计入查询次数；查询接口响应同时设置为 `no-store`，避免客户端或中间层复用旧结果。

服务默认采用保守的查询保护策略：

- 同一时间只执行一个问财查询。
- 上一次查询结束后，默认至少等待 `5` 秒才开始下一次查询。
- 最多允许 `50` 个查询排队；队列满时返回 HTTP `429`，调用方稍后重试。

可以按本机实际情况调整：

```bash
iwencai-server --min-query-interval 5 --max-query-queue 50
```

这只是本地保护措施，不代表问财官方承诺的安全阈值；不要把 `0` 间隔当作推荐配置。

常用接口：

```bash
# 文档列表
curl http://127.0.0.1:8765/api/docs

# Markdown 接入文档
curl http://127.0.0.1:8765/api/docs/local-api.md

# 健康检查
curl http://127.0.0.1:8765/api/health

# 检查登录态
curl http://127.0.0.1:8765/api/auth/status

# 查看所有账号
curl http://127.0.0.1:8765/api/accounts

# 打开浏览器并扫码登录
curl -X POST http://127.0.0.1:8765/api/auth/login

# 查询
curl -X POST http://127.0.0.1:8765/api/query ^
  -H "Content-Type: application/json" ^
  -d "{\"account_id\":\"default\",\"question\":\"上证50\"}"
```

服务内部会串行执行登录和查询，并限制查询启动频率，避免多个项目同时抢占同一个浏览器 profile 或短时间内连续访问问财。

其他项目接入请看：[本地 API 接入说明](docs/local-api.md)。

### 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `-q, --question` | 自然语言查询语句 | — |
| `--login` | 打开浏览器并扫码登录，保存全局登录态 | 关 |
| `--logout` | 清理全局登录态和浏览器 profile | 关 |
| `--login-timeout` | 等待扫码或短信登录的秒数 | 600 |
| `--json` | 以 JSON 格式输出 | 关 |
| `--headful` | 显示浏览器窗口 | 关 |
| `--wait-ms` | 页面加载后等待毫秒 | 4000 |
| `--profile-dir` | 指定浏览器 profile 目录 | 全局登录态目录下的 `browser-profile` |
| `--auth-dir` | 指定全局登录态目录 | Windows 用户应用数据目录下的 `iwencai-py/auth` |
| `--raw` | 查询无结果时输出原始响应 | 关 |
| `--install-playwright` | 缺失 Playwright 时自动安装 | 关 |
| `-y, --yes` | 安装时跳过确认 | 关 |

## 工作原理

1. HTTP 服务启动时只加载账号配置，不自动打开登录窗口
2. 管理台或 CLI 登录时启动本机 Chrome（每个账号使用独立 profile）
3. 查询时优先选择默认账号，并在额度用尽或登录失效时切换到其他已确认登录账号
4. 去除 `navigator.webdriver` 等自动化特征，避开反爬
5. 打开问财新版筛选结果页
6. 等待页面 JS 渲染结果表格
7. 从 DOM 提取股票列表（合并问财的固定左列 + 滚动右列双栏表格，并自动翻页）
8. 按账号记录每日查询额度
9. 输出为表格或 JSON

账号数据目录：

```text
Windows: %APPDATA%\iwencai-py\
其他系统: ~/.iwencai-auth/
```

其中：

- `accounts.json` 保存账号名称、备注、默认账号和账号目录。
- `accounts/<account-id>/` 保存新增账号的独立 cookies、localStorage、Chrome profile 和 `quota.json`。
- 第一个通过管理台添加的账号会自动成为默认账号，主账号和后续账号使用完全相同的流程。
- 旧版本自动生成的 `auth/` 主账号目录会保留，但不会继续作为隐藏账号使用；升级后请通过管理台重新添加主账号。

其他项目查询时传 `account_id` 作为优先账号；不传时使用默认账号。优先账号额度用完或登录失效后，服务会自动选择其他已确认登录且有剩余额度的账号继续查询。

## 注意事项

- 问财网页的结果列会根据查询语句动态变化；工具输出的列名就是页面上显示的表头
- 问财网页单页通常最多显示 50 条；工具会自动翻页抓取后续结果
- 频繁大量查询可能触发问财的速率限制 —— 脚本使用时建议合理间隔
- 本项目与同花顺 / 问财官方无任何关联，仅是对其公开网页结果的自动化封装

## License

Apache-2.0
