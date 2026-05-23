from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState
from agent.router.node_registry import route_attachment_to_node
from agent.llm.gateway import LLMGateway


class VisionExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        routed = []
        for attachment in state.attachments:
            node = route_attachment_to_node("chat", attachment)
            if node:
                routed.append({"attachment": attachment, "node": node.model_dump()})
        if not routed:
            return observation(step, status="skipped", summary="没有可处理的图片"), []

        model_result = await self._try_multimodal_understanding(routed, state, request, db_session=db_session)
        if model_result is None:
            return (
                observation(
                    step,
                    status="failed",
                    summary="视觉模型不可用，请检查后台视觉模型配置",
                    error="no multimodal/vision model configured",
                ),
                [],
            )
        if isinstance(model_result, dict) and model_result.get("error"):
            return (
                observation(
                    step,
                    status="failed",
                    summary=f"视觉模型调用失败：{model_result['error']}",
                    error=model_result["error"],
                ),
                [],
            )

        art = artifact(
            "image_understanding",
            "vision",
            {
                "objects": model_result.get("objects", []),
                "possible_defects": model_result.get("possible_defects", []),
                "risk": model_result.get("risk", "medium"),
                "informal": True,
                "local_routes": routed,
                "image_count": len(routed),
                "model_result": model_result,
            },
            confidence=0.7,
        )
        return (
            observation(
                step,
                status="success",
                summary=str(model_result.get("summary", "") or "图片理解完成"),
                artifact_ids=[art.artifact_id],
                metrics={"image_count": len(routed)},
            ),
            [art],
        )

    async def _try_multimodal_understanding(self, routed: list[dict], state: ManagerState, request: NormalizedRequest, *, db_session=None):
        if not routed:
            return None
        if db_session is None:
            return {"error": "db_session not available"}
        try:
            from agent.llm.client import LLMClient
            from app.services.object_storage.resolver import attachment_to_data_url
            from app.services.model_config_service import ModelConfigService

            models = await ModelConfigService(db_session, request.org_id).list_runtime_models()
            runtime = await LLMGateway().select_runtime(models=models, model_types={"multimodal", "vision"}, reserve=False)
            if not runtime:
                return {"error": "no multimodal/vision model configured in this org"}
            image_urls = []
            for item in routed:
                attachment = item.get("attachment") or {}
                url = str(attachment.get("url") or "")
                image_urls.append(attachment_to_data_url(attachment) or url)
            client = LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=runtime.get("model_id"),
                provider=runtime.get("provider"),
                org_id=request.org_id,
            )
            state.used_llm_calls += 1
            response = await client.vision_chat(
                "请描述这张图片的内容，识别其中的物体、文字、可能的缺陷或异常。返回 JSON：{\"summary\":\"...\",\"objects\":[],\"possible_defects\":[],\"risk\":\"low|medium|high\"}。",
                image_urls,
            )
            parsed = self._parse_vision_response(response)
            parsed["model_id"] = runtime.get("model_id")
            return parsed
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _parse_vision_response(response: dict) -> dict:
        import json as _json
        content = response.get("content") if isinstance(response, dict) else None
        if isinstance(content, dict):
            return content
        choices = response.get("choices") if isinstance(response, dict) else None
        if isinstance(choices, list) and choices:
            content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            try:
                return _json.loads(content)
            except Exception:
                return {"summary": content[:500]}
        return {"raw": str(response)[:500]}
