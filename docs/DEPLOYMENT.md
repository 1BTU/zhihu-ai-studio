# 部署与配置

这是单账号、自托管的服务器项目。原生 Python HTTP 服务只监听 `127.0.0.1:27821`，浏览器从 HTTPS Nginx 入口访问。工作台、API 和 Wiki 共享登录。不要把 Python 端口直接改成公网监听。

## 1. 安装与初始化

需要 Linux、Python 3.11+、Node.js、Chromium 所需的系统依赖和 Nginx。Puppeteer 的实际浏览器版本由 lockfile 决定。

```bash
git clone https://github.com/1BTU/zhihu-ai-studio.git
cd zhihu-ai-studio
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
cp .env.example .env
.venv/bin/python scripts/init_local.py
```

初始化会询问账号和密码，只保留密码哈希。没有预设账号或通用默认密码。`daily-config.json` 自动从示例复制，初始 `publish=false`、`notify_email=false`。配置、会话、稿件和运行日志不会被 Git 跟踪。

设置 `.env` 的 `STUDIO_ORIGIN` 为你自己的 **HTTPS origin**，例如 `https://write.example.com`；不加 `/studio`。本项目不自动解析 `.env`，手动启动时需要加载，systemd 使用 `EnvironmentFile`，每日脚本会自动加载。

```bash
set -a
source .env
set +a
.venv/bin/python sync-web.py
.venv/bin/python studio/server.py
```

启动后后端登录页可通过 `curl http://127.0.0.1:27821/login/` 检查。正常网页登录需要下面的 HTTPS 代理，因为认证 Cookie 带 `Secure` 属性。

## 2. 反向代理与服务

参考 [`deploy/nginx.conf.example`](../deploy/nginx.conf.example)，将其中的路径替换成实际目录，放进已经配置好证书的 HTTPS `server` 块。主要路径：

| 地址 | 用途 |
| --- | --- |
| `/studio/overview/` | 发布与指标概览 |
| `/studio/articles/` | 成稿、阅读、删除与恢复、发布 |
| `/studio/chat/` | 多会话 AI 写作 |
| `/studio/columns/` | 专栏定位和模型配置 |
| `/studio/wiki/` | 写作参考库 |
| `/studio/jobs/` | 任务运行结果 |
| `/studio/feedback/` | 文字、截图反馈 |
| `/studio/settings/` | 模型服务设置 |

Wiki 静态输出默认在 `site/wiki/`，由 Nginx 的 `auth_request` 检查同一个会话。改动参考卡后重新执行 `sync-web.py`。页面导出不会替你刷新外站数据。

[`deploy/zhihu-studio.service`](../deploy/zhihu-studio.service) 是服务模板。先修改用户、项目路径和 PATH，再安装。运行账号需要能写项目内的 `private/`、`reports/`、`site/`；Chromium 和 Codex 也必须由这个账号完成各自登录。

## 3. 模型与热点采集

在“模型与设置”中添加兼容 Chat Completions 的模型服务，输入你的服务地址和密钥，验证 `/models` 后选择模型。DeepSeek 是已验证的接入路径；其他服务需要支持流式响应和工具调用，不能保证任意兼容端点都可直接工作。

模型密钥保存在服务器私有 JSON 中，网页得到的是配置状态，文章生成不获得终端或发布工具。

路由顺序：

- 写作：会话模型 → 专栏写作模型 → 全局默认模型。
- 审稿：专栏审稿模型 → 全局审稿模型 → 当前写作模型。

也可以选择本机 Codex CLI。此时需要事先安装并登录 `codex`，以及为它配置所需的联网能力。`CODEX_BIN` 可指定可执行文件。

热点采集脚本是**外部依赖，不在本仓库中复制**。安装你使用的 `news-aggregator-skill`，设置 `NEWS_FETCHER` 为其 `scripts/fetch_news.py` 的绝对路径；脚本需接受 `--source`、`--limit`、`--no-save`，stdout 返回 JSON，诊断写入 stderr。运行它还需要安装其自身 requirements。

```bash
# 使用你实际安装的脚本路径验证；不操作知乎。
.venv/bin/python "$NEWS_FETCHER" --source sspai,hackernews --limit 3 --no-save
```

当前聊天流程也会准备热点上下文，因此开始完整写作前需要配置该采集依赖。排版使用仓库内 `skills/zhihu-converter/SKILL.md`，包含按题材分段、平台输出与修改复核规则；无需另外安装同名旧版 skill。新闻采集 skill 仍是由使用者管理的外部依赖。

## 4. 写作参考库

仓库提供的是公开文章的链接、结构分析、写法页和互动观测证据，**不提供这些文章的全文**。初始笔记便于理解数据结构，互动证据会过期，不应永远视为合格参考。

```bash
.venv/bin/python wiki.py refresh
.venv/bin/python wiki.py lint
.venv/bin/python wiki.py search --query '亲密关系 日常 期待' --limit 4
.venv/bin/python sync-web.py
```

`refresh` 自动更新已收录的少数派候选；其他平台的数据缺失不会被猜成已验证。新增卡片需要来源、实际阅读确认、指标证据和结构分析。参考 [`writing-wiki/README.md`](../writing-wiki/README.md)。

## 5. 知乎登录、图片与首次发布

```bash
npm run login
```

二维码生成在本机 `artifacts/zhihu-login-qr.png`，用自己的知乎 App 扫码。浏览器资料目录保存在 `private/`，不上传 GitHub。页面要求短信或手机验证时需由账号本人完成。

图文稿的 `illustrations` 包含 `before_block`、`hosted_url`、`hosted_sha256`。如使用图床，将 `IMAGE_HOST_BASE` 指向你自己的公共 HTTPS 图片目录。程序只下载该目录下符合规则的图片，检查 SHA-256，再通过编辑器上传；不把 Gitee 外链直接当成知乎图片。正文和图片必须在刷新后通过核验。

图像**生成**目前由交互式 AI 图像能力完成；每天无人值守生成图片的服务尚未接入。已经具备图片的稿件可以使用图文上传和核验流程。不要仅打开 `illustrations.enabled` 就假定定时任务能自动出图。

先在工作台生成并检查一篇稿件，再用明确的发布指令或按钮提交。内部审稿通过、已提交知乎、知乎审核通过分别记录。绑定知乎目标专栏的定向投稿尚未完成实账号验证，程序会停止，不会悄悄发到其他位置。

## 6. 定时与邮件

编辑 `daily-config.json` 后，先只生成：

```bash
.venv/bin/python daily.py --generate-only
```

完整流程依赖外站、采集 Skill、模型和至少两篇合格范文，因此这是一次真实运行，不是离线测试。审稿不通过会保留过程，不发布。

确认模型、登录和文章流程正常后，再设置 `publish=true`，按 [`deploy/cron.example`](../deploy/cron.example) 安装定时任务。示例每天 3 篇短文，在 08:00–11:00、12:00–14:00、18:00–21:00 各随机选择一个发布时间。每分钟 tick，随机计划写入 schedule.json，重启不重抽；提前 30 分钟开始准备，超过窗口保留稿件而不补发。发布前再次校验时间。今天已有旧批次则不重复执行，下一天开始新计划。

邮件目前通过本机 Codex 的已连接 Gmail 能力发送到配置的 `recipient`，**不是内置 SMTP 服务**。需要先配置连接与发送授权，再启用 `notify_email`，运行 `daily.py --test-mail` 验证。QQ 邮箱仅作为收件人；不要求收件邮箱开放 SMTP。未启用邮件时，二维码仍可在服务器文件中查看。

## 7. 意见箱自动修复（可选）

文字、截图粘贴和排期由主站处理；自动执行修复需要单独运行 `studio/repair_runner.py` 和已登录的 Codex。不要默认给服务用户 root 权限。

修复运行在仅含项目源码和本次截图的暂存目录中，检查白名单、精确替换、独立审查、语法及 UI 后部署，保留撤销记录。后端部署需要重启 `zhihu-studio.service`；若要启用此能力，部署者需为专门服务账号配置仅针对该服务的重启授权。普通写作部署无需启用修复 worker。

## 8. 检查

```bash
.venv/bin/python -m unittest discover -s tests -v
npm run test:images
node studio/repair-smoke.mjs .
```

Python 与图片验证测试不发布文章或发送邮件。UI smoke 使用本地模拟接口，不连接真实知乎。README 截图来自作者部署实例，不是仓库内置的演示数据库。

### 知乎日常巡查与互动

`operations.enabled` 开启后，调度器在 `operations.time`（默认 15:00）起两小时内尝试启动一次巡查，与文章使用同一账号锁。工作台 `/studio/operations/` 显示活动入口、候选问题、内容、审稿说明、提交链接和异常。活动发现不等于报名，不自动领取权益或填写报名资料。

回答仅从成功读取问题语境的候选中选取，最多 2 条；引用至少两个实际核实来源，检索合格范文，独立审核后才进入提交。提问最多 1 条，要求先检索同义问题，允许零条。`operations.publish` 独立控制回答/提问提交，默认关闭。记录与模型调用数据留在私有 reports 目录，不进入 Git。

目前活动/候选发现已通过实账号验证；具体问题页曾返回知乎访问限制，回答发布还未完成实账号端到端验证。访问受限会标为 blocked 并停止；按钮不唯一、正文核对失败、回执缺失时停止。发布意图先落盘，结果不确定不会自动重试。部署者应先验证账号访问及发布回执，再启用自动互动。

### 每日创作挑战赛打卡

`challenge.enabled=true` 开启每天 `challenge.time`（默认 20:30）后的自动打卡，晚间文章优先。首次启用前填写仍有效的已报名活动 `challenge.url`。活动已结束或规则变化导致无法识别时，记录异常而不宣称成功。浏览器操作使用已登录的 Codex CLI；工作目录限定到当天 challenge 文件夹，可写目录仅额外加入当前浏览器 profile，网络开启，禁止修改项目源代码或服务器配置。非交互参数参考 [官方文档](https://learn.chatgpt.com/docs/non-interactive-mode)。

AI 读取当日真实进度，只补缺少的任务：原创想法、合适的关注与赞同、经阅读后的评论、查重后的有价值提问等。不反复取消关注或赞同以刷任务、不要求凑稿。每个动作先保存意图和正文；内容提交最多执行一轮，异常或延迟计入时，每隔 30 分钟只复查，最多四次检查，23:00 后停止。中断恢复不再次启动提交。

最终结果由独立浏览器读取活动页核验，必须“已完成”且创作、互动两项数量达标，模型自报成功不算。`python challenge.py --verify-only` 可只核对当天进度。结果、截图、意图与日志在私有 `reports/YYYY-MM-DD/challenge/`，工作台“知乎日常”显示打卡记录。登录失效且跳转登录页时复用二维码邮件流程；每个打卡日最多启动一次登录恢复。
