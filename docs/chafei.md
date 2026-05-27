# 论文查非辅助报告流程设计方案

> 目标：当用户在聊天界面上传 Word / PDF / LaTeX 论文，并被系统识别为“查非 / 格式检查 / 审阅”意图后，后端自动完成文档解析、规则检查、Ai-Review 风格提示词生成、模型审阅、辅助报告生成，并在界面展示可下载的 Markdown / Word / PDF 报告。

---

## 1. 设计目标

本方案不是单纯新增一个“大模型问答提示词”，而是构建一条稳定、高效率、可管理、可扩展的论文查非辅助链路。

核心目标如下：

1. 用户上传论文后，系统自动识别是否属于论文查非 / 格式审阅任务。
2. 文件被保存到对象存储，后续流程只通过附件元信息读取文件。
3. 后端解析 Word / PDF / LaTeX，抽取正文、标题、段落、页边距、字号、图表、引用等信息。
4. 规则检查器先生成客观、结构化的问题清单。
5. 再生成 Review Evidence Pack，作为大模型审阅的证据输入。
6. 使用 Ai-Review 风格 Prompt，让大模型输出专业、稳定、可读的论文审阅意见。
7. 最终在聊天界面展示简短辅助报告，并提供 Markdown / Word / PDF 下载入口。
8. 内置函数、工具库工具、提示词、模板规则需要分层管理，避免逻辑混乱。

---

## 2. 当前项目已有基础

当前 `new_tgg` 分支已经具备论文查非能力的基础链路：

```text
上传附件
↓
聊天消息携带 ext.attachments
↓
ManagerPolicy 识别 paper_format_check
↓
FileExecutor 读取附件
↓
parse_file_content 解析文件
↓
check_paper_format 执行规则检查
↓
生成 paper_format_report artifact
↓
ChatExecutor 使用 chat.paper_format_check.system 组织回答
```

当前已有能力包括：

| 模块 | 当前状态 |
|---|---|
| 意图识别 | 已有 `paper_format_check` 路由 |
| 能力注册 | 已有 `file.paper_format_check` capability |
| 文件读取 | 已通过对象存储读取附件 |
| docx 解析 | 已用 `python-docx` 抽取段落、标题、样式、页边距等 |
| tex 解析 | 已支持源码解析 |
| pdf 解析 | 基础解析存在，但论文格式审阅链路中还未重点实现 |
| 规则检查 | 已有摘要、关键词、参考文献、标题层级、字号、行距、标点等检查 |
| Prompt | 已有 `chat.paper_format_check.system`，但内容较简单 |
| 下载报告 | 尚未完整实现 |
| 工具库展示 | `paper_format_checker` 尚未封装成工具库工具 |

---

## 3. 推荐总流程

```text
Word / PDF / LaTeX 上传
↓
对象存储保存附件
↓
文档解析
- docx：python-docx
- tex：源码解析
- pdf：PyMuPDF / pypdf / Docling，后续补强
↓
规则检查
- 结构问题
- 格式问题
- 文字规范问题
- 模板差异问题
↓
生成 Review Evidence Pack
↓
Ai-Review 风格 Prompt
↓
模型生成
- 简短回答
- Markdown 报告
- 问题列表
- 修改建议
↓
可选导出
- Markdown
- Word
- PDF
↓
聊天界面展示辅助报告卡片和下载按钮
```

---

## 4. 分层架构设计

推荐将整个功能拆成 6 层，而不是把所有逻辑都写进一个函数。

```text
接口层
  chat upload / chat message / report download

路由层
  ManagerPolicy / ManagerLoop / ManagerDispatcher

执行层
  FileExecutor / PaperReviewExecutor 可选

工具层
  file_parsers / paper_format_checker / paper_review_report_builder

Prompt 层
  chat.paper_format_check.system / prompt_builder / prompt_admin

产物层
  paper_format_report artifact / report files / object storage
```

---

## 5. 用户提交论文后的详细处理流程

### 5.1 上传阶段

用户在聊天界面上传 Word / PDF / LaTeX 文件。

前端调用：

```http
POST /chat/uploads
```

后端处理：

1. 接收上传文件。
2. 保存到对象存储，例如 MinIO / 本地对象存储。
3. 返回附件元信息。

返回结构建议：

```json
{
  "name": "paper.docx",
  "kind": "document",
  "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "bucket": "chat-attachments",
  "object_key": "org/user/session/paper.docx",
  "url": "/chat/files/chat-attachments/org/user/session/paper.docx",
  "size": 1024000
}
```

注意：后续 Agent 不应依赖本地临时路径，而应通过 `bucket + object_key` 读取对象存储内容。

### 5.2 消息提交阶段

用户输入：

```text
帮我检查这篇论文格式、错别字和模板问题
```

前端发送：

```http
POST /chat/sessions/{session_id}/messages
```

请求体中的 `ext.attachments` 应携带上传返回的附件信息：

```json
{
  "message": "帮我检查这篇论文格式、错别字和模板问题",
  "ext": {
    "attachments": [
      {
        "name": "paper.docx",
        "kind": "document",
        "bucket": "chat-attachments",
        "object_key": "org/user/session/paper.docx",
        "url": "/chat/files/chat-attachments/org/user/session/paper.docx"
      }
    ],
    "template_id": "generic_cn_thesis",
    "report_formats": ["md", "docx"]
  }
}
```

### 5.3 意图识别阶段

`ManagerPolicy` 根据用户 query 和附件类型识别任务。

命中条件：

```text
附件类型是 document
并且用户问题命中以下关键词：
- 查非
- 论文格式
- 排版
- 模板
- 规范检查
- 错别字
- 病句
- 标点错误
- paper format
- proofread
```

识别结果：

```json
{
  "intent": "paper_format_check",
  "needs": [
    "file.paper_format_check",
    "chat.response.compose"
  ]
}
```

### 5.4 文件执行阶段

`ManagerDispatcher` 根据 plan step 找到 `FileExecutor`。

当前推荐保留 `FileExecutor` 作为第一阶段实现入口：

```text
file.paper_format_check
↓
FileExecutor.execute()
↓
read_attachment_bytes()
↓
parse_file_content()
↓
check_paper_format()
↓
build_review_evidence_pack()
↓
generate_report_files()
↓
paper_format_report artifact
```

---

## 6. 文档解析设计

### 6.1 docx 解析

使用：

```python
python-docx
```

应抽取：

| 信息 | 用途 |
|---|---|
| 段落文本 | 内容审阅、证据片段 |
| 标题层级 | 检查结构跳级 |
| 字体 / 字号 | 检查格式 |
| 加粗 / 对齐 | 检查标题格式 |
| 行距 / 段前段后 | 检查正文排版 |
| 页边距 | 检查版式 |
| 页眉页脚 | 检查论文模板要求 |
| 图题 / 表题 | 检查图表规范 |

### 6.2 LaTeX 解析

使用源码正则和轻量解析。

应抽取：

| 信息 | 用途 |
|---|---|
| `\documentclass` | 判断模板类型 |
| `\title` | 检查标题 |
| `\author` | 检查作者信息 |
| `abstract` 环境 | 检查摘要 |
| `\section` / `\subsection` | 检查章节层级 |
| `\caption` | 检查图题表题 |
| `bibliography` / `thebibliography` | 检查参考文献 |
| figure / table 数量 | 检查图表完整性 |

注意：LaTeX 只看源码不能代表最终 PDF 排版，需要在报告中说明限制。

### 6.3 PDF 解析

短期可使用：

```text
pypdf / PyMuPDF
```

中长期可引入：

```text
Docling
```

推荐分阶段实现：

| 阶段 | 实现方式 | 能力 |
|---|---|---|
| 第一阶段 | pypdf | 文本抽取 |
| 第二阶段 | PyMuPDF | 页面、字体、坐标、图片、表格位置 |
| 第三阶段 | Docling | 文档结构、版面、表格、引用结构 |

PDF 解析输出应统一到项目内部结构：

```json
{
  "kind": "pdf",
  "text": "...",
  "pages": [
    {
      "page_no": 1,
      "text": "...",
      "blocks": [],
      "fonts": [],
      "figures": [],
      "tables": []
    }
  ],
  "headings": [],
  "references": [],
  "layout": {}
}
```

---

## 7. 规则检查设计

规则检查器负责生成客观问题，不负责写审稿意见。

推荐分成四类：

```text
结构问题
格式问题
文字规范问题
模板差异问题
```

### 7.1 结构问题

示例规则：

| 规则 | 说明 |
|---|---|
| `structure.abstract_missing` | 缺少摘要 |
| `structure.keywords_missing` | 缺少关键词 |
| `structure.references_missing` | 缺少参考文献 |
| `structure.heading_jump` | 标题层级跳变 |
| `structure.figure_caption_missing` | 图题缺失 |
| `structure.table_caption_missing` | 表题缺失 |

### 7.2 格式问题

示例规则：

| 规则 | 说明 |
|---|---|
| `style.margin_outlier` | 页边距异常 |
| `style.heading_font_size_small` | 标题字号偏小 |
| `style.line_spacing_small` | 正文行距偏小 |
| `style.font_inconsistent` | 字体不一致 |
| `style.paragraph_indent_missing` | 正文首行缩进缺失 |

### 7.3 文字规范问题

示例规则：

| 规则 | 说明 |
|---|---|
| `text.fullwidth_ascii` | 全角英文 / 数字 |
| `text.multiple_spaces` | 连续空格 |
| `text.mixed_punctuation` | 中英文标点混用 |
| `text.heading_trailing_punct` | 标题末尾标点 |
| `text.suspected_typo` | 疑似错别字 |
| `text.suspected_grammar_issue` | 疑似病句 |

### 7.4 模板差异问题

当前项目只有 `generic_cn_thesis` 通用模板，不足以严格校验学校毕业论文格式。

建议新增模板规则管理：

```text
backend/agent/tools/paper_format_templates.py
```

模板结构建议：

```json
{
  "template_id": "school_cn_thesis_v1",
  "name": "某高校本科毕业论文模板",
  "version": "1.0.0",
  "docx_rules": {
    "required_sections": ["摘要", "关键词", "目录", "正文", "参考文献", "致谢"],
    "page_margin_cm": {
      "top": 2.5,
      "bottom": 2.5,
      "left": 3.0,
      "right": 2.5
    },
    "body_font": {
      "zh": "宋体",
      "en": "Times New Roman",
      "size_pt": 12
    },
    "line_spacing": 1.5
  }
}
```

重庆邮电大学研究生学位论文模板（2022版）在本项目中采用双通道处理：

1. `附件1-Word批注版-重庆邮电大学研究生学位论文模板（2022版）V2.0.docx` 作为确定性规则模板，用于 `paper_format_checker` 的章节、页边距、字体、字号、行距等规则校验。
2. `附件4-写作指南-重庆邮电大学研究生学位论文模板（2022版）V2.0.docx` 作为写作指南证据，从对象存储读取并抽取文本后交给大模型做补充评判。
3. 最终报告合并规则模型表达和写作指南模型补充；最终 `issues` 仍以规则检查结果为准，写作指南产生的新建议必须标注为需人工复核。

---

## 8. Review Evidence Pack 设计

`Review Evidence Pack` 是规则检查结果与大模型之间的桥梁。

它的作用：

1. 降低 Prompt 输入噪声。
2. 避免大模型直接读全文导致成本高。
3. 让模型基于证据生成审阅意见。
4. 支持后续报告导出。

建议结构：

```json
{
  "document": {
    "file_name": "paper.docx",
    "document_type": "docx",
    "template_id": "generic_cn_thesis",
    "page_count": 25,
    "word_count": 8200
  },
  "score": 76,
  "limitations": [
    "未指定严格学校模板，当前使用通用论文规则。",
    "LaTeX 检查仅基于源码，不代表最终 PDF 版式。"
  ],
  "outline": [
    {
      "level": 1,
      "title": "摘要",
      "paragraph_index": 2
    }
  ],
  "issues": [
    {
      "code": "structure.abstract_missing",
      "title": "缺少摘要",
      "severity": "high",
      "category": "structure",
      "message": "文档中未识别到“摘要”部分。",
      "evidence": "未找到标题或段落“摘要”",
      "location": {
        "section": "abstract"
      },
      "suggestion": "补充中文摘要并按模板放在前置部分。"
    }
  ],
  "evidence_snippets": [
    {
      "id": "E1",
      "source": "paragraph",
      "location": "paragraph 12",
      "text": "这是存在连续空格的段落……",
      "related_issue_codes": ["text.multiple_spaces"]
    }
  ],
  "style_summary": {
    "font_names": ["宋体", "Times New Roman"],
    "font_sizes": [10.5, 12, 14],
    "line_spacing_values": [1.0, 1.5],
    "margin_cm": {
      "top": 2.54,
      "bottom": 2.54,
      "left": 3.18,
      "right": 3.18
    }
  }
}
```

---

## 9. Ai-Review 风格 Prompt 设计

### 9.1 Prompt 作用

Ai-Review 风格 Prompt 不负责发现问题，而负责把结构化检查结果转化为专业审阅意见。

分工如下：

```text
paper_format_checker：发现问题
Review Evidence Pack：整理证据
Ai-Review Prompt：生成审阅报告
Report Builder：导出报告文件
```

### 9.2 推荐 Prompt

建议替换或升级：

```text
chat.paper_format_check.system
```

推荐内容：

```text
你是论文格式与规范审阅助手，输出风格参考专业论文审阅报告。

你将收到：
1. 用户问题。
2. 文档解析摘要。
3. Review Evidence Pack。
4. 规则检查生成的 issues。
5. 模板限制说明。

你的任务：
1. 根据结构化检查结果生成审阅意见。
2. 不要编造论文内容、模板要求、学校规范或参考文献结论。
3. 没有证据的问题必须标注“需人工复核”。
4. 如果没有指定模板，只能按通用论文规范给建议。
5. 如果 PDF / LaTeX 解析存在限制，必须在局限性中说明。
6. 优先处理 high severity 问题，再处理中低优先级问题。
7. 输出要适合直接保存为 Markdown 报告。
8. 只返回 JSON。

返回 JSON 格式：
{
  "answer": "给用户看的简短中文回复",
  "summary": "一句话总结",
  "markdown_report": "完整 Markdown 报告正文",
  "issues": [
    {
      "title": "问题标题",
      "severity": "high|medium|low",
      "category": "structure|style|text|template",
      "location": "问题位置",
      "evidence": "证据",
      "impact": "影响",
      "suggestion": "修改建议",
      "need_human_review": true
    }
  ],
  "download_title": "论文查非辅助报告"
}
```

### 9.3 输出 Markdown 报告模板

模型生成的 `markdown_report` 建议固定结构：

```markdown
# 论文查非与格式审阅辅助报告

## 一、总体结论

- 文档类型：
- 综合评分：
- 问题数量：
- 主要风险：

## 二、高优先级问题

### 1. 问题标题

- 类型：
- 位置：
- 证据：
- 影响：
- 修改建议：

## 三、中优先级问题

...

## 四、低优先级问题

...

## 五、需人工复核项

...

## 六、局限性说明

...

## 七、修改优先级建议

1. 先补充结构缺失内容。
2. 再统一标题与正文格式。
3. 最后处理标点、空格、错别字等细节。
```

---

## 10. 报告生成设计

### 10.1 报告文件类型

建议支持三种格式：

| 格式 | 实现优先级 | 说明 |
|---|---:|---|
| Markdown | 高 | 最快实现，前端可直接下载 |
| Word | 中 | 用 `python-docx` 根据 Markdown / 结构化 JSON 生成 |
| PDF | 低 | 可由 Markdown / HTML 转 PDF |

### 10.2 后端新增报告生成器

建议新增文件：

```text
backend/agent/tools/paper_review_report_builder.py
```

核心函数：

```python
def build_markdown_report(review_output: dict, evidence_pack: dict) -> str:
    ...

def build_docx_report(markdown_report: str, meta: dict) -> bytes:
    ...

def build_pdf_report(markdown_report: str, meta: dict) -> bytes:
    ...
```

第一阶段只实现 Markdown：

```python
def build_markdown_report(review_output: dict, evidence_pack: dict) -> str:
    report = str(review_output.get("markdown_report") or "").strip()
    if report:
        return report

    return f"""# 论文查非与格式审阅辅助报告

## 一、总体结论

{review_output.get("summary", "")}

## 二、问题列表

{format_issues(evidence_pack.get("issues", []))}

## 三、局限性说明

{format_limitations(evidence_pack.get("limitations", []))}
"""
```

### 10.3 报告保存到对象存储

报告生成后保存到对象存储：

```text
bucket: chat-reports
object_key: org_id/user_id/session_id/message_id/paper-review-report.md
```

返回下载信息：

```json
{
  "format": "md",
  "file_name": "paper-review-report.md",
  "bucket": "chat-reports",
  "object_key": "org/user/session/message/paper-review-report.md",
  "url": "/chat/files/chat-reports/org/user/session/message/paper-review-report.md",
  "content_type": "text/markdown"
}
```

### 10.4 paper_format_report artifact 扩展

当前 `paper_format_report` 建议扩展为：

```json
{
  "document_type": "docx",
  "template_id": "generic_cn_thesis",
  "summary": "已完成论文查非检查，共发现 8 个问题。",
  "score": 76,
  "issues": [],
  "limitations": [],
  "parsed_files": [],
  "unsupported": [],
  "model_summary": "",
  "review_evidence_pack": {},
  "ai_review_output": {
    "answer": "",
    "summary": "",
    "markdown_report": "",
    "issues": []
  },
  "report_files": [
    {
      "format": "md",
      "file_name": "论文查非辅助报告.md",
      "url": "/chat/files/chat-reports/..."
    }
  ]
}
```

---

## 11. 前端展示设计

当 assistant 消息返回 `message_type = file_answer` 且 payload 中存在 `paper_format_report` 或 `report_files` 时，前端展示辅助报告卡片。

### 11.1 报告卡片

```text
论文查非辅助报告

综合评分：76 / 100
发现问题：8 个
高优先级：2 个
中优先级：4 个
低优先级：2 个

主要问题：
- 缺少摘要
- 参考文献格式不完整
- 标题层级跳变
- 中英文标点混用

[查看详情] [下载 Markdown] [下载 Word]
```

### 11.2 下载按钮

前端从 payload 中读取：

```json
{
  "report_files": [
    {
      "format": "md",
      "file_name": "论文查非辅助报告.md",
      "url": "/chat/files/chat-reports/..."
    }
  ]
}
```

渲染为：

```text
下载 Markdown
下载 Word
下载 PDF
```

第一阶段可只显示 Markdown。

---

## 12. 内置函数、工具、提示词的管理

### 12.1 内置函数

当前 `paper_format_checker.py` 是内部函数模块，适合放规则检查逻辑：

```text
backend/agent/tools/paper_format_checker.py
```

职责：

```text
输入 parsed document
输出 issues / score / limitations
```

不建议它直接调用大模型，也不建议它直接生成 Word / PDF 报告。

### 12.2 是否封装成工具库工具

当前 `paper_format_checker` 没有封装成工具库工具，因此不会在工具库页面显示。

如果希望在工具库页面显示，需要新增内置工具 manifest。

建议新增：

```text
backend/agent/tools/builtin/paper_format_tools.py
```

示例：

```python
from agent.tools.paper_format_checker import check_paper_format

TOOL_MANIFESTS = [
    {
        "tool_key": "file.paper_format_check",
        "display_name": "论文查非与格式检查",
        "description": "对 docx、tex、pdf 论文执行结构、格式、文字规范和模板差异检查。",
        "tool_type": "native",
        "category": "file_parse",
        "handler_path": "agent.tools.builtin.paper_format_tools.check",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "parsed": {"type": "object"},
                "file_name": {"type": "string"},
                "query": {"type": "string"},
                "template_id": {"type": "string"}
            },
            "required": ["parsed", "file_name"]
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "issues": {"type": "array"},
                "limitations": {"type": "array"}
            }
        },
        "risk_level": "low",
        "is_readonly": True
    }
]

def check(parsed: dict, file_name: str, query: str = "", template_id: str | None = None) -> dict:
    return check_paper_format(
        parsed=parsed,
        file_name=file_name,
        query=query,
        template_id=template_id,
    )
```

然后在：

```text
backend/app/services/tool_sync_service.py
```

加入：

```python
"agent.tools.builtin.paper_format_tools"
```

这样执行：

```http
POST /tools/sync/builtin
```

后，工具库页面才可以展示这个内置工具。

### 12.3 Prompt 管理

Prompt 分三层管理：

| 层级 | 文件 / 入口 | 作用 |
|---|---|---|
| 代码默认 Prompt | `backend/agent/prompts/chat_prompts.py` | 内置默认版本 |
| Prompt Builder | `backend/agent/prompts/prompt_builder.py` | 运行时选择 prompt_key 和版本 |
| Prompt 管理页面 | `prompt_admin` / 数据库 | 后台可编辑、灰度、回滚 |

建议将论文查非 prompt 升级为：

```text
chat.paper_format_check.system
版本：chat_paper_format_check_v2_ai_review
```

并且在 prompt 内容中明确：

```text
只基于 Review Evidence Pack 输出。
不得编造模板要求。
没有证据的结论标注“需人工复核”。
返回 JSON，必须包含 markdown_report。
```

---

## 13. 推荐新增 / 修改文件

### 13.1 后端新增文件

```text
backend/agent/tools/paper_review_evidence.py
backend/agent/tools/paper_review_report_builder.py
backend/agent/tools/builtin/paper_format_tools.py
```

### 13.2 后端修改文件

```text
backend/agent/router/executors/file_executor.py
backend/agent/tools/paper_format_checker.py
backend/agent/tools/file_parsers.py
backend/agent/prompts/chat_prompts.py
backend/agent/prompts/prompt_builder.py
backend/agent/router/executors/chat_executor.py
backend/app/services/tool_sync_service.py
```

### 13.3 前端修改方向

```text
ChatMessage 渲染组件
文件回答卡片组件
报告下载按钮组件
```

建议组件：

```text
PaperReviewReportCard
ReportDownloadButtons
IssueSeverityBadge
```

---

## 14. 高效率落地方案

### 阶段一：最小可用版

目标：用户上传 docx / tex 后，聊天界面可以看到辅助报告并下载 Markdown。

实现内容：

1. 升级 `chat.paper_format_check.system`。
2. 新增 `Review Evidence Pack` 构建函数。
3. 让 `paper_format_report` 包含 `review_evidence_pack`。
4. 让模型输出 `markdown_report`。
5. 新增 Markdown 报告生成器。
6. 把 Markdown 保存到对象存储。
7. 在返回 payload 中加入 `report_files`。
8. 前端展示“下载 Markdown”。

不做：

```text
PDF 严格版面分析
Word 导出
PDF 导出
学校模板严格比对
工具库工具化
```

### 阶段二：工具库可管理版

目标：让论文查非工具出现在工具库页面，支持版本、状态、绑定和执行记录。

实现内容：

1. 新增 `builtin/paper_format_tools.py`。
2. 加入 `ToolSyncService.BUILTIN_MODULES`。
3. 执行 `/tools/sync/builtin`。
4. 工具库页面展示 `file.paper_format_check`。
5. 可选记录 ToolExecution。

### 阶段三：多格式报告版

目标：支持 Markdown / Word / PDF 三种下载。

实现内容：

1. `build_docx_report()`。
2. `build_pdf_report()`。
3. 对象存储保存多格式文件。
4. 前端展示多个下载按钮。

### 阶段四：模板严格校验版

目标：支持毕业论文模板规范检查。

实现内容：

1. 模板规则库。
2. 模板上传 / 选择。
3. 按模板生成差异检查。
4. 报告中区分：
   - 规则确定问题
   - 模板差异问题
   - 需人工复核项

---

## 15. 关键数据结构

### 15.1 RuleIssue

```json
{
  "code": "structure.abstract_missing",
  "title": "缺少摘要",
  "severity": "high",
  "category": "structure",
  "message": "文档中未识别到“摘要”部分。",
  "evidence": "未找到标题或段落“摘要”",
  "location": {
    "section": "abstract"
  },
  "suggestion": "补充中文摘要并按模板放在前置部分。"
}
```

### 15.2 AiReviewOutput

```json
{
  "answer": "已完成论文查非辅助审阅，发现 8 个问题，建议优先修改摘要、参考文献和标题层级。",
  "summary": "发现 8 个格式与规范问题，其中 2 个高优先级。",
  "markdown_report": "# 论文查非与格式审阅辅助报告\n\n...",
  "issues": [],
  "download_title": "论文查非辅助报告"
}
```

### 15.3 ReportFile

```json
{
  "format": "md",
  "file_name": "论文查非辅助报告.md",
  "bucket": "chat-reports",
  "object_key": "org/user/session/message/论文查非辅助报告.md",
  "url": "/chat/files/chat-reports/org/user/session/message/论文查非辅助报告.md",
  "content_type": "text/markdown"
}
```

---

## 16. 最终返回给前端的建议 payload

```json
{
  "answer": "已完成论文查非辅助审阅，发现 8 个问题。你可以查看下方报告摘要，也可以下载完整 Markdown 报告。",
  "summary": "论文查非完成，发现 8 个问题。",
  "message_type": "file_answer",
  "status": "completed",
  "paper_format_report": {
    "score": 76,
    "issue_count": 8,
    "high_count": 2,
    "medium_count": 4,
    "low_count": 2,
    "summary": "发现结构完整性和格式规范问题。",
    "issues": [],
    "limitations": [],
    "report_files": [
      {
        "format": "md",
        "file_name": "论文查非辅助报告.md",
        "url": "/chat/files/chat-reports/..."
      }
    ]
  },
  "ui_schema": "paper_review_report_v1"
}
```

---

## 17. 需要注意的问题

### 17.1 不要让大模型直接替代规则检查

错误做法：

```text
全文丢给模型
↓
让模型自己判断格式是否合规
```

问题：

```text
成本高
不稳定
容易编造模板要求
难以解释
难以复现
```

推荐做法：

```text
规则检查器先产出 issues
↓
模型只负责审阅表达和修改建议
```

### 17.2 没有模板时必须说明限制

如果用户没有选择学校模板，报告中必须写：

```text
未指定严格模板，当前仅按通用论文规范进行辅助检查，不能代替学校模板终审。
```

### 17.3 PDF 初期不要承诺严格版面检查

如果 PDF 只做文本抽取，必须说明：

```text
当前 PDF 检查主要基于文本抽取，不能完整判断字号、页边距、行距等版面格式。
```

### 17.4 报告是辅助报告，不是正式检测结果

界面和报告都应写清：

```text
本报告为聊天页辅助审阅结果，不会写入正式质检任务或结果表。
```

---

## 18. 结论

推荐把论文查非功能设计为：

```text
规则检查 + 证据组织 + Ai-Review Prompt + 报告生成 + 前端下载
```

其中：

```text
paper_format_checker
负责客观检查。

Review Evidence Pack
负责把检查结果整理成可被模型稳定消费的证据。

Ai-Review Prompt
负责生成专业审阅意见和 Markdown 报告。

Report Builder
负责将报告保存为 Markdown / Word / PDF。

前端
负责展示辅助报告卡片和下载按钮。
```

第一阶段最重要的不是一次性做完整查重系统，而是尽快打通：

```text
上传论文
↓
识别 paper_format_check
↓
规则检查
↓
模型生成 Markdown 报告
↓
界面展示下载
```

这样既能复用当前 `new_tgg` 已有代码，又能快速形成用户可感知的论文辅助审阅能力。
