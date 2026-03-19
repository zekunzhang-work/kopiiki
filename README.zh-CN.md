# Kopiiki

一个用于提取网页快照并打包为独立离线包的工具。

## 🚀 快速启动 (GUI 模式)

执行项目根目录下的脚本可自动完成环境配置和服务启动：
1. 检查 Python 3 和 Node.js 环境。
2. 安装后端 (`pip`) 与前端 (`npm`) 依赖。
3. 下载 Playwright 提取所需的 Chromium 浏览器内核。
4. 启动 Flask 后端 (`:5002`) 与 Vite 前端 (`:5176`)。

```bash
cd kopiiki
./start.sh
```

- **前端界面**: http://localhost:5176
- **后端服务**: http://localhost:5002

---

## 🤖 CLI 与 AI Agent 集成

Kopiiki 可作为 AI Agent（如 Cursor、Claude Code 等）的数据处理管道。项目中包含了一个用于命令行环境的独立运行脚本。

### 命令行（CLI）使用方法
可以在终端中直接调用提取流程：
```bash
# 1. 进入后端目录
cd kopiiki/backend

# 2. 激活 Python 虚拟环境
source venv/bin/activate

# 3. 运行爬虫脚本并指定目标 URL
python cli.py https://example.com/
```
脚本将唤起无头 Chromium 实例，提取与之关联的至多 6 个子页面，完成内部链接的本地化转换，并将生成的 `[domain].zip` 打包存入 `kopiiki/backend/downloads/`。

### AI Agent 工作流
大语言模型 Agent 可通过以下步骤将 Kopiiki 接入其自动化工作流：
1. 执行 Shell 命令 `python cli.py <URL>`。
2. 使用 `unzip downloads/<domain>.zip -d ./working_dir` 解压生成的压缩包。
3. 读取生成的 `README.md` 及提取的 `.html` 文件，作为生成 React/Tailwind 代码的参考基准。

---

## ⚙️ 技术架构

项目采用前后端分离架构，处理网页渲染与资源抓取：

```
[ 用户终端 / AI Agent ]
      │
[ 前端 (React) :5176 ] <─── 实时进度状态 (SSE) ───┐
      │                                        │
      └─── 提取请求 (POST) ───▶ [ 后端 (Flask) :5002 ]
                                     │
                                     └──▶ [ Playwright (Chromium) / CLI script ]
                                               │
                                               └──▶ [ 目标网页 ]
```

- **前端**: 处理交互逻辑与进度的展示。
- **后端**: Python 服务管理 Playwright 实例，负责高性能的网页渲染、导航解析及静态资源映射。

---

## 🖥️ 前端操作指引

Kopiiki 提供了基本的操作界面用于网页提取：

1. **输入 URL**: 在输入框中输入目标网页地址。
2. **开始提取**: 点击右侧的 Enter 图标或按下回车键。
3. **实时监控**: 界面下方显示实时的提取执行日志。
4. **取消操作**: 提取过程中可随时点击停止图标中断任务。
5. **获取结果**: 提取完成后，系统会自动生成并下载包含网页资源的 ZIP 压缩包。

![前端操作界面预览](docs/assets/preview.png)

---

## ❤️ 鸣谢与法律声明

### 鸣谢
本工具的开发受到 [**WebTwin**](https://github.com/sirioberati/WebTwin) 项目启发。感谢原作者在网页存档及自动化抓取领域的开源工作。

### 法律免责声明
1. **用途限制**: Kopiiki 仅供个人备份、开发测试、学术研究及教育目的使用。
2. **合规义务**: 用户在使用本工具时，须确保行为符合目标网站的 `robots.txt` 协议、服务条款及相关版权法律。
3. **风险自担**: 用户应对提取内容及后续使用行为承担法律责任。开发者不对因使用本工具导致的版权纠纷或法律风险承担责任。

---

[MIT License](LICENSE)
