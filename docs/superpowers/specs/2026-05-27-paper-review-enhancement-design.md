# 论文查非增强 — 实现设计

> 基于 docs/chafei.md 的三阶段实现

## Phase 1: 最小可用版

打通 上传→规则检查→Review Evidence→Ai-Review Prompt→Markdown报告→下载 全链路

### 改动清单

1. **Prompt upgrade** (`chat_prompts.py`, `chat_executor.py`) — Ai-Review风格，要求返回 `markdown_report`
2. **Review Evidence Pack** (新 `paper_review_evidence.py`) — 结构化证据组织
3. **Report Builder** (新 `paper_review_report_builder.py`) — build_markdown_report()
4. **FileExecutor 增强** — 生成 evidence pack，保存报告到对象存储，artifact 包含 report_files
5. **ChatExecutor compose** — 注入 paper_format_report 到最终响应
6. **前端** — 报告卡片 + 下载按钮

## Phase 2: 工具库管理

- 新 `builtin/paper_format_tools.py` manifest
- 注册到 `ToolSyncService.BUILTIN_MODULES`

## Phase 3: 多格式报告

- `build_docx_report()` + `build_pdf_report()`
- 多文件保存到对象存储
- 前端多下载按钮
