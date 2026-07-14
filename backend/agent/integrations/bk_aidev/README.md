# bk-aidev-agent capability adoption

This directory contains the low-coupling capabilities adopted from
`TencentBlueKing/bk-aidev-agent` without importing its Django, BlueKing PaaS,
WeCom, BKUI, or full Agent runtime.

## Upstream baseline

- Repository: `https://github.com/TencentBlueKing/bk-aidev-agent`
- Branch inspected: `develop`
- Commit: `decba1152615f4dbd7de8681a0290e0f2c33158e`
- Commit date: `2026-07-10`
- License: MIT; see `LICENSE.upstream.txt`

## Adopted capabilities

- `mcp_client.py`: follows the upstream resource-manager approach by using
  `langchain_mcp_adapters.client.MultiServerMCPClient`, with transport
  selection, retries, timeouts, discovery, tool filtering, and normalized
  results.
- `tool_safety.py`: applies the upstream tool-result limiting and sensitive
  value redaction principles to the existing PIAP `ToolInvoker` and tool test
  path.
- `approval_bridge.py`: maps an upstream-style human-in-the-loop tool block to
  the existing PIAP `ApprovalService` instead of introducing a second approval
  subsystem.
- `context_compression.py`: applies the upstream progressive history reduction
  idea to PIAP prompt construction while retaining PIAP's existing LLM session
  summary service.

## Local storage mapping

MCP tools use the existing schema and require no database migration:

- `ToolDefinition.source_ref`: MCP server URL
- `ToolVersion.endpoint`: MCP server URL
- `ToolVersion.method`: `MCP`
- `ToolVersion.retry_policy.transport`: `streamable_http` or `sse`
- `ToolVersion.retry_policy.mcp_tool_name`: original MCP tool name
- `ToolVersion.retry_policy.retries`: call retry count

Imported tools remain drafts until they are tested, activated, and bound to an
agent through the existing tool-management workflow.
