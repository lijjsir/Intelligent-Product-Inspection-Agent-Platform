PROMPTS = [
    {
        "key": "shared.evidence_synthesize.system",
        "display_name": "证据合成提示词",
        "description": "将多个检索结果和证据片段合成为统一的证据摘要。",
        "agent_key": "shared",
        "agent_name": "共享能力",
        "stage_key": "evidence_synthesize",
        "stage_name": "证据合成",
        "usage_location": "共享能力 / 证据合成",
        "source_file": "backend/agent/prompts/shared_prompts.py",
        "source_symbol": "shared.evidence_synthesize.system",
        "content": """请将以下多个证据片段合成为统一的证据摘要。

要求：
1. 去重：相同或相似的证据合并。
2. 排序：按相关性和权威性排序。
3. 标注：每条证据标注来源。
4. 冲突处理：如果证据之间存在冲突，说明并标注。
""",
    },
    {
        "key": "shared.citation_format.system",
        "display_name": "引用格式化提示词",
        "description": "将引用信息格式化为统一的引用格式。",
        "agent_key": "shared",
        "agent_name": "共享能力",
        "stage_key": "citation_format",
        "stage_name": "引用格式化",
        "usage_location": "共享能力 / 引用格式化",
        "source_file": "backend/agent/prompts/shared_prompts.py",
        "source_symbol": "shared.citation_format.system",
        "content": """请将以下引用信息格式化为统一格式。

引用格式：`[来源编号] 标准名称 条款编号 原文摘录`

要求：
1. 保持原文内容不变。
2. 补齐缺失的编号信息。
""",
    },
    {
        "key": "shared.rule_conflict.system",
        "display_name": "规则冲突仲裁提示词",
        "description": "当多条标准规则冲突时，进行优先级仲裁。",
        "agent_key": "shared",
        "agent_name": "共享能力",
        "stage_key": "rule_conflict",
        "stage_name": "规则冲突仲裁",
        "usage_location": "共享能力 / 规则冲突仲裁",
        "source_file": "backend/agent/prompts/shared_prompts.py",
        "source_symbol": "shared.rule_conflict.system",
        "content": """当多条标准规则存在冲突时，请按以下优先级仲裁：

1. 国家强制性标准 > 国家推荐性标准 > 行业标准 > 企业标准
2. 最新版本 > 旧版本
3. 具体条款 > 通用条款

对于每条冲突，说明：
- 冲突的规则
- 优先级判断依据
- 最终采用的规则
""",
    },
]
