from __future__ import annotations

import json as _json

from agent.llm.gateway import LLMGateway
from agent.router.contracts import CapabilityContext
from agent.router.errors import make_agent_error
from agent.vision.heuristic_detector import extract_defects
from agent.vision.prompts import VISION_INSPECTION_JSON_PROMPT


class VisionUnderstandingHandler:
    """Image understanding capability handler -- standalone handler with proper error boundaries."""

    async def run(self, context: CapabilityContext):
        from agent.router.executors.base import artifact, observation
        from agent.router.node_registry import route_attachment_to_node

        step = context.step
        state = context.state
        request = context.request
        db_session = context.db_session

        routed = []
        for attachment in state.attachments:
            node = route_attachment_to_node("chat", attachment)
            if node:
                routed.append({"attachment": attachment, "node": node.model_dump()})

        if not routed:
            art = artifact(
                step,
                "image_understanding",
                content={"image_count": 0, "informal": True},
                confidence=0.0,
                status="empty",
                empty_result=True,
                metrics={"images_processed": 0},
            )
            return observation(step, status="skipped", summary="没有可处理的图片", artifact_ids=[art.artifact_id], metrics={"images_processed": 0}), [art]

        model_result = await self._try_multimodal_understanding(routed, state, request, db_session=db_session)
        if model_result is None:
            raise make_agent_error(
                "IMAGE_MODEL_UNAVAILABLE",
                source="image.understanding",
            )
        if isinstance(model_result, dict) and model_result.get("error"):
            raise make_agent_error(
                "IMAGE_MODEL_UNAVAILABLE",
                detail={"error": str(model_result.get("error"))},
                source="image.understanding",
            )

        art = artifact(
            step,
            "image_understanding",
            content={
                "objects": model_result.get("objects", []),
                "possible_defects": model_result.get("possible_defects", []),
                "defects": model_result.get("defects", []),
                "risk": model_result.get("risk", "medium"),
                "informal": True,
                "local_routes": routed,
                "image_count": len(routed),
                "model_result": model_result,
            },
            confidence=0.7,
            metrics={"images_processed": len(routed), "confidence": 0.7},
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

    async def _try_multimodal_understanding(self, routed: list[dict], state, request, *, db_session=None):
        if not routed:
            return None
        if db_session is None:
            return {"error": "db_session not available"}
        try:
            from agent.llm.client import LLMClient
            from app.services.object_storage.resolver import attachment_to_data_url
            from app.services.model_config_service import ModelConfigService

            models = await ModelConfigService(db_session, request.org_id).list_runtime_models()
            runtime = await LLMGateway().select_runtime(models=models, model_types={"multimodal", "vision", "vlm"}, reserve=False)
            if not runtime:
                return {"error": "no multimodal/vision model configured in this org"}
            image_urls = []
            for item in routed:
                attachment = item.get("attachment") or {}
                url = str(attachment.get("url") or "")
                image_urls.append(attachment_to_data_url(attachment) or url)
            detector_result = None
            detector_defects = []
            try:
                from agent.vision.detector_client import VisionDetectorClient

                detector = VisionDetectorClient()
                detector_result = await detector.detect(
                    image_urls=image_urls,
                    product_id=getattr(request, "product_id", None),
                    spec_code=getattr(request, "spec_code", None),
                )
                detector_defects = extract_defects(detector_result, image_count=len(image_urls))
            except Exception as detector_exc:
                detector_result = {"error": str(detector_exc)}
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
            response = await client.vision_chat(
                VISION_INSPECTION_JSON_PROMPT,
                image_urls,
            )
            parsed = self._parse_vision_response(response)
            model_defects = extract_defects(parsed, image_count=len(image_urls))
            parsed["defects"] = detector_defects or model_defects
            if detector_result is not None:
                parsed["detector_result"] = detector_result
            parsed["model_id"] = runtime.get("model_id")
            return parsed
        except Exception as exc:
            raise make_agent_error(
                "IMAGE_UNDERSTANDING_FAILED",
                message="图片理解失败，无法完成当前图片分析。",
                debug={"raw_error": str(exc)},
                source="image.understanding",
                cause=exc,
            ) from exc

    @staticmethod
    def _parse_vision_response(response: dict) -> dict:
        if not isinstance(response, dict):
            return {"raw": str(response)[:500]}

        # LLMClient._post_json already unwraps and parses JSON model content.
        # Accept that normalized shape directly instead of looking only for the
        # original OpenAI ``choices`` envelope.
        if any(
            key in response
            for key in ("summary", "objects", "possible_defects", "defects", "risk")
        ):
            parsed = dict(response)
            parsed.pop("__meta__", None)
            return parsed

        text = response.get("text")
        if isinstance(text, str) and text.strip():
            return {"summary": text.strip()[:2000]}

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
