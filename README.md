# Skill 分类管理器

<p align="center">
  <strong>按科研工作流分类、批量管理 cc-switch 中 skill 在各 AI Agent 启用状态的桌面工具</strong>
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-blue.svg">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.7%2B-3776AB.svg?logo=python&logoColor=white">
  <img alt="Zero Dependencies" src="https://img.shields.io/badge/Dependencies-0-6aa84f.svg">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg">
</p>

Skill 分类管理器是一个本地运行的**零第三方依赖**工具，用于按科研工作流阶段对 [cc-switch](https://github.com/farion1231/cc-switch) 中的 skill 进行分类，并批量控制它们在 7 个 AI Agent（Claude Code、Codex、Gemini CLI 等）中的启用状态。

采用 **本地 Python 服务 + 浏览器前端** 架构，界面风格与 cc-switch 同源（现代深色卡片式），双击即可运行，无需安装任何依赖。

---

## 目录

- [功能特性](#功能特性)
- [支持的 Agent](#支持的-agent)
- [快速开始](#快速开始)
- [界面使用](#界面使用)
- [AI 智能分类](#ai-智能分类)
- [命令行使用](#命令行使用)
- [路径自动探测](#路径自动探测)
- [工作原理](#工作原理)
- [文件结构](#文件结构)
- [常见问题](#常见问题)
- [注意事项](#注意事项)
- [许可证](#许可证)

---

## 功能特性

- **7 个 AI Agent 独立开关**：每个 skill 可分别控制在 Claude Code、Codex、Gemini CLI、Grok Build、OpenCode、Hermes、MiniMax Code 中的启用状态。
- **分类 × Agent 一键开关**：侧栏每个分类卡片内嵌 7 个 Agent 圆点开关，右侧分类内还有一整排整类开关，一键控制该分类下所有 skill。
- **按工作流分类**：将 skill 按科研流程（文献、实验、绘图、写作、汇报、开发）分组，支持自定义类别。
- **✨ AI 智能分类**：复用 cc-switch 中已配置的大模型（如 DeepSeek），一键对 skill 自动分类；支持模型切换与精确到多个分类的范围选择，**先预览、确认后才写入**。
- **扫描更新**：一键重读 cc-switch 数据库，自动发现新安装、尚未归类的 skill。
- **未分类集中管理**：新 skill 自动归入「未分类」分组，方便批量归类。
- **自由归类**：可新建、删除、重命名分类，任意 skill 可重新归入其它类别（归属即时保存）。
- **路径自动探测**：部署到任意电脑无需手动配置，自动定位数据库、SSOT 与各 Agent 目录。
- **路径诊断**：一键查看所有探测到的路径及其存在性，方便排查问题。
- **Web + 命令行**：浏览器界面与 CLI 双入口，功能一致。

## 支持的 Agent

与 cc-switch `skills` 表的 `enabled_*` 列一一对应：

| Agent | 启用列 | 默认 skills 目录 |
|---|---|---|
| Claude Code | `enabled_claude` | `~/.claude/skills` |
| Codex | `enabled_codex` | `~/.codex/skills` |
| Gemini CLI | `enabled_gemini` | `~/.gemini/skills` |
| Grok Build | `enabled_grokbuild` | `~/.grok/skills` |
| OpenCode | `enabled_opencode` | `~/.config/opencode/skills` |
| Hermes | `enabled_hermes` | `%LOCALAPPDATA%\hermes`（Windows）/ `~/.hermes/skills` |
| MiniMax Code | `enabled_mcode` | `~/.minimax/skills` |

> **说明**：cc-switch 的 `claude-desktop`、`openclaw`、`pi` 虽出现在应用列表中，但没有独立的 `enabled_*` 列、不做独立 skill 同步，因此本工具不纳入管理。

## 快速开始

### 环境要求

- Windows / macOS / Linux
- Python 3.7+（**仅需标准库，零第三方依赖**）
- 一个现代浏览器（Chrome / Edge / Firefox 等）
- 已安装 [cc-switch](https://github.com/farion1231/cc-switch)

验证 Python 是否已加入 PATH：

```bash
python --version
```

### 启动（Web 界面）

**Windows**：双击 `技能分类管理器.bat`，会自动启动本地服务并打开浏览器。

**macOS / Linux**：在项目目录下运行：

```bash
python server.py
```

然后在浏览器访问 <http://127.0.0.1:8765/>。

> 关闭服务：关闭运行 `server.py` 的那个终端窗口即可。

### 命令行

```bash
python skill_manager.py list
```

详细用法见 [命令行使用](#命令行使用)。

## 界面使用

### 界面布局

- **左侧**：分类列表（含「未分类」分组）。每个分类卡片右侧内嵌 **7 个 Agent 圆点开关**，可一键开关该分类下某 Agent 的全部 skill；悬停分类项可删除分类。
- **右侧**：选中分类后，顶部有一整排 **7 个 Agent 整类开关**；下方列出该分类每个 skill 的明细，每个 skill 同样带 7 个 Agent 开关和归类下拉框。
- **顶部按钮**：`扫描更新`、`新建类别`、`路径诊断`、`✨ AI 智能分类`、`全部开启`、`全部关闭`、`放弃修改`、`应用修改`。

### 日常操作

1. **分类 × Agent 一键开关**：侧栏分类卡片右侧的圆点，或右侧顶部的一排整类开关，均可一键控制该分类下某 Agent 的全部 skill。
2. **单个 skill 微调**：在 skill 卡片里点击对应 Agent 的开关（蓝 = 开启、灰 = 关闭）。
3. **应用修改**：所有改动只是暂存（顶部出现黄点提示），点 **「应用修改」** 后写入数据库并同步文件。
4. 完成后**重新打开 cc-switch**，界面里看到的状态与本工具完全一致。

### 新 skill 的归类

在 cc-switch 里新装 skill 后：

1. 点顶部 **「扫描更新」**，程序重读数据库，新 skill 自动进入左侧 **「未分类」** 分组。
2. 点「未分类」，用每个 skill 右侧的下拉框**选择目标分类**（即写入 `categories.json` 并立即生效）。
3. 没有合适的分类？下拉框选 **「＋ 新建类别…」**，或点顶部 **「新建类别」**。
4. 想给已归类 skill 换分类，同样在它的下拉框里重选即可。

> 归类操作（新建类别、调整归属）会立即保存到 `categories.json`，无需点「应用修改」；「应用修改」只负责写各 Agent 的启用状态。

## AI 智能分类

本工具可直接复用 cc-switch 中已配置的大模型（如 DeepSeek、智谱 GLM 等 OpenAI/Anthropic 兼容服务）来对 skill 自动分类，**无需额外填写 API Key**。

### 使用方式

1. 点顶栏 **「✨ AI 智能分类」**。
2. 选择**模型**（自动读取 cc-switch 中配置的可用模型，如 `deepseek-flash` / `deepseek-v4-pro`）。
3. 选择**分类范围**：
   - 仅「未分类」：只处理尚未归类的 skill（默认）。
   - 全部 skill：全部重新分类。
   - 当前分类：当前侧栏选中的那一个分类。
   - 指定分类：**多选**，精确勾选任意几个分类。
4. （可选）填写一行「想怎么分」的分类意图。
5. 点「开始分类」，大模型返回分类方案后，界面会展示 **Skill / 原分类 / 新分类** 的预览表格。
6. 核对无误后点 **「确认应用」**，方案才会真正写入 `categories.json`。

> **安全设计**：AI 分类采用「两段式」流程——生成方案时**只读不写**，必须等你点「确认应用」后才落地，确保数据在你确认前零改动。

### 工作原理

- 从 cc-switch 数据库的 `providers` 表读取已配置的 Provider（API Key / Base URL / 模型），凭据直接复用，不另存、不展示明文。
- 优先使用 OpenAI 兼容接口，其次 Anthropic 兼容接口。
- 分类方案以 JSON 形式返回并解析，新分类会自动创建，skill 自动归入。

## 命令行使用

在项目目录下运行：

```bash
python skill_manager.py list               # 查看分类及各类启用统计
python skill_manager.py status 01          # 查看某分类下每个 skill 的开关
python skill_manager.py on  02             # 启用 02 类（全部 Agent）
python skill_manager.py off 02 -a codex    # 只给 Codex 关闭 02 类
python skill_manager.py on  all -a gemini  # 只给 Gemini 开启全部
python skill_manager.py sync               # 数据库与文件对账修复
python skill_manager.py check              # 校验分类覆盖是否完整
python skill_manager.py paths              # 自动探测并打印 cc-switch 相关路径
python skill_manager.py scan               # 列出尚未归类的新 skill
python skill_manager.py assign ima-skill 05_汇报与文档  # 归入分类（不存在则自动新建）
python skill_manager.py newcat 07_其他     # 新建空分类
```

- 分类名支持前缀模糊匹配（如 `01`、`02`）。
- `-a` 可选值：`claude` / `codex` / `gemini` / `grokbuild` / `opencode` / `hermes` / `mcode` / `both`（默认 `both`）。
- 命令行操作立即生效，无需确认。

## 路径自动探测

本工具**不写死路径**，启动时自动按 cc-switch 的官方解析规则定位相关路径，因此可直接部署到任意电脑：

| 探测项 | 解析规则（与 cc-switch 源码一致） |
|---|---|
| 中央配置目录 | 环境变量 `CC_SWITCH_CONFIG_DIR` 优先，否则 `~/.cc-switch` |
| 数据库文件 | `<配置目录>/cc-switch.db` |
| SSOT skill 仓库 | `skillStorageLocation=unified` → `~/.agents/skills`，否则 `<配置目录>/skills` |
| 各 Agent 目录 | 优先读取 `settings.json` 的 `claudeConfigDir` / `codexConfigDir` / `geminiConfigDir` / `grokConfigDir` / `opencodeConfigDir` / `hermesConfigDir`，否则用默认值 |
| MiniMax Code 目录 | 环境变量 `MINIMAX_DATA_DIR`（或 `MAVIS_DATA_DIR`）优先，否则 `~/.minimax` |
| Hermes 目录 | Windows 用 `%LOCALAPPDATA%\hermes`，其它平台用 `~/.hermes` |

查看探测结果：界面点顶部 **「路径诊断」** 按钮；CLI 运行 `python skill_manager.py paths`。

## 工作原理

与 cc-switch 自身逻辑保持一致：

1. **SSOT 仓库**：skill 源文件存放在 `~/.cc-switch/skills/<目录>`（单一事实源）。
2. **启用状态**：记录在 `~/.cc-switch/cc-switch.db` 的 `skills` 表 `enabled_<agent>` 列。
3. **文件同步**：`copy` 方式——启用时把 SSOT 目录复制到对应 Agent 的 `skills` 目录；禁用时从应用目录删除（**不删除 SSOT 仓库本体**，随时可重新开启）。

## 文件结构

| 文件 | 作用 |
|---|---|
| `技能分类管理器.bat` | Windows 双击启动入口（本地服务 + 自动开浏览器） |
| `server.py` | Web 后端（REST API，标准库实现） |
| `web/index.html` | 前端页面结构 |
| `web/style.css` | 前端样式（cc-switch 风格） |
| `web/app.js` | 前端交互逻辑 |
| `ccswitch_paths.py` | 路径自动探测模块（数据库 / SSOT / 各 Agent 目录） |
| `skill_manager.py` | 命令行版 |
| `categories.json` | 分类映射表（界面或 CLI 均可修改） |
| `LICENSE` | MIT 开源许可证 |
| `README.md` | 本说明文档 |

## 常见问题

**Q：双击 `.bat` 没反应 / 浏览器没打开？**
检查 Python 是否加入 PATH：命令行运行 `python --version`。若未加入，重装 Python 并勾选 "Add Python to PATH"，或手动运行 `python server.py` 后访问 `http://127.0.0.1:8765/`。

**Q：提示「未找到 cc-switch 数据库」？**
请确认已安装 cc-switch；若使用了自定义配置目录，设置环境变量 `CC_SWITCH_CONFIG_DIR` 后重启本工具。

**Q：某个 Agent 的 skills 目录显示「缺失」？**
说明该 Agent 尚未安装或未初始化，属正常现象；启用其 skill 时会自动创建对应目录。

**Q：切换到别的电脑需要改配置吗？**
不需要。启动时自动探测路径；如需确认，点「路径诊断」或运行 `python skill_manager.py paths` 查看。

**Q：端口 8765 被占用？**
若提示服务已在运行，直接访问 `http://127.0.0.1:8765/` 即可；如需换端口，编辑 `server.py` 中的 `PORT`。

**Q：AI 智能分类提示「未找到可用的 AI 接口配置」？**
请先在 cc-switch 中配置一个 OpenAI/Anthropic 兼容的 Provider（如 DeepSeek、智谱 GLM），并确保其已启用。本工具会自动读取该配置。

## 注意事项

1. **点「应用修改」前先退出 cc-switch**（托盘图标右键退出），避免数据库写冲突；应用完再打开 cc-switch 即可。
2. 工具只改 cc-switch 数据库的启用标记，并同步各 Agent 的 `skills` 目录；`~/.cc-switch/skills/` 里的 skill 仓库本体永不删除。
3. 若使用了 cc-switch 的「自定义配置目录」，请设置环境变量 `CC_SWITCH_CONFIG_DIR` 指向该目录，本工具会自动识别。
4. 归类信息保存在本工具的 `categories.json` 中，请随项目一起备份/分发。
5. **关于 `categories.json` 的公开**：本仓库随附的 `categories.json` 是作者本人维护的分类映射表，随仓库一并公开。它**不含任何 API Key、账号、令牌等敏感信息**（AI 凭据始终从 cc-switch 本地数据库实时读取，从不写入本项目文件）。若你 fork 后不想公开自己的分类数据，可在 `.gitignore` 中加入 `categories.json`，或改用本地维护。

## 许可证

本项目采用 [MIT License](LICENSE) 开源。使用前请阅读 LICENSE 文件了解具体条款。

---

<p align="center">
  由 <a href="https://github.com/farion1231/cc-switch">cc-switch</a> 生态驱动 · 纯 Python 标准库实现 · 零依赖
</p>
