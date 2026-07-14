"""Selected, low-coupling capabilities adopted from bk-aidev-agent."""

from agent.integrations.bk_aidev.context_compression import (
    ContextCompressionStats,
    compress_history,
)
from agent.integrations.bk_aidev.approval_bridge import (
    create_tool_approval,
    decrypt_tool_arguments,
    encrypt_tool_arguments,
)
from agent.integrations.bk_aidev.mcp_client import (
    McpClientAdapter,
    McpClientError,
    McpToolDescriptor,
)
from agent.integrations.bk_aidev.tool_safety import (
    ToolSafetyPolicy,
    configured_tool_safety_policy,
    sanitize_tool_output,
)

__all__ = [
    "ContextCompressionStats",
    "McpClientAdapter",
    "McpClientError",
    "McpToolDescriptor",
    "ToolSafetyPolicy",
    "compress_history",
    "configured_tool_safety_policy",
    "create_tool_approval",
    "decrypt_tool_arguments",
    "encrypt_tool_arguments",
    "sanitize_tool_output",
]
