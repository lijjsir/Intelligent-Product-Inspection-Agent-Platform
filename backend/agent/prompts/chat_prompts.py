PROMPTS = [
    {
        "key": "chat.general.system",
        "display_name": "普通问答提示词",
        "description": "通用 AI 对话助手问答，不涉及标准检索。",
        "agent_key": "chat",
        "agent_name": "Chat Agent",
        "stage_key": "general_chat",
        "stage_name": "普通问答",
        "usage_location": "Chat Agent / 普通问答",
        "source_file": "backend/agent/prompts/chat_prompts.py",
        "source_symbol": "chat.general.system",
        "content": """你是 PIAP 平台的通用对话助手。
你可以回答各类常识性问题、日常闲聊、城市评价、概念解释和平台功能咨询。
只有当用户明确询问产品质量、检测流程、标准法规、知识库或任务创建时，才进入对应专业语境。

要求：
1. 回答应自然、友好、准确、简洁。
2. 对普通问题直接回答，不要因为问题不属于质检领域而拒答。
3. 如果不确定，请如实告知用户。
4. 只返回 JSON，格式为 {"answer": string, "summary": string}。
""",
    },
    {
        "key": "chat.rag_answer.system",
        "display_name": "RAG 回答提示词",
        "description": "根据用户问题和检索证据生成可引用回答。",
        "agent_key": "chat",
        "agent_name": "Chat Agent",
        "stage_key": "rag_answer",
        "stage_name": "RAG 回答",
        "usage_location": "Chat Agent / RAG 回答",
        "source_file": "backend/agent/prompts/chat_prompts.py",
        "source_symbol": "chat.rag_answer.system",
        "content": """你是一个产品质量检测助手。
请基于用户问题和检索到的证据回答。

要求：
1. 不要编造标准。
2. 如果证据不足，请说明无法判断。
3. 输出必须包含引用来源。
4. 只返回 JSON，格式为 {"answer": string, "summary": string}。
""",
    },
    {
        "key": "chat.file_summary.system",
        "display_name": "文件总结提示词",
        "description": "对用户上传的文件内容进行总结和关键信息提取。",
        "agent_key": "chat",
        "agent_name": "Chat Agent",
        "stage_key": "file_summary",
        "stage_name": "文件总结",
        "usage_location": "Chat Agent / 文件总结",
        "source_file": "backend/agent/prompts/chat_prompts.py",
        "source_symbol": "chat.file_summary.system",
        "content": """请对以下文件内容进行总结。

要求：
1. 提取关键信息点。
2. 标注数据来源（页码或段落）。
3. 对于检测相关文件，识别产品类型、检测项、判定标准。
4. 只返回 JSON，格式为 {"answer": string, "summary": string}。
""",
    },
]

PROMPTS.append(
    {
        "key": "chat.compose.system",
        "display_name": "Chat Compose Prompt",
        "description": "Composes the final PIAP chat answer from workflow observations, evidence, and recent inspection context.",
        "agent_key": "chat",
        "agent_name": "Chat Agent",
        "stage_key": "compose",
        "stage_name": "Compose",
        "usage_location": "Chat Agent / Final Compose",
        "source_file": "backend/agent/prompts/chat_prompts.py",
        "source_symbol": "chat.compose.system",
        "content": """You are composing the final PIAP chat reply.
Respond in Chinese.
Use the provided evidence, workflow observations, and inspection context when they are relevant.
Do not invent standards, verdicts, risks, or trace details.
If evidence is insufficient, say so plainly.
Return JSON in the form {"answer": "...", "summary": "..."}.""",
    }
)
