from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState
from agent.router.node_registry import route_attachment_to_node
from agent.llm.gateway import LLMGateway


class FileExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        from agent.tools.file_parsers import parse_file_content
        from agent.tools.paper_format_checker import check_paper_format
        from app.services.object_storage.resolver import read_attachment_bytes

        parsed_files: list[dict] = []
        routed: list[dict] = []
        unsupported: list[dict] = []
        paper_reports: list[dict] = []
        template_id = str((step.input or {}).get("template_id") or "").strip() or None
        for attachment in state.attachments:
            node = route_attachment_to_node("chat", attachment)
            if not node:
                unsupported.append(attachment)
                continue
            routed.append({"attachment": attachment, "node": node.model_dump()})
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
            parsed_item = {
                "name": str(attachment.get("name") or "attachment"),
                "url": str(attachment.get("url") or ""),
                "content_type": content_type,
                "kind": parsed.get("kind"),
                "text": text[:12000],
                "summary": self._summarize_text(text),
                "metadata": {k: v for k, v in parsed.items() if k != "text"},
            }
            parsed_files.append(parsed_item)
            if step.capability_key == "file.paper_format_check":
                paper_reports.append(
                    check_paper_format(
                        parsed=parsed,
                        file_name=parsed_item["name"],
                        query=state.original_query,
                        template_id=template_id,
                    )
                )

        if step.capability_key == "file.paper_format_check":
            artifact_type = "paper_format_report"
        else:
            artifact_type = "file_summary" if step.capability_key == "file.summary" else "file_answer"
        model_summary = await self._try_chat_summary(parsed_files, state, request, db_session=db_session)
        if not parsed_files:
            art = artifact(artifact_type, "file", {"unsupported": unsupported, "parsed_files": []}, confidence=0.2)
            return (
                observation(step, status="skipped", summary="文件无法解析", artifact_ids=[art.artifact_id], error=str(unsupported)),
                [art],
            )
        if step.capability_key == "file.paper_format_check":
            merged = self._merge_paper_reports(paper_reports, unsupported=unsupported, parsed_files=parsed_files, model_summary=model_summary)
            content = merged
            obs_summary = str(merged.get("summary") or "") or "已完成论文查非分析"
            confidence = 0.8
        else:
            content = {
                "informal": True,
                "parsed_files": parsed_files,
                "model_summary": model_summary,
                "unsupported": unsupported,
            }
            obs_summary = model_summary or self._compose_summary(parsed_files, state.original_query)
            confidence = 0.75
        art = artifact(artifact_type, "file", content, confidence=confidence)
        return (
            observation(
                step,
                status="success",
                summary=obs_summary,
                artifact_ids=[art.artifact_id],
                metrics={"parsed_file_count": len(parsed_files), "unsupported_count": len(unsupported)},
            ),
            [art],
        )

    @staticmethod
    def _summarize_text(text: str) -> str:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return ""
        return cleaned[:500] + ("..." if len(cleaned) > 500 else "")

    def _compose_summary(self, parsed_files: list[dict], query: str) -> str:
        if not parsed_files:
            return "未能解析可用文件内容。"
        parts = []
        for item in parsed_files:
            parts.append(f"{item['name']}（{item.get('kind') or 'file'}）：{item.get('summary') or '无文本内容'}")
        return "\n".join(parts)

    @staticmethod
    def _merge_paper_reports(
        reports: list[dict],
        *,
        unsupported: list[dict],
        parsed_files: list[dict],
        model_summary: str | None,
    ) -> dict:
        if not reports:
            return {
                "document_type": "unknown",
                "template_id": None,
                "summary": "当前没有可用于论文查非的 docx 或 tex 文件。",
                "score": 0,
                "issues": [],
                "limitations": ["当前仅支持 docx 和 tex 的论文查非检查。"],
                "parsed_files": parsed_files,
                "unsupported": unsupported,
                "model_summary": model_summary,
            }
        base = dict(reports[0])
        if len(reports) == 1:
            base["parsed_files"] = parsed_files
            base["unsupported"] = unsupported
            base["model_summary"] = model_summary
            return base
        all_issues = []
        limitations = []
        document_types = []
        for item in reports:
            all_issues.extend(list(item.get("issues") or []))
            limitations.extend(list(item.get("limitations") or []))
            document_types.append(str(item.get("document_type") or "unknown"))
        total_score = sum(int(item.get("score") or 0) for item in reports) // len(reports)
        summary = model_summary or f"已完成 {len(reports)} 个文件的论文查非分析，共发现 {len(all_issues)} 个问题。"
        return {
            "document_type": ",".join(document_types),
            "template_id": base.get("template_id"),
            "summary": summary,
            "score": total_score,
            "issues": all_issues,
            "limitations": list(dict.fromkeys(limitations)),
            "parsed_files": parsed_files,
            "unsupported": unsupported,
            "model_summary": model_summary,
        }

    async def _try_chat_summary(self, parsed_files: list[dict], state: ManagerState, request: NormalizedRequest, *, db_session=None) -> str | None:
        if not parsed_files:
            return None
        if db_session is None:
            parsed_text = "\n".join(f"{f['name']}: {f.get('summary', '')}" for f in parsed_files[:3])
            return parsed_text[:800] if parsed_text else None
        try:
            from agent.llm.client import LLMClient
            from app.services.model_config_service import ModelConfigService

            models = await ModelConfigService(db_session, request.org_id).list_runtime_models()
            runtime = await LLMGateway().select_runtime(models=models, model_types={"chat"}, reserve=False)
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
