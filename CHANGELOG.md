# 更新说明

本项目所有重要变更都会记录在本文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2026-09-27

### 新增

- **AI 智能分类支持多 API 接口选择**：弹窗新增「API 接口」下拉框，列出 cc-switch 中所有已配置 API Key 的 Provider（OpenAI 兼容与 Anthropic 兼容均可），当前启用的接口默认选中并置顶；新增 `GET /api/ai_providers` 接口。
- **模型列表一键实时刷新**：模型下拉旁新增 🔄 按钮，调用所选接口的 `GET /v1/models` 实时拉取最新模型（Anthropic 风格自动使用 `x-api-key` 鉴权）；拉取失败时保留原列表并提示原因；新增 `POST /api/ai_models` 接口。
- **Anthropic 兼容接口的模型映射解析**：claude-desktop 类型 Provider 的模型列表改从 `providers.meta` 的 `claudeDesktopModelRoutes` 路由映射读取（此前误用兜底模型导致映射模型不可见），`labelOverride` 作为显示别名，前端显示为「别名（实际模型）」；并兜底读取 env 的 `ANTHROPIC_MODEL`。
- 模型下拉支持任意已刷新出的模型名，不再局限于 cc-switch 原 modelCatalog。

### 修复

- **新建/删除分类后界面不更新**：`_assign` / `_newcat` / `_delcat` 重赋值 `_cat_order` 时缺少 `global` 声明，模块级分类顺序表永不更新，导致 UI 需重启或重扫才能看到分类变更。
- **base_url 重复拼接 `/v1`**：base_url 自带版本路径（如智谱的 `/api/paas/v4`）时不再重复拼接，对 chat/completions、messages、models 三个端点统一生效。
- **AI 调用期间界面假死**：`/api/ai_classify` 与 `/api/ai_models` 不再持有服务全局锁（LLM 调用最长 120 秒，此前会阻塞所有其他请求）；`_ai_classify` 改为「快照输入 → 无锁网络 I/O → 校验写回」的细粒度锁结构。
- **CLI 合计行口径不一致**：`skill_manager.py list` 新增「◆ 未分类」独立行，合计行改为按全库 skill 去重统计，修复重复归类导致的虚增。
- 前端：AI 分类范围选「当前分类」但未选中具体分类时，提前拦截并给出明确提示；接口列表拉取失败时显示具体错误原因。

### 改进

- CLI 的 `save_categories` 改为原子写（临时文件 + `os.replace`），与 Web 端一致，防止写入中断损坏 `categories.json`。
- 刷新模型列表按钮带旋转加载动画，接口切换自动联动模型列表与接口信息提示。

## [1.0.0] - 初始版本

- 按科研工作流分类管理 cc-switch 中的 skill，批量控制 7 个 AI Agent 的启用状态。
- 本地 Python 服务 + 浏览器前端架构，零第三方依赖。
- AI 智能分类（两段式：先预览、确认后写入）。
- 路径自动探测，部署到任意电脑无需手动配置。
- Web 界面 + 命令行双入口。
