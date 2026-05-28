# 论文查非高效率实现方案（规则化检查 + 模型审阅 + 模板指南 RAG）

## 1. 文档目标

本文档用于指导当前仓库 `new_tgg / develop` 分支中的论文查非能力升级，目标是实现一个更高效率、更稳定、更可追溯的论文查非流程。

核心原则：

1. 去掉论文查非过程中的不必要模型总结调用。
2. 扩展规则判断，使其从“基础格式检查”升级为“模板驱动的论文格式审查”。
3. 增强 DOCX/PDF 解析能力，减少误判和漏判。
4. 将模板写作指南做成规则条款索引：元数据进入 MySQL，向量进入 Qdrant。
5. 不保留兜底策略：模型失败后直接向前端返回错误。
6. 模型只处理：规则化报告解释、AI Review 风格生成、RAG 检索到的模板指南条款，不直接自由判断整篇论文。

***

## 2. 当前流程的问题

### 2.1 论文查非多了一次不必要的模型总结

当前 `FileExecutor.execute()` 在文件处理流程中会统一调用 `_try_chat_summary()`。对于普通文件问答或文件总结，这一步是合理的；但对于论文查非并不合理。

论文查非已经有明确流程：

```text
上传文件
→ 解析文件
→ 规则检查
→ 构造 Evidence Pack
→ 模型生成 AI Review 报告
→ 返回前端
```

如果在规则检查前后再调用一次普通文件总结模型，会造成：

- 多一次 LLM 调用；
- 多一段无用 token 消耗；
- 总耗时增加；
- 结果链路变复杂；
- 论文查非主结果和普通总结结果之间职责混乱。

#### 处理策略

论文查非路径直接跳过 `_try_chat_summary()`。

伪代码：

```python
model_summary = None

if step.capability_key != "file.paper_format_check":
    model_summary = await self._try_chat_summary(
        parsed_files,
        state,
        request,
        db_session=db_session,
    )
```

论文查非的最终解释只由 `paper_review_ai.py` 的 Ai-Review 模型生成，不再由文件总结模型生成。

***

### 2.2 规则判断不全面

当前规则主要覆盖：

- 是否存在摘要；
- 是否存在关键词；
- 是否存在参考文献；
- 标题层级是否跳变；
- 图题是否可能缺失；
- 页边距是否异常；
- 正文字体、字号、行距是否与模板不一致；
- 连续空格；
- 全角英文或数字；
- 中英文标点混用；
- LanguageTool 辅助检查。

这些规则只能算“基础格式 / 文字规范检查”，还不能支撑完整毕业论文格式审查。

#### 需要补齐的规则类别

| 类别    | 规则方向                         | 说明                           |
| ----- | ---------------------------- | ---------------------------- |
| 结构完整性 | 封面、声明、中英文摘要、目录、正文、参考文献、致谢、附录 | 按学校模板判断必需模块是否存在              |
| 标题体系  | 一级、二级、三级标题编号、层级跳变、标题末尾标点     | 判断章节结构是否规范                   |
| 页面版式  | 页面尺寸、页边距、页眉、页脚、页码、奇偶页        | 需要 DOCX/PDF 版式数据支持           |
| 正文格式  | 中文字体、英文字体、字号、行距、首行缩进、段前段后    | 当前已有部分，但需要更细                 |
| 摘要关键词 | 中文摘要、英文摘要、关键词数量、分隔符、格式       | 需要单独规则                       |
| 图表公式  | 图题、表题、公式编号、编号连续性、图表题位置       | 当前只做非常粗略判断                   |
| 参考文献  | 文末格式、正文引用、引用编号连续性、正文与文末对应关系  | 需要重点增强                       |
| 引用规范  | 是否存在未引用文献、正文引用缺失文末条目         | 可用规则 + 正则初步完成                |
| 附录/成果 | 附录、攻读学位期间成果等学校模板要求           | 按模板配置                        |
| 文字规范  | 错别字、标点、空格、英文大小写、术语统一         | 可以规则 + LanguageTool + 模型辅助解释 |

***

### 2.3 DOCX/PDF 解析能力限制明显

当前 DOCX 解析主要依赖 `python-docx`，能够获取段落文本、样式名、部分 run 字体、字号、段落行距、页边距等信息。但 Word 中很多格式来自样式继承，`run.font.name` 为空不代表字体不存在。因此当前解析结果可能出现：

- 字体识别不全；
- 字号识别不全；
- 样式继承未展开；
- 标题样式误识别；
- 表格内容、脚注、页眉页脚、目录页码解析不足。

PDF 当前主要是文本抽取，无法可靠判断：

- 字体；
- 字号；
- 坐标；
- 行距；
- 页边距；
- 图表位置；
- 页眉页脚；
- 页面版式。

因此 PDF 只能做辅助检查，严格格式检查应优先使用 DOCX。

***

## 3. 目标架构

升级后的论文查非架构如下：

```text
用户上传 DOCX / PDF / TEX
        │
        ▼
文件解析层
        │
        ├─ DOCX：结构、样式、表格、页眉页脚、脚注、目录、引用
        ├─ PDF：文本、字体、字号、坐标、页面布局、图表区域
        └─ TEX：命令、章节、参考文献、图表环境
        │
        ▼
模板规则加载层
        │
        ├─ MySQL：模板、条款、规则元数据、适用对象
        └─ Qdrant：模板条款向量索引
        │
        ▼
规则引擎层
        │
        ├─ 结构规则
        ├─ 样式规则
        ├─ 图表公式规则
        ├─ 参考文献规则
        ├─ 文字规范规则
        └─ 模板差异规则
        │
        ▼
规则化报告 Evidence Pack
        │
        ├─ document
        ├─ outline
        ├─ issues
        ├─ expected / actual
        ├─ evidence_snippets
        ├─ style_summary
        ├─ parser_confidence
        └─ related_template_clauses
        │
        ▼
RAG 检索模板指南相关条款
        │
        ▼
AI Review 模型
        │
        ├─ 只解释规则结果
        ├─ 只引用 Evidence Pack 和模板条款
        ├─ 不重新自由判断整篇论文
        └─ 不编造模板要求
        │
        ▼
最终审阅报告
        │
        ├─ Markdown
        ├─ DOCX
        └─ 前端结构化展示
```

***

## 4. 关键实现点一：去掉多余模型总结

### 4.1 修改位置

建议修改：

```text
backend/agent/router/executors/file_executor.py
```

当前逻辑中，`model_summary = await self._try_chat_summary(...)` 对论文查非也会执行。

### 4.2 修改方案

论文查非跳过普通文件总结模型：

```python
model_summary = None

if step.capability_key != "file.paper_format_check":
    model_summary = await self._try_chat_summary(
        parsed_files,
        state,
        request,
        db_session=db_session,
    )
```

### 4.3 预期收益

- 论文查非少一次模型调用；
- 降低延迟；
- 降低 token 成本；
- 降低模型失败概率；
- 减少前端等待时间；
- 职责更清晰：文件总结模型不参与论文查非。

***

## 5. 关键实现点二：增强规则判断

### 5.1 规则结构设计

建议将规则从硬编码函数逐步升级为“模板规则配置 + 规则执行器”。

规则对象建议如下：

```json
{
  "rule_code": "template.body.font",
  "template_id": "cqupt_graduate_thesis_2022",
  "category": "style",
  "target": "body_paragraph",
  "severity": "medium",
  "expected": {
    "zh_font": "宋体",
    "en_font": "Times New Roman",
    "font_size_pt": 12,
    "line_spacing": 1.5
  },
  "check_type": "style_compare",
  "source_clause_ids": ["cqupt_2022_clause_0032"]
}
```

### 5.2 Issue 输出结构

规则引擎输出的 issue 不应只有 `title/message/evidence/suggestion`，还应包含：

```json
{
  "code": "template.body.font_mismatch",
  "title": "正文字体或字号与模板不一致",
  "severity": "medium",
  "category": "template",
  "location": {
    "section_title": "第 2 章 相关技术",
    "paragraph_index": 35,
    "paragraph_no": 3,
    "display_text": "第2章《相关技术》下第3段"
  },
  "expected": {
    "zh_font": "宋体",
    "en_font": "Times New Roman",
    "font_size_pt": 12
  },
  "actual": {
    "font_name": "Calibri",
    "font_size_pt": 10.5
  },
  "evidence": "该段落的实际文本片段",
  "parser_confidence": "high",
  "source_rule": "template.body.font",
  "source_clause_ids": ["cqupt_2022_clause_0032"],
  "suggestion": "按模板统一正文字体和字号。"
}
```

### 5.3 优先补充的规则

#### 5.3.1 结构规则

- `structure.cover_missing`
- `structure.originality_statement_missing`
- `structure.authorization_statement_missing`
- `structure.cn_abstract_missing`
- `structure.en_abstract_missing`
- `structure.cn_keywords_missing`
- `structure.en_keywords_missing`
- `structure.toc_missing`
- `structure.references_missing`
- `structure.acknowledgement_missing`
- `structure.appendix_missing_if_required`

#### 5.3.2 标题规则

- `heading.level_jump`
- `heading.numbering_missing`
- `heading.numbering_discontinuous`
- `heading.trailing_punctuation`
- `heading.font_mismatch`
- `heading.alignment_mismatch`
- `heading.spacing_mismatch`

#### 5.3.3 正文规则

- `body.font_mismatch`
- `body.font_size_mismatch`
- `body.line_spacing_mismatch`
- `body.first_line_indent_mismatch`
- `body.space_before_after_mismatch`
- `body.alignment_mismatch`

#### 5.3.4 图表公式规则

- `figure.caption_missing`
- `figure.caption_position_mismatch`
- `figure.numbering_discontinuous`
- `table.caption_missing`
- `table.caption_position_mismatch`
- `table.numbering_discontinuous`
- `formula.numbering_missing`
- `formula.numbering_discontinuous`

#### 5.3.5 参考文献规则

- `references.section_missing`
- `references.format_mismatch`
- `references.numbering_discontinuous`
- `references.unused_reference`
- `references.citation_missing_in_bibliography`
- `references.bibliography_missing_for_citation`

#### 5.3.6 文字规范规则

- `text.fullwidth_ascii`
- `text.multiple_spaces`
- `text.mixed_punctuation`
- `text.cn_en_space_mismatch`
- `text.repeated_punctuation`
- `text.suspicious_typo`
- `text.abstract_too_short`
- `text.keywords_count_invalid`

***

## 6. 关键实现点三：增强 DOCX/PDF 解析

### 6.1 DOCX 解析增强

建议新增或增强：

```text
backend/agent/tools/file_parsers.py
backend/agent/tools/paper_docx_parser.py
```

#### 6.1.1 样式继承展开

不要只取 `run.font.name`。应合并：

1. run 级别样式；
2. paragraph style；
3. document styles；

输出时增加：

1. theme font；
2. 默认 Normal 样式。

```json
{
  "font_name_raw": "",
  "font_name_resolved": "宋体",
  "font_size_raw": null,
  "font_size_resolved": 12,
  "style_source": "paragraph_style"
}
```

#### 6.1.2 页眉页脚

需要解析：

- 页眉文本；
- 页脚文本；
- 页码字段；
- 奇偶页不同设置；
- 首页不同设置。

输出：

```json
{
  "headers": [
    {
      "section_index": 1,
      "text": "重庆邮电大学硕士学位论文",
      "paragraphs": [...]
    }
  ],
  "footers": [
    {
      "section_index": 1,
      "text": "12",
      "has_page_number_field": true
    }
  ]
}
```

#### 6.1.3 表格解析

需要解析：

- 表格文本；
- 表题；
- 表格位置；
- 表格前后段落；
- 是否三线表可作为后续增强项。

#### 6.1.4 引用与参考文献

通过正文正则初步抽取：

```text
[1]
[1-3]
[1,2]
（作者，年份）
```

输出：

```json
{
  "citations": [
    {
      "raw": "[1]",
      "number": 1,
      "paragraph_index": 88
    }
  ],
  "references": [
    {
      "number": 1,
      "text": "[1] ...",
      "paragraph_index": 210
    }
  ]
}
```

### 6.2 PDF 解析增强

建议新增：

```text
backend/agent/tools/paper_pdf_parser.py
```

使用 PyMuPDF 或 pdfplumber，输出：

```json
{
  "pages": [
    {
      "page_no": 1,
      "width_pt": 595.2,
      "height_pt": 841.8,
      "blocks": [
        {
          "type": "text",
          "text": "摘要",
          "bbox": [72, 80, 120, 100],
          "font": "SimSun",
          "size": 14,
          "is_bold": true
        }
      ]
    }
  ],
  "font_summary": {
    "SimSun": 300,
    "Times New Roman": 150
  },
  "font_size_summary": {
    "12": 500,
    "14": 30
  },
  "layout_summary": {
    "page_size": "A4",
    "estimated_margins": {
      "top": 2.5,
      "bottom": 2.5,
      "left": 3.0,
      "right": 2.5
    }
  }
}
```

PDF 仍然要标注限制：

```text
PDF 格式判断基于坐标和字体抽取结果，可能受 PDF 生成方式影响；严格格式审查建议上传 DOCX。
```

***

## 7. 关键实现点四：模板指南规则条款索引

### 7.1 为什么不能每次传 2 万字指南

写作指南 2 万字每次传入模型会带来：

- prompt 太长；
- 速度慢；
- 成本高；
- 模型可能漏掉关键条款；
- 小格式规则容易被长文本稀释；
- 多次请求重复解析同一指南，浪费计算资源。

因此应改为：

```text
写作指南离线解析
→ 条款切分
→ 元数据存 MySQL
→ 条款内容向量化
→ 向量存 Qdrant
→ 运行时按 issue 检索相关条款
→ 只传相关条款给模型
```

### 7.2 MySQL 表设计

#### 7.2.1 paper\_template

```sql
CREATE TABLE paper_template (
    id VARCHAR(64) PRIMARY KEY,
    template_id VARCHAR(128) NOT NULL UNIQUE,
    template_name VARCHAR(255) NOT NULL,
    school_name VARCHAR(255),
    degree_type VARCHAR(64),
    version VARCHAR(64),
    description TEXT,
    source_bucket VARCHAR(128),
    source_object_key VARCHAR(512),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

#### 7.2.2 paper\_template\_clause

```sql
CREATE TABLE paper_template_clause (
    id VARCHAR(64) PRIMARY KEY,
    template_id VARCHAR(128) NOT NULL,
    clause_id VARCHAR(128) NOT NULL,
    parent_clause_id VARCHAR(128),
    section_title VARCHAR(255),
    clause_title VARCHAR(255),
    clause_text TEXT NOT NULL,
    normalized_text TEXT,
    applies_to JSON,
    rule_codes JSON,
    target_type VARCHAR(64),
    category VARCHAR(64),
    severity VARCHAR(32),
    page_no INT,
    paragraph_index INT,
    source_file_name VARCHAR(255),
    source_hash VARCHAR(128),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uq_template_clause (template_id, clause_id)
);
```

#### 7.2.3 paper\_template\_rule

```sql
CREATE TABLE paper_template_rule (
    id VARCHAR(64) PRIMARY KEY,
    template_id VARCHAR(128) NOT NULL,
    rule_code VARCHAR(128) NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    category VARCHAR(64) NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    check_type VARCHAR(64) NOT NULL,
    expected JSON,
    source_clause_ids JSON,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uq_template_rule (template_id, rule_code)
);
```

### 7.3 Qdrant Collection 设计

Collection：

```text
paper_template_clauses
```

向量点 payload：

```json
{
  "template_id": "cqupt_graduate_thesis_2022",
  "clause_id": "cqupt_2022_clause_0032",
  "section_title": "正文格式",
  "clause_title": "正文字体字号要求",
  "category": "style",
  "target_type": "body_paragraph",
  "rule_codes": [
    "template.body.font_mismatch",
    "template.body.font_size_mismatch"
  ],
  "severity": "medium",
  "source_file_name": "writing-guide.docx"
}
```

向量文本建议：

```text
section_title + clause_title + normalized_text + rule_codes + target_type
```

### 7.4 条款切分策略

写作指南 DOCX 解析后，按以下规则切分：

1. 优先按标题层级切分；
2. 标题下短段落合并为一个 clause；
3. 表格中的格式要求转成结构化 clause；
4. 每个 clause 绑定 `section_title`、`target_type`、`category`；
5. 用规则抽取或模型离线抽取生成 `expected`；
6. 每个 clause 生成稳定 `clause_id`。

示例：

```json
{
  "clause_id": "cqupt_2022_body_font",
  "section_title": "正文格式",
  "clause_title": "正文字体字号",
  "target_type": "body_paragraph",
  "category": "style",
  "rule_codes": [
    "template.body.font_mismatch",
    "template.body.font_size_mismatch"
  ],
  "clause_text": "正文中文采用宋体，英文采用 Times New Roman，字号为小四。",
  "expected": {
    "zh_font": "宋体",
    "en_font": "Times New Roman",
    "font_size_pt": 12
  }
}
```

### 7.5 模板导入流程

新增工具或服务：

```text
backend/agent/tools/paper_template_indexer.py
backend/app/services/paper_template_index_service.py
```

导入流程：

```text
读取模板写作指南 DOCX
→ parse_docx_bytes
→ 提取标题、段落、表格
→ 切分 clause
→ 规则化 expected
→ 写入 MySQL
→ 调 embedding
→ 写入 Qdrant
→ 返回索引统计
```

返回结果：

```json
{
  "template_id": "cqupt_graduate_thesis_2022",
  "clause_count": 128,
  "rule_count": 42,
  "qdrant_points": 128,
  "status": "success"
}
```

***

## 8. 关键实现点五：取消兜底策略，模型失败直接报错

### 8.1 当前问题

当前模型调用失败时，代码倾向于返回 fallback output，例如：

```json
{
  "model_used": false,
  "limitations": ["Ai-Review 模型调用失败：..."]
}
```

这会让前端看起来像“成功返回了一个不完整结果”。但论文查非如果定义为“必须经过 AI Review 生成最终报告”，那么模型失败就应该是失败。

### 8.2 新原则

论文查非链路必须满足：

```text
规则检查成功 + 模型成功 = 成功
规则检查成功 + 模型失败 = 失败
规则检查失败 = 失败
模板指南 RAG 失败 = 失败或按配置失败
报告生成失败 = 失败
```

不要把失败写进 `limitations` 当成成功返回。

### 8.3 后端错误结构

统一返回：

```json
{
  "status": "failed",
  "message_type": "error",
  "error_code": "paper_review_model_failed",
  "error_message": "Ai-Review 模型调用失败：xxx",
  "ui_schema": "paper_review_error_v1"
}
```

### 8.4 paper\_review\_ai.py 修改

新增异常类：

```python
class PaperReviewModelError(RuntimeError):
    pass
```

模型配置缺失、模型选择失败、模型调用失败、模型输出 JSON 不合法，都直接抛错：

```python
if db_session is None:
    raise PaperReviewModelError("未传入数据库会话，无法读取模型配置。")

if not runtime:
    raise PaperReviewModelError("未找到可用的聊天模型配置。")

try:
    response = await client.chat(...)
except Exception as exc:
    raise PaperReviewModelError(f"Ai-Review 模型调用失败：{exc}") from exc

normalized = normalize_ai_review_output(response)
if not normalized.get("markdown_report"):
    raise PaperReviewModelError("Ai-Review 返回内容缺少 markdown_report。")
```

删除或禁用 `_fallback_output()`。

### 8.5 paper\_review\_enrichment\_service.py 修改

不再吞异常：

```python
except Exception as exc:
    logger.exception(
        "paper review enrichment failed session_id=%s assistant_message_id=%s",
        request.session_id,
        request.assistant_message_id,
    )
    raise
```

### 8.6 是否保留异步增强

如果前端要求“模型失败直接报错”，推荐将 AI Review 从后台异步增强改为论文查非主流程的一部分。

推荐新流程：

```text
file.paper_format_check
    ├─ parse
    ├─ rule check
    ├─ retrieve guide clauses
    ├─ model review
    ├─ report build
    └─ return final response
```

不推荐：

```text
先返回规则结果
后台异步生成 AI Review
失败后再 patch 错误
```

因为这会导致前端体验割裂：用户先看到成功，后又变失败。

***

## 9. 关键实现点六：模型只处理规则化报告解释 + AI Review 风格 + RAG 模板指南

### 9.1 模型职责边界

模型不负责：

- 直接读取原始 DOCX/PDF 判断格式；
- 自己判断字号、行距、页边距；
- 自己从 2 万字模板指南里找所有规则；
- 自由扩展不存在的学校要求；
- 编造参考文献结论；
- 编造未检测到的问题。

模型只负责：

- 根据规则化 issues 解释问题；
- 根据 evidence 组织审阅报告；
- 根据 RAG 检索到的模板条款说明依据；
- 给出修改优先级；
- 输出 AI Review 风格的结构化 JSON 和 Markdown 报告。

### 9.2 模型输入结构

最终传给模型的输入建议：

```json
{
  "task": {
    "type": "paper_format_ai_review",
    "language": "zh-CN",
    "output_format": "json"
  },
  "document": {
    "file_name": "论文.docx",
    "document_type": "docx",
    "template_id": "cqupt_graduate_thesis_2022",
    "word_count": 12000,
    "page_count": 56
  },
  "rule_report": {
    "score": 82,
    "issue_count": 8,
    "high_count": 2,
    "medium_count": 4,
    "low_count": 2,
    "issues": [
      {
        "code": "template.body.line_spacing_mismatch",
        "severity": "medium",
        "category": "template",
        "location": "第2章《相关技术》下第3段",
        "expected": {
          "line_spacing": 1.5
        },
        "actual": {
          "line_spacing": 1.0
        },
        "evidence": "段落文本片段",
        "parser_confidence": "high",
        "source_clause_ids": ["cqupt_2022_body_line_spacing"]
      }
    ]
  },
  "retrieved_template_clauses": [
    {
      "clause_id": "cqupt_2022_body_line_spacing",
      "title": "正文行距要求",
      "text": "正文应采用指定行距……",
      "score": 0.86
    }
  ],
  "style_summary": {
    "font_names": ["宋体", "Times New Roman", "Calibri"],
    "font_sizes": [10.5, 12],
    "line_spacing_values": [1.0, 1.5]
  },
  "limitations": [
    "PDF 当前仅做文本抽取与结构辅助检查，不做严格版式比对。"
  ]
}
```

### 9.3 模型 Prompt 约束

系统提示词应强调：

```text
你是论文格式与规范审阅助手。
你只能基于 rule_report、evidence、retrieved_template_clauses 生成审阅报告。
规则引擎已经完成客观判断，你不需要重新判断论文是否违规。
不得编造模板条款。
不得新增没有证据支撑的问题。
没有证据支撑的问题必须拒绝输出。
输出必须是 JSON。
```

建议输出：

```json
{
  "answer": "不超过200字总结",
  "summary": "一句话结论",
  "markdown_report": "完整 Markdown 报告",
  "issues": [
    {
      "code": "template.body.line_spacing_mismatch",
      "title": "正文行距与模板不一致",
      "severity": "medium",
      "location": "第2章《相关技术》下第3段",
      "evidence": "段落文本片段",
      "template_basis": "正文应采用指定行距……",
      "impact": "影响论文排版一致性和模板合规性",
      "suggestion": "将该段及同类正文段落统一调整为 1.5 倍行距",
      "need_human_review": false
    }
  ],
  "limitations": [],
  "download_title": "论文查非与格式审阅报告"
}
```

***

## 10. 推荐模块改造清单

### 10.1 修改现有文件

| 文件                                                        | 修改内容                                                                 |
| --------------------------------------------------------- | -------------------------------------------------------------------- |
| `backend/agent/router/executors/file_executor.py`         | 跳过论文查非的 `_try_chat_summary()`；把 AI Review 纳入主流程；构造新的 Evidence Pack   |
| `backend/agent/tools/paper_format_checker.py`             | 扩展规则；issue 增加 expected/actual/source\_clause\_ids/parser\_confidence |
| `backend/agent/tools/file_parsers.py`                     | 拆分 DOCX/PDF/TEX 解析；保留统一入口                                            |
| `backend/agent/tools/paper_review_ai.py`                  | 删除 fallback；模型失败直接抛异常；严格校验模型输出                                       |
| `backend/app/services/paper_review_enrichment_service.py` | 如果保留该服务，则不吞异常；推荐改为同步主流程                                              |
| `backend/agent/tools/paper_review_evidence.py`            | Evidence Pack 改为规则化报告 + RAG 条款                                       |
| `backend/agent/tools/paper_template_evidence.py`          | 不再返回 `text[:12000]`；改为按 issue 检索相关条款                                 |

### 10.2 新增文件

| 文件                                                     | 作用                   |
| ------------------------------------------------------ | -------------------- |
| `backend/agent/tools/paper_docx_parser.py`             | 增强 DOCX 解析           |
| `backend/agent/tools/paper_pdf_parser.py`              | 增强 PDF 解析            |
| `backend/agent/tools/paper_template_indexer.py`        | 写作指南条款切分与索引          |
| `backend/app/services/paper_template_index_service.py` | 模板条款入 MySQL + Qdrant |
| `backend/app/models/paper_template.py`                 | MySQL ORM 模型         |
| `backend/app/repositories/paper_template_repo.py`      | 模板和条款仓储              |
| `backend/agent/rag/paper_template_clause_retriever.py` | Qdrant 检索模板条款        |
| `backend/app/api/v1/paper_templates.py`                | 模板导入、重建索引、查询接口       |

***

## 11. 新论文查非主流程伪代码

```python
async def run_paper_format_check(step, state, request, db_session):
    # 1. 读取附件
    file_bytes = read_attachment_bytes(...)

    # 2. 解析文件
    parsed = parse_file_content(file_name, file_bytes)

    # 3. 加载模板规则
    template_rules = await PaperTemplateRuleService(db_session).load_rules(template_id)

    # 4. 规则检查
    rule_report = check_paper_format(
        parsed=parsed,
        file_name=file_name,
        query=state.original_query,
        template_id=template_id,
        template_rules=template_rules,
    )

    # 5. 如果规则检查本身失败，直接抛错
    if rule_report.get("status") == "failed":
        raise PaperReviewError(rule_report.get("error_message"))

    # 6. 根据 issues 检索相关模板条款
    related_clauses = await PaperTemplateClauseRetriever().retrieve_for_issues(
        template_id=template_id,
        issues=rule_report["issues"],
        top_k=8,
    )

    # 7. 构造模型输入
    evidence_pack = build_review_evidence_pack(
        parsed=parsed,
        check_result=rule_report,
        file_name=file_name,
        related_template_clauses=related_clauses,
    )

    # 8. 调用模型
    ai_review_output = await generate_ai_review_output(
        evidence_pack=evidence_pack,
        query=state.original_query,
        db_session=db_session,
        org_id=request.org_id,
        trace_id=state.trace_id,
        task_id=state.session_id,
    )

    # 9. 生成报告
    report_files = await save_report_files(
        ai_review_output=ai_review_output,
        evidence_pack=evidence_pack,
    )

    # 10. 返回前端
    return {
        "status": "completed",
        "score": rule_report["score"],
        "issues": rule_report["issues"],
        "ai_review_output": ai_review_output,
        "report_files": report_files,
        "ui_schema": "paper_review_report_v1",
    }
```

***

## 12. 前端交互建议

### 12.1 成功状态

```json
{
  "message_type": "file_answer",
  "status": "completed",
  "ui_schema": "paper_review_report_v1",
  "paper_format_report": {
    "score": 82,
    "issue_count": 8,
    "high_count": 2,
    "medium_count": 4,
    "low_count": 2,
    "summary": "发现 8 个格式与规范问题。",
    "issues": [],
    "ai_review_output": {},
    "report_files": []
  }
}
```

### 12.2 失败状态

```json
{
  "message_type": "error",
  "status": "failed",
  "ui_schema": "paper_review_error_v1",
  "error_code": "paper_review_model_failed",
  "error_message": "Ai-Review 模型调用失败：模型服务超时。"
}
```

前端不应展示“部分成功”的报告。

***

## 13. 性能优化点

### 13.1 去掉一次 LLM 调用

论文查非跳过 `_try_chat_summary()`。

### 13.2 模板指南预索引

模板指南只在导入或更新时解析和向量化，不在每次论文查非时全文解析。

### 13.3 RAG 按 issue 检索

不检索整篇指南，只按 issue code、category、target\_type、evidence 查询相关条款。

### 13.4 缓存规则检查结果

缓存键：

```text
file_sha256 + template_id + rule_version + parser_version
```

缓存内容：

- parsed document；
- rule\_report；
- style\_summary；
- evidence snippets。

### 13.5 缓存 AI Review 结果

缓存键：

```text
rule_report_hash + retrieved_clause_ids + prompt_version + model_id
```

如果同一论文、同一模板、同一规则版本重复检查，可以直接返回已有报告。

### 13.6 控制模型输入大小

建议模型输入限制：

| 内容                | 限制                         |
| ----------------- | -------------------------- |
| issues            | 高优先级全部 + 中优先级前 10 + 低优先级摘要 |
| evidence          | 每个 issue 300 字以内           |
| retrieved clauses | 5 到 10 条                   |
| 每条 clause         | 500 字以内                    |
| 总 prompt          | 尽量控制在 8k tokens 内          |

***

## 14. 验收标准

### 14.1 效率验收

- 论文查非流程不再调用普通文件总结模型；
- 单篇 DOCX 检查只调用一次 AI Review 模型；
- 模板指南不再每次全文传入模型；
- 同一模板指南导入后可复用 MySQL/Qdrant 索引；
- 相同文件重复检查可命中缓存。

### 14.2 准确性验收

- issue 中必须包含 `expected` 和 `actual`；
- issue 必须有明确位置；
- issue 必须有证据片段；
- 模型报告中的问题必须能追溯到 rule issue；
- 模型报告中的模板依据必须来自 RAG 检索到的 clause；
- 模型不得新增无证据问题。

### 14.3 错误处理验收

- 模型配置缺失时，前端显示失败；
- 模型调用超时时，前端显示失败；
- 模型返回 JSON 不合法时，前端显示失败；
- 报告生成失败时，前端显示失败；
- 不再把模型失败写入 limitations 当成成功结果。

### 14.4 模板索引验收

- 写作指南可被切分为 clause；
- clause 元数据写入 MySQL；
- clause 向量写入 Qdrant；
- 根据 issue 能检索到相关条款；
- 检索结果能进入 Evidence Pack；
- 模型输出能引用 clause 内容。

***

## 15. 推荐分阶段实施

### 第一阶段：效率与失败策略修正

目标：快速解决最明显问题。

- 跳过 `_try_chat_summary()`；
- 删除 Ai-Review fallback；
- 模型失败直接抛错；
- 前端接收 `paper_review_error_v1`；
- AI Review 改为主流程，减少异步补丁式体验。

### 第二阶段：Evidence Pack 标准化

目标：让模型只解释规则化结果。

- issue 增加 expected/actual；
- issue 增加 parser\_confidence；
- issue 增加 source\_clause\_ids；
- Evidence Pack 改为 `rule_report + retrieved_template_clauses`；
- Prompt 强制模型不得新增无证据问题。

### 第三阶段：模板指南索引

目标：替代 2 万字全文传入。

- 建 MySQL 表；
- 建 Qdrant collection；
- 写模板导入服务；
- 写 clause retriever；
- 模型输入只带相关条款。

### 第四阶段：规则扩展

目标：从基础检查变为模板审查。

- 扩展结构规则；
- 扩展标题规则；
- 扩展正文规则；
- 扩展图表公式规则；
- 扩展参考文献规则；
- 扩展摘要关键词规则。

### 第五阶段：DOCX/PDF 解析增强

目标：减少误判漏判。

- DOCX 样式继承展开；
- DOCX 表格、页眉页脚、脚注解析；
- PDF 字体、字号、坐标解析；
- PDF 页面布局估算；
- 解析结果增加 confidence。

***

## 16. 最终推荐结论

推荐将论文查非定义为一个严格流程：

```text
规则引擎负责判断
RAG 负责提供模板条款依据
模型负责解释和生成 AI Review 报告
前端负责展示成功或明确失败
```

不要让模型直接判断整篇论文，也不要让模型失败后返回兜底报告。

最终高效链路应为：

```text
上传文件
→ 解析结构和样式
→ 加载模板规则
→ 规则检查
→ 根据问题检索模板条款
→ 构造 Evidence Pack
→ 单次 AI Review 模型调用
→ 生成报告
→ 前端展示
```

这样可以同时提升：

- 响应速度；
- 模型稳定性；
- 格式判断准确性；
- 报告可追溯性；
- 前端错误表达清晰度；
- 模板复用能力。

