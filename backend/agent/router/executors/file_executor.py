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
        from agent.tools.paper_format_templates import DEFAULT_STRICT_PAPER_TEMPLATE_ID
        from app.services.object_storage.resolver import read_attachment_bytes

        parsed_files: list[dict] = []
        routed: list[dict] = []
        unsupported: list[dict] = []
        paper_reports: list[dict] = []
        template_id = str((step.input or {}).get("template_id") or "").strip() or None
        if step.capability_key == "file.paper_format_check" and not template_id:
            template_id = DEFAULT_STRICT_PAPER_TEMPLATE_ID
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
        model_summary = None
        if step.capability_key != "file.paper_format_check":
            model_summary = await self._try_chat_summary(parsed_files, state, request, db_session=db_session)
        if not parsed_files:
            art = artifact(artifact_type, "file", {"unsupported": unsupported, "parsed_files": []}, confidence=0.2)
            return (
                observation(step, status="skipped", summary="文件无法解析", artifact_ids=[art.artifact_id], error=str(unsupported)),
                [art],
            )
        if step.capability_key == "file.paper_format_check":
            merged = self._merge_paper_reports(paper_reports, unsupported=unsupported, parsed_files=parsed_files, model_summary=model_summary)
            self._finalize_paper_report_counts(merged)

            if db_session and parsed_files:
                parsed_for_evidence = {
                    **{k: v for k, v in parsed_files[0].get("metadata", {}).items()},
                    "kind": parsed_files[0].get("kind"),
                    "text": parsed_files[0].get("text", ""),
                }
                from agent.tools.paper_review_evidence import build_review_evidence_pack
                review_evidence_pack = build_review_evidence_pack(
                    parsed=parsed_for_evidence,
                    check_result=merged,
                    file_name=str(parsed_files[0].get("name") or ""),
                )
                merged["review_evidence_pack"] = review_evidence_pack

                effective_template_id = str(merged.get("template_id") or template_id or "")
                guide_evidence = None
                if effective_template_id and merged.get("issues"):
                    from agent.tools.paper_template_evidence import load_writing_guide_evidence
                    guide_evidence = await load_writing_guide_evidence(
                        effective_template_id,
                        issues=merged.get("issues"),
                        trace_id=state.trace_id,
                        task_id=state.session_id,
                        org_id=request.org_id,
                    )
                    if guide_evidence:
                        merged["writing_guide_evidence"] = guide_evidence
                        if guide_evidence.get("error"):
                            from agent.tools.paper_review_ai import PaperReviewModelError
                            raise PaperReviewModelError(
                                str(guide_evidence.get("error_message") or "模板条款检索失败")
                            )
                        clauses = list(guide_evidence.get("clauses") or [])
                        if clauses:
                            review_evidence_pack["related_template_clauses"] = clauses

                from agent.tools.paper_review_ai import generate_ai_review_output, PaperReviewModelError
                try:
                    ai_review_output = await generate_ai_review_output(
                        evidence_pack=review_evidence_pack,
                        guide_evidence=guide_evidence if guide_evidence and not guide_evidence.get("error") else None,
                        query=state.original_query,
                        db_session=db_session,
                        org_id=request.org_id,
                        trace_id=state.trace_id or state.workflow_run_id or state.request_id,
                        task_id=state.session_id,
                    )
                    merged["ai_review_output"] = ai_review_output
                    merged["model_used"] = True
                    if ai_review_output.get("summary"):
                        merged["summary"] = str(ai_review_output.get("summary"))
                        merged["model_summary"] = str(ai_review_output.get("summary"))
                    ai_limitations = [str(item) for item in list(ai_review_output.get("limitations") or []) if str(item).strip()]
                    if ai_limitations:
                        merged["limitations"] = list(dict.fromkeys([*list(merged.get("limitations") or []), *ai_limitations]))
                except PaperReviewModelError:
                    raise
                except Exception as exc:
                    raise PaperReviewModelError(f"论文查非 AI Review 失败：{exc}") from exc

                try:
                    report_files = await self._save_report_files(
                        merged=merged,
                        state=state,
                        request=request,
                    )
                    merged["report_files"] = report_files
                except Exception as exc:
                    raise PaperReviewModelError(f"论文查非报告生成失败：{exc}") from exc

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
                "chat_advice": "当前没有可用于论文查非的文档，请上传 docx 或 tex 文件后重试。",
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
            base["chat_advice"] = FileExecutor._build_chat_advice(list(base.get("issues") or []))
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
            "chat_advice": FileExecutor._build_chat_advice(all_issues),
            "limitations": list(dict.fromkeys(limitations)),
            "parsed_files": parsed_files,
            "unsupported": unsupported,
            "model_summary": model_summary,
        }

    @staticmethod
    def _build_chat_advice(issues: list[dict[str, object]]) -> str:
        if not issues:
            return "未发现明确格式问题，但仍建议人工复核模板细节。"
        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_issues = sorted(
            issues,
            key=lambda item: (
                severity_order.get(str(item.get("severity") or "").lower(), 9),
                str(item.get("title") or ""),
            ),
        )
        lines = ["已整理出以下修改意见："]
        for idx, issue in enumerate(sorted_issues[:5], start=1):
            location = FileExecutor._location_text(issue.get("location"))
            evidence = str(issue.get("evidence") or "").strip() or "无直接证据片段"
            suggestion = str(issue.get("suggestion") or "").strip() or "请结合模板要求人工复核。"
            lines.append(f"{idx}. {str(issue.get('title') or '格式问题')}")
            lines.append(f"位置：{location}")
            lines.append(f"证据：{evidence}")
            lines.append(f"建议：{suggestion}")
        if len(sorted_issues) > 5:
            lines.append(f"其余 {len(sorted_issues) - 5} 项问题请查看下载报告。")
        return "\n".join(lines)

    @staticmethod
    def _location_text(location: object) -> str:
        if isinstance(location, dict):
            display = str(location.get("display_text") or "").strip()
            if display:
                return display
            section = str(location.get("section_title") or location.get("section") or "").strip()
            paragraph_no = location.get("paragraph_no")
            line = location.get("line")
            if section and paragraph_no:
                return f"《{section}》下第{paragraph_no}段"
            if section and line:
                return f"《{section}》附近，第{line}行"
            if section:
                return f"《{section}》附近"
            if paragraph_no:
                return f"第{paragraph_no}段"
            if line:
                return f"第{line}行"
        return "位置待人工确认"

    @staticmethod
    def _finalize_paper_report_counts(merged: dict) -> None:
        issues = list(merged.get("issues") or [])
        merged["score"] = int(merged.get("score") or 0)
        merged["issue_count"] = len(issues)
        merged["high_count"] = sum(1 for item in issues if str(item.get("severity") or "") == "high")
        merged["medium_count"] = sum(1 for item in issues if str(item.get("severity") or "") == "medium")
        merged["low_count"] = sum(1 for item in issues if str(item.get("severity") or "") == "low")
        merged["report_files"] = list(merged.get("report_files") or [])
        merged["chat_advice"] = str(merged.get("chat_advice") or FileExecutor._build_chat_advice(issues))

    @staticmethod
    def _build_paper_review_enrichment_payload(
        *,
        merged: dict,
        parsed_files: list[dict],
        template_id: str,
        query: str,
        org_id: str,
        trace_id: str | None,
        task_id: str | None,
    ) -> dict | None:
        if not parsed_files:
            return None

        review_evidence_pack = {}
        if merged.get("issues"):
            parsed_for_evidence = {
                **{k: v for k, v in parsed_files[0].get("metadata", {}).items()},
                "kind": parsed_files[0].get("kind"),
                "text": parsed_files[0].get("text", ""),
            }
            from agent.tools.paper_review_evidence import build_review_evidence_pack

            review_evidence_pack = build_review_evidence_pack(
                parsed=parsed_for_evidence,
                check_result=merged,
                file_name=str(parsed_files[0].get("name") or ""),
            )

        return {
            "query": query,
            "org_id": org_id,
            "trace_id": trace_id,
            "task_id": task_id,
            "template_id": template_id,
            "review_evidence_pack": review_evidence_pack,
            "parsed_files": parsed_files,
        }

    @staticmethod
    async def _save_report_files(
        *,
        merged: dict,
        state: ManagerState,
        request: NormalizedRequest,
    ) -> list[dict]:
        """Generate and save report files to object storage."""
        from agent.tools.paper_review_report_builder import (
            build_markdown_report,
            build_docx_report,
            build_pdf_report,
        )

        report_files: list[dict] = []
        org_id = state.org_id or request.org_id or "default"
        user_id = state.user_id or "default"
        session_id = state.session_id or "default"
        message_id = state.assistant_message_id or "default"
        object_prefix = f"{org_id}/{user_id}/{session_id}/{message_id}"

        issues = list(merged.get("issues") or [])
        score = merged.get("score", 0)
        sc = sum(1 for i in issues if i.get("severity") == "high")
        mc = sum(1 for i in issues if i.get("severity") == "medium")
        lc = sum(1 for i in issues if i.get("severity") == "low")

        ai_output = merged.get("ai_review_output") or {}
        evidence_pack = merged.get("review_evidence_pack") or {}

        review_output = dict(ai_output)
        review_output["answer"] = str(review_output.get("answer") or merged.get("summary") or "")
        review_output["summary"] = str(review_output.get("summary") or merged.get("summary") or "")
        review_output["markdown_report"] = str(review_output.get("markdown_report") or "")
        model_issues = list(review_output.get("issues") or [])
        review_output["model_issues"] = model_issues
        review_output["issues"] = issues
        review_output["limitations"] = list(
            review_output.get("limitations") or merged.get("limitations") or []
        )
        review_output["download_title"] = str(
            review_output.get("download_title") or "论文查非辅助报告"
        )

        md_report = build_markdown_report(review_output=review_output, evidence_pack=evidence_pack)

        from app.services.object_storage.factory import build_object_storage
        storage = build_object_storage()
        md_key = f"{object_prefix}/paper-review-report.md"
        md_object = storage.put_bytes(bucket="chat-reports", object_key=md_key, data=md_report.encode("utf-8"), content_type="text/markdown")
        report_files.append({
            "format": "md",
            "file_name": "论文查非辅助报告.md",
            "bucket": "chat-reports",
            "object_key": md_key,
            "url": FileExecutor._report_file_url(md_object, md_key),
            "content_type": "text/markdown",
        })

        docx_data = build_docx_report(md_report)
        docx_key = f"{object_prefix}/paper-review-report.docx"
        docx_object = storage.put_bytes(bucket="chat-reports", object_key=docx_key, data=docx_data,
                                        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        report_files.append({
            "format": "docx",
            "file_name": "论文查非辅助报告.docx",
            "bucket": "chat-reports",
            "object_key": docx_key,
            "url": FileExecutor._report_file_url(docx_object, docx_key),
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        })

        pdf_data = build_pdf_report(md_report)
        pdf_key = f"{object_prefix}/paper-review-report.pdf"
        pdf_object = storage.put_bytes(bucket="chat-reports", object_key=pdf_key, data=pdf_data,
                                      content_type="application/pdf")
        report_files.append({
            "format": "pdf",
            "file_name": "论文查非辅助报告.pdf",
            "bucket": "chat-reports",
            "object_key": pdf_key,
            "url": FileExecutor._report_file_url(pdf_object, pdf_key),
            "content_type": "application/pdf",
        })

        merged["ai_review_output"] = review_output
        merged["score"] = score
        merged["issue_count"] = len(issues)
        merged["high_count"] = sc
        merged["medium_count"] = mc
        merged["low_count"] = lc
        merged["chat_advice"] = str(merged.get("chat_advice") or FileExecutor._build_chat_advice(issues))

        return report_files

    @staticmethod
    def _report_file_url(_storage_object: dict | None, object_key: str) -> str:
        return f"/api/v1/chat/files/chat-reports/{object_key}"

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
