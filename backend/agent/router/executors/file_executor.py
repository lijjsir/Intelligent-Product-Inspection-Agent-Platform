from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState
from agent.router.node_registry import route_attachment_to_node
from agent.llm.gateway import LLMGateway


class FileExecutor:
    """Handle ordinary document parsing, summaries, file Q&A and RAG actions."""

    SUPPORTED_CAPABILITIES = {
        "file.summary",
        "file.qa",
        "file.parse",
        "rag.retrieve",
        "rag.ingest",
    }

    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        from agent.tools.file_parsers import parse_file_content
        from app.services.object_storage.resolver import read_attachment_bytes

        cap = step.capability
        if cap in {"rag.retrieve", "rag.ingest"}:
            from agent.router.capability_router import get_capability_router
            from agent.router.contracts import CapabilityContext

            return await get_capability_router().call(
                cap,
                CapabilityContext(step=step, state=state, request=request, db_session=db_session),
            )

        if cap not in self.SUPPORTED_CAPABILITIES:
            from agent.router.errors import make_agent_error

            raise make_agent_error(
                "UNSUPPORTED_CAPABILITY",
                message=f"FileExecutor 不支持能力：{cap}",
                detail={"capability": cap, "executor": "file"},
                source="file.executor",
            )

        parsed_files: list[dict] = []
        unsupported: list[dict] = []
        for attachment in state.attachments:
            node = route_attachment_to_node("chat", attachment)
            if not node:
                unsupported.append(attachment)
                continue
            payload = read_attachment_bytes(attachment)
            if payload is None:
                unsupported.append({**attachment, "reason": "file_not_available"})
                continue
            content, content_type = payload
            try:
                parsed = parse_file_content(str(attachment.get("name") or "attachment.txt"), content)
            except Exception as exc:
                unsupported.append({**attachment, "reason": str(exc)})
                continue
            text = str(parsed.get("text") or "")
            parsed_files.append(
                {
                    "name": str(attachment.get("name") or "attachment"),
                    "url": str(attachment.get("url") or ""),
                    "content_type": content_type,
                    "kind": parsed.get("kind"),
                    "text": text[:12000],
                    "summary": self._summarize_text(text),
                    "metadata": {key: value for key, value in parsed.items() if key != "text"},
                }
            )

        artifact_type = "file_summary" if cap == "file.summary" else "file_answer"
        if not parsed_files:
            if state.attachments:
                from agent.router.errors import make_agent_error

                raise make_agent_error(
                    code="FILE_PARSE_FAILED",
                    message="文件解析失败，无法继续执行文件总结或问答。",
                    detail={"attachment_count": len(state.attachments), "unsupported": unsupported},
                    source=cap,
                )
            art = artifact(
                step,
                artifact_type,
                content={"unsupported": unsupported, "parsed_files": []},
                confidence=0.2,
            )
            return (
                observation(step, status="skipped", summary="没有附件文件", artifact_ids=[art.artifact_id]),
                [art],
            )

        model_summary = await self._try_chat_summary(
            parsed_files, state, request, db_session=db_session
        )
        content = {
            "informal": True,
            "parsed_files": parsed_files,
            "model_summary": model_summary,
            "unsupported": unsupported,
        }
        summary = model_summary or self._compose_summary(parsed_files)
        art = artifact(step, artifact_type, content=content, confidence=0.75)
        return (
            observation(
                step,
                status="success",
                summary=summary,
                artifact_ids=[art.artifact_id],
                metrics={
                    "parsed_file_count": len(parsed_files),
                    "unsupported_count": len(unsupported),
                },
            ),
            [art],
        )

    @staticmethod
    def _summarize_text(text: str) -> str:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return ""
        return cleaned[:500] + ("..." if len(cleaned) > 500 else "")

    def _compose_summary(self, parsed_files: list[dict]) -> str:
        if not parsed_files:
            return "未能解析可用文件内容。"
        return "\n".join(
            f"{item['name']}（{item.get('kind') or 'file'}）：{item.get('summary') or '无文本内容'}"
            for item in parsed_files
        )

    async def _try_chat_summary(
        self,
        parsed_files: list[dict],
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> str | None:
        if not parsed_files:
            return None
        if db_session is None:
            parsed_text = "\n".join(
                f"{item['name']}: {item.get('summary', '')}" for item in parsed_files[:3]
            )
            return parsed_text[:800] if parsed_text else None
        try:
            from agent.llm.client import LLMClient
            from app.services.model_config_service import ModelConfigService

            models = await ModelConfigService(db_session, request.org_id).list_runtime_models()
            runtime = await LLMGateway().select_runtime(
                models=models, model_types={"chat"}, reserve=False
            )
            if not runtime:
                return None
            joined = "\n\n".join(
                f"文件：{item.get('name')}\n内容：{str(item.get('text') or '')[:4000]}"
                for item in parsed_files[:3]
            )
            client = LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=runtime.get("model_id"),
                provider=runtime.get("provider"),
                trace_id=state.trace_id or state.workflow_run_id or state.request_id,
                task_id=state.session_id,
                org_id=request.org_id,
            )
            state.used_llm_calls += 1
            response = await client.chat(
                [
                    {"role": "system", "content": "你是聊天页文件辅助分析节点，只返回 JSON。"},
                    {
                        "role": "user",
                        "content": (
                            "请基于文件内容回答用户问题或总结文件。返回 JSON："
                            "{\"summary\":\"...\",\"answer\":\"...\"}。\n"
                            f"用户问题：{state.original_query}\n{joined}"
                        ),
                    },
                ],
                temperature=0.1,
                observation_name="chat.file_node",
                observation_metadata={"surface": state.surface, "file_count": len(parsed_files)},
            )
            data = self._extract_json(response)
            return str(data.get("answer") or data.get("summary") or "").strip() if data else None
        except Exception:
            return None

    @staticmethod
    def _extract_json(response: dict) -> dict | None:
        import json

        content = response.get("content") if isinstance(response, dict) else None
        if isinstance(content, dict):
            return content
        choices = response.get("choices") if isinstance(response, dict) else None
        if isinstance(choices, list) and choices:
            content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            try:
                return json.loads(content)
            except Exception:
                return None
        return None
