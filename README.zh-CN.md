# Kopiiki

Kopiiki 有两种提取方式：

- **Snapshot**：生成可离线打开的网站快照 ZIP，并重写本地资源路径。
- **Design**：使用 Gemini 生成以 `DESIGN.md` 为核心的 Design Capsule，供 Coding Agent 理解并重建网站的设计语言，而不是复制原站版权资产。

## 快速启动

在项目根目录运行：

```bash
./start.sh
```

脚本会：

1. 检查 Python 3 和 Node.js。
2. 安装后端与前端依赖。
3. 安装 Playwright Chromium。
4. 启动 Flask 后端 `:5002`。
5. 启动 Vite 前端 `:5176`。

打开：

- 前端界面：http://localhost:5176
- 后端服务：http://localhost:5002

Vite 需要 Node.js `20.19+` 或 `22.12+`。

## Gemini 配置

`Snapshot` 不需要 API key。`Design` 需要 Gemini。

```bash
cp .env.example .env
# 编辑 .env，填入 GEMINI_API_KEY
```

可选变量：

```bash
KOPIIKI_GEMINI_MODEL=gemini-3-pro-preview
KOPIIKI_GEMINI_MOCK=1
KOPIIKI_HOST=127.0.0.1
KOPIIKI_ALLOWED_ORIGINS=http://localhost:5176,http://127.0.0.1:5176
KOPIIKI_ALLOW_PRIVATE_TARGETS=1
```

`KOPIIKI_GEMINI_MODEL` 默认是 `gemini-3-pro-preview`。如果账号暂时没有 preview 模型权限，可以改用 `gemini-2.5-pro`。

修改 `.env` 后需要重启后端。

`KOPIIKI_ALLOW_PRIVATE_TARGETS=1` 只适合可信本地测试，例如提取 localhost 或内网目标。日常使用建议保持关闭。

如果受限网络导致 Playwright Chromium 安装卡住，可以先只启动界面：

```bash
KOPIIKI_SKIP_BROWSER_INSTALL=1 ./start.sh
```

真正执行提取仍然需要可用的 Playwright Chromium。

## GUI 使用方法

1. 打开 `http://localhost:5176`。
2. 在输入行粘贴目标网站 URL。
3. 选择 `Snapshot` 或 `Design`。
4. 按 Enter 或点击 return 图标。
5. 等待日志出现 `DONE`。
6. 下载生成的 ZIP。

右上角 `HISTORY` 可以下载历史 ZIP、复制相对路径、刷新记录或删除旧文件。生成文件保存在 `backend/downloads`。

右上角 `README` 是产品内简明使用说明。

## 产出模式

### Snapshot

Snapshot 生成：

```text
<domain>-<jobid>.zip
```

它会捕获目标页面和本地化后的资源，方便离线打开。

### Design

Design 模式会：

1. 用 Playwright 在 desktop、tablet、mobile 多视口采集确定性浏览器证据。
2. 把临时截图和 DOM/CSS 证据发送给 Gemini。
3. 写出 Markdown-first 的 Design Capsule。
4. 默认不打包原始截图、原站图片、原站视频、logo、商业字体文件或商标化图形。

Design 生成：

```text
<domain>-design-<jobid>.zip
```

ZIP 结构：

```text
DESIGN.md
design/
  references/section-anatomy.md
  references/layout-grammar.md
  references/font-strategy.md
  references/component-families.md
  references/motion.md
  references/responsive.md
  references/asset-prompts.md
  references/visual-checkpoints.md
  evidence/observations.md
  evidence/section-map.md
  evidence/observations.json
  scripts/validate-design-capsule.mjs
```

`DESIGN.md` 包含 token、布局语法、section anatomy、字体替代策略、响应式策略、动效策略、do/don't，以及各 reference 文件索引。

素材提示会写清楚格式、尺寸、背景、透明通道要求、使用位置、生成 prompt、避让规则和实现说明。Kopiiki 只写 prompt，不生成、不下载、不打包图像或视频素材。

解压 Design Capsule 后可以运行：

```bash
node design/scripts/validate-design-capsule.mjs
```

## CLI 使用方法

进入后端目录：

```bash
cd backend
source venv/bin/activate

# Snapshot 模式
python cli.py https://example.com/
python cli.py https://example.com/ --mode snapshot

# Design 模式
python cli.py https://example.com/ --mode design
python cli.py https://example.com/ --design
```

CLI 产物会写入 `backend/downloads`。

## API 说明

前端通过这些接口访问 Flask 后端：

- `POST /api/extract`，请求体为 `{ url, mode }`
- `GET /api/progress/<job_id>`，用于 SSE 日志
- `POST /api/cancel/<job_id>`
- `GET /api/download/<filename>`
- `GET /api/history`
- `GET /api/config`

`/api/config` 只返回 Gemini 是否配置、provider、mock 标记和模型名，不会返回 API key。

## 安全默认值

Kopiiki 是本地开发工具，不是公开托管的爬虫服务。

- 后端默认绑定 `127.0.0.1`。
- CORS 默认限制为本地前端来源。
- `/api/extract` 只接受 `http://` 和 `https://` URL。
- localhost、内网、link-local、multicast、reserved、unspecified IP 目标默认会被阻止。
- `.env` 和 `.env.*` 已从 git 中排除。

如果要把 Kopiiki 暴露到自己电脑之外，请先阅读 [SECURITY.md](SECURITY.md)。

## 验证

后端测试使用 Python `unittest`：

```bash
PYTHONPYCACHEPREFIX=/tmp/kopiiki-pycache backend/venv/bin/python -m unittest discover -s backend/tests
```

mock Design Capsule 测试不需要 Gemini key。如果配置了 `GEMINI_API_KEY`，测试也可以使用本地 HTML fixture 跑真实 Gemini smoke test。

前端检查：

```bash
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=moderate
```

发版检查清单：[docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)。

## 技术架构

```text
[ Browser UI :5176 ] -- POST /api/extract --> [ Flask backend :5002 ]
[ Browser UI :5176 ] <-- SSE progress logs -- [ Flask backend :5002 ]

[ CLI / Agent ] ----------------------------> [ backend/cli.py ]
                                                   |
                                                   v
                                      [ Snapshot / Design pipeline ]
                                                   |
                                                   v
                                      [ Playwright Chromium capture ]
                                                   |
                                                   v
                                      [ Target website evidence ]
                                                   |
                                                   v
                                [ Snapshot ZIP or Gemini Design ZIP ]
```

核心后端模块：

- `backend/app.py`：API、任务、SSE、History、下载。
- `backend/cli.py`：命令行入口。
- `backend/webtwin_assets.py`：Snapshot 提取。
- `backend/design_evidence.py`：多视口 DOM/CSS/截图证据采集。
- `backend/gemini_design.py`：Gemini prompt、JSON 解析、fallback normalization。
- `backend/design_capsule.py`：`DESIGN.md` 和 reference 文件渲染。

## 法律边界

Kopiiki 适用于个人备份、开发测试、研究和教育用途。

用户需要自行确保使用方式符合目标网站服务条款、`robots.txt`、版权法、商标法以及字体/媒体授权要求。

Snapshot 模式可能包含原站资源，只应在你有权创建本地归档的场景中使用。

Design 模式默认不包含原始截图、原站图片、原站视频、logo、商业字体文件、商标化图形或大段原文案。它采用 prompt-first 的方式帮助后续 agent 生成替代素材。

## 鸣谢

Kopiiki 受到 [WebTwin](https://github.com/sirioberati/WebTwin) 启发，并进一步扩展到 agent-readable design extraction。

[MIT License](LICENSE)
