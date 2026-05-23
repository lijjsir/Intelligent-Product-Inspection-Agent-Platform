"""Built-in web search tool manifest and handler."""

from __future__ import annotations

import re

TOOL_MANIFESTS = [
    {
        "tool_key": "web.search",
        "display_name": "联网搜索",
        "description": "提取用户问题中的核心关键词（仅名词/实体名，去掉语气词、疑问词、动词），通过 DuckDuckGo 检索互联网公开信息。query 参数只传空格分隔的关键词，不要传完整问句。",
        "tool_type": "native",
        "category": "search",
        "handler_path": "agent.tools.builtin.search_tools.search",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "核心搜索关键词（仅名词/实体名/专有名词，空格分隔，不超过 20 字）。示例：用户问'张雪峰现在怎么样了' → 传 '张雪峰 近况 去世'",
                },
                "max_results": {"type": "integer", "default": 5, "description": "返回结果数量（1-10）"},
                "region": {"type": "string", "default": "cn-zh", "description": "搜索区域/语言偏好"},
            },
            "required": ["query"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "results": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}, "snippet": {"type": "string"}}}},
                "query": {"type": "string"},
                "total": {"type": "integer"},
                "keywords": {"type": "string", "description": "实际使用的搜索关键词"},
            },
        },
        "risk_level": "low",
        "is_readonly": True,
    },
]

# ── Keyword extraction: strip question/stop patterns from Chinese text ──
_CLEAN_PATTERNS = [
    # Question suffixes
    re.compile(r"怎么样了"), re.compile(r"怎么样"), re.compile(r"是什么"),
    re.compile(r"为什么"), re.compile(r"怎么回事"), re.compile(r"如何"),
    # Modal/tense markers
    re.compile(r"现在"), re.compile(r"目前"), re.compile(r"最近"), re.compile(r"当前"),
    re.compile(r"了没有"), re.compile(r"了吗"), re.compile(r"了没"), re.compile(r"没"),
    re.compile(r"是不是"), re.compile(r"能不能"), re.compile(r"可不可以"),
    re.compile(r"有没有"), re.compile(r"会不会"), re.compile(r"应不应该"),
    # Question words
    re.compile(r"哪些"), re.compile(r"什么"), re.compile(r"哪个"), re.compile(r"怎么"),
    re.compile(r"请问"), re.compile(r"帮我"), re.compile(r"给我"), re.compile(r"告诉"),
    re.compile(r"查询"), re.compile(r"搜索"), re.compile(r"查找"),
    re.compile(r"了解"), re.compile(r"知道"), re.compile(r"知道吗"),
    re.compile(r"一下"), re.compile(r"一下吗"),
    # Filler / pronouns / verbs (standalone single chars between spaces)
    re.compile(r"请"), re.compile(r"可以"), re.compile(r"是否"), re.compile(r"还有"),
    re.compile(r"关于"), re.compile(r"有关"), re.compile(r"相关"),
    re.compile(r"他(?=\s|$)"), re.compile(r"她(?=\s|$)"), re.compile(r"它(?=\s|$)"),
    re.compile(r"(^|\s)有(?=\s|$)"), re.compile(r"(^|\s)是(?=\s|$)"), re.compile(r"(^|\s)的(?=\s|$)"),
    re.compile(r"(^|\s)查(?=\s|$)"), re.compile(r"(^|\s)更(?=\s|$)"), re.compile(r"(^|\s)最(?=\s|$)"),
    re.compile(r"(^|\s)了(?=\s|$)"), re.compile(r"(^|\s)没(?=\s|$)"),
    re.compile(r"(^|\s)吗(?=\s|$)"), re.compile(r"(^|\s)呢(?=\s|$)"), re.compile(r"(^|\s)吧(?=\s|$)"),
    # Punctuation
    re.compile(r"[，,。！？?.!！：:；;、'\"''""（）()\\[\\]【】\\s]+"),
]
# Keep these as meaningful content
_KEEP_CHARS = re.compile(r"[^一-龥a-zA-Z0-9+\-.#@_/\s]")


def _extract_keywords(text: str, max_len: int = 60) -> str:
    """Extract core keywords from a Chinese query by stripping noise words."""
    cleaned = text.strip()
    for pat in _CLEAN_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    # Remove non-content characters
    cleaned = _KEEP_CHARS.sub(" ", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Truncate
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rsplit(" ", 1)[0]
    return cleaned or text[:max_len]


async def search(query: str, max_results: int = 5, region: str = "cn-zh") -> dict:
    """Execute a web search via DuckDuckGo with automatic keyword extraction."""
    keywords = _extract_keywords(query)
    search_query = keywords if keywords else query

    DDGS = None
    for mod in ("ddgs", "duckduckgo_search"):
        try:
            DDGS = __import__(mod, fromlist=["DDGS"]).DDGS
            break
        except ImportError:
            continue
    if DDGS is None:
        return {"query": query, "keywords": keywords, "results": [], "total": 0, "error": "ddgs / duckduckgo_search package not installed"}

    max_results = max(1, min(max_results, 10))
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(search_query, region=region, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
    except Exception as exc:
        return {"query": query, "keywords": keywords, "results": [], "total": 0, "error": str(exc)}

    return {
        "query": query,
        "keywords": keywords,
        "results": results,
        "total": len(results),
    }
