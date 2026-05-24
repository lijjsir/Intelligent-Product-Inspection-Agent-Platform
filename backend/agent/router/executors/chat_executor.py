from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent.llm.client import LLMClient
from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


logger = logging.getLogger(__name__)


class ChatExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        if step.capability_key == "chat.general":
            answer = await self._call_model(
                state,
                request,
                self._general_prompt(state),
                use_tools=True,
            )
            if answer is None:
                return observation(step, status="failed", summary="聊天模型不可用，请检查后台模型配置"), []
            return observation(step, status="success", summary=answer), []

        if step.capability_key == "chat.response.compose":
            answer = await self._call_model(
                state,
                request,
                self._compose_prompt(state),
                use_tools=True,
            )
            if answer is None:
                fallback = self._build_fallback(state)
                art = artifact("composed_response", "chat", {"answer": fallback, "summary": fallback, "message_type": "assistant_text", "status": "degraded", "surface": state.surface, "blocked": False})
                return observation(step, status="success", summary=fallback, artifact_ids=[art.artifact_id]), [art]
            composed = self._compose_from_model(state, answer)
            art = artifact("composed_response", "chat", composed)
            return observation(step, status="success", summary=composed.get("summary", answer), artifact_ids=[art.artifact_id]), [art]

        return observation(step, status="failed", summary=f"未知 capability: {step.capability_key}"), []

    # ── model helpers ──

    async def _call_model(
        self,
        state: ManagerState,
        request: NormalizedRequest,
        user_prompt: str,
        *,
        use_tools: bool = False,
    ) -> str | None:
        runtime = state.manager_model_runtime or {}
        if not runtime.get("model_id"):
            return None
        try:
            client = LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=runtime.get("model_id"),
                provider=runtime.get("provider"),
                org_id=request.org_id,
                input_price_per_million=runtime.get("input_price_per_million"),
                output_price_per_million=runtime.get("output_price_per_million"),
            )
            state.used_llm_calls += 1

            tools, tool_name_map = self._build_tools_for_llm(state)
            if use_tools and tools:
                return await self._run_tool_loop(state, client, user_prompt, tools, tool_name_map)

            response = await client.chat(
                [
                    {
                        "role": "system",
                        "content": "你是智能助手。用中文简洁准确回答。返回 JSON：{\"answer\":\"...\"}。",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                observation_name="chat",
                observation_metadata={"surface": state.surface},
            )
            return self._extract_answer(response)
        except Exception as exc:
            logger.warning("Chat model call failed: %s", exc, exc_info=True)
            return None

    def _build_tools_for_llm(self, state: ManagerState) -> tuple[list[dict[str, Any]], dict[str, str]]:
        available = getattr(state, "available_tools", None)
        if not available:
            return [], {}

        tools: list[dict[str, Any]] = []
        name_map: dict[str, str] = {}
        used_names: set[str] = set()
        for spec in available:
            if not hasattr(spec, "to_openai_tool"):
                continue
            internal_name = str(getattr(spec, "name", "") or "")
            if not internal_name:
                continue
            llm_name = self._llm_tool_name(internal_name, used_names)
            tool = dict(spec.to_openai_tool())
            function = dict(tool.get("function") or {})
            function["name"] = llm_name
            tool["function"] = function
            tools.append(tool)
            name_map[llm_name] = internal_name
        return tools, name_map

    @staticmethod
    def _llm_tool_name(internal_name: str, used_names: set[str]) -> str:
        base = re.sub(r"[^a-zA-Z0-9_-]", "_", internal_name).strip("_") or "tool"
        base = base[:64]
        candidate = base
        index = 2
        while candidate in used_names:
            suffix = f"_{index}"
            candidate = f"{base[:64 - len(suffix)]}{suffix}"
            index += 1
        used_names.add(candidate)
        return candidate

    async def _run_tool_loop(
        self, state: ManagerState, client: LLMClient,
        user_prompt: str, tools: list[dict[str, Any]], tool_name_map: dict[str, str] | None = None,
    ) -> str | None:
        invoker = getattr(state, "tool_invoker", None)
        tool_name_map = tool_name_map or {}

        forced_tool_names = set(getattr(state, "forced_tool_names", []) or [])
        force_web = "web.search" in forced_tool_names

        system_prompt = (
            "你是智能助手。可以使用工具获取信息。"
            "如果需要工具，必须通过 tool_calls 调用工具，不要把工具参数作为普通内容输出。"
            "如果不需要工具，必须返回 JSON：{\"answer\":\"...\"}。"
            "用中文回答。"
        )
        if force_web:
            system_prompt = (
                "你是智能助手。用户开启了联网搜索，你必须优先调用 web.search 工具检索互联网实时信息，"
                "然后再结合其他工具（知识库、文件解析等）一起解决问题。"
                "如果需要工具，必须通过 tool_calls 调用工具，不要把工具参数作为普通内容输出。"
                "如果不需要工具，必须返回 JSON：{\"answer\":\"...\"}。"
                "重要：调用 web.search 时，query 参数只传核心关键词（名词/实体名，空格分隔），"
                "去掉'怎么样''如何''是什么'等无用词。例如用户问'张雪峰现在怎么了'，只传 '张雪峰 近况'。"
                "用中文回答。"
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        max_rounds = min(state.max_tool_calls, 3)
        used_tool = False

        for _round in range(max_rounds):
            response = await client.chat_with_tools(
                messages, tools=tools, temperature=0.2,
                observation_name="chat.tool_loop",
                observation_metadata={"surface": state.surface, "round": _round},
            )

            tool_calls = response.get("tool_calls") or self._tool_calls_from_content(response.get("content"), tools)
            if tool_calls:
                pass
            elif response.get("content"):
                if used_tool:
                    messages.append({"role": "assistant", "content": response["content"]})
                    return await self._finalize_tool_answer(state, client, messages)
                answer = self._extract_answer(response)
                if answer:
                    return answer
                messages.append({"role": "assistant", "content": response["content"]})
                return await self._finalize_tool_answer(state, client, messages)
            else:
                if used_tool:
                    return await self._finalize_tool_answer(state, client, messages)
                return "无法确定答案"

            for tc in tool_calls:
                llm_tool_name = str(tc.get("name") or "")
                internal_tool_name = tool_name_map.get(llm_tool_name, llm_tool_name)
                messages.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": tc.get("id", ""), "type": "function",
                    "function": {"name": llm_tool_name, "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False)},
                }]})

                if invoker:
                    from agent.tools.contracts import ToolContext
                    context = ToolContext(
                        org_id=state.org_id, request_id=state.request_id,
                        agent=getattr(state, "selected_agent", "") or "",
                        surface=state.surface,
                        user_id=state.user_id, session_id=state.session_id,
                        workflow_run_id=state.workflow_run_id,
                        allowed_modes=state.allowed_modes,
                    )
                    result = await invoker.invoke(tool_name=internal_tool_name, arguments=tc.get("arguments", {}), context=context)
                    result_text = json.dumps({"status": result.status, "data": result.data, "error": result.error}, ensure_ascii=False)
                    messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result_text})
                else:
                    messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                     "content": json.dumps({"status": "skipped", "error": "ToolInvoker not available"})})

                used_tool = True
                state.used_tool_calls += 1

            # After executing tools, finalize immediately — don't loop
            return await self._finalize_tool_answer(state, client, messages)

        if used_tool:
            return await self._finalize_tool_answer(state, client, messages)
        return "无法确定答案"

    def _tool_calls_from_content(self, content: Any, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(content, str) or not content.strip():
            return []

        # Try XML / Anthropic format first: <function_calls><invoke name="x"><parameter name="y">z</parameter></invoke></function_calls>
        xml_calls = self._parse_xml_tool_calls(content, tools)
        if xml_calls:
            return xml_calls

        # Try JSON format: {"tool": "x", "arguments": {...}} or {"name": "x", "arguments": {...}}
        return self._parse_json_tool_calls(content, tools)

    def _parse_xml_tool_calls(self, content: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse Anthropic/Claude-style XML tool calls from text content."""
        import re as _re
        result: list[dict[str, Any]] = []
        # Match <function_calls> or <tool_calls> blocks
        block_match = _re.search(
            r"<(?:function_calls|tool_calls)>(.*?)</(?:function_calls|tool_calls)>",
            content, _re.DOTALL,
        )
        if not block_match:
            # Try standalone <invoke> tags
            invocations = _re.findall(
                r"<invoke\s+name\s*=\s*[\"']([^\"']+)[\"']\s*>(.*?)</invoke>",
                content, _re.DOTALL,
            )
        else:
            invocations = _re.findall(
                r"<invoke\s+name\s*=\s*[\"']([^\"']+)[\"']\s*>(.*?)</invoke>",
                block_match.group(1), _re.DOTALL,
            )

        for tool_name, params_block in invocations:
            arguments: dict[str, Any] = {}
            param_matches = _re.findall(
                r"<parameter\s+name\s*=\s*[\"']([^\"']+)[\"'](?:\s+string\s*=\s*[\"'](?:true|false)[\"'])?\s*>(.*?)</parameter>",
                params_block, _re.DOTALL,
            )
            for pname, pvalue in param_matches:
                pvalue = pvalue.strip()
                if pvalue.isdigit():
                    arguments[pname] = int(pvalue)
                elif pvalue.lower() in ("true", "false"):
                    arguments[pname] = pvalue.lower() == "true"
                else:
                    arguments[pname] = pvalue

            # Map tool name to known tool
            matched_tool = tool_name
            if tool_name not in {t.get("function", {}).get("name", "") for t in tools}:
                for t in tools:
                    fn = t.get("function") or {}
                    if fn.get("name", "").replace("_", ".") == tool_name.replace("_", "."):
                        matched_tool = fn["name"]
                        break

            result.append({
                "id": f"call_{matched_tool}",
                "name": matched_tool,
                "arguments": arguments,
            })
        return result

    def _parse_json_tool_calls(self, content: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = self._parse_json_object(content)
        if not payload:
            return []
        if payload.get("answer") or payload.get("text"):
            return []

        explicit_name = payload.get("tool") or payload.get("tool_name") or payload.get("name") or payload.get("function")
        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else payload

        candidates: list[tuple[int, str, dict[str, Any]]] = []
        for tool in tools:
            function = tool.get("function") or {}
            tool_name = str(function.get("name") or "")
            if not tool_name:
                continue
            if explicit_name and str(explicit_name) != tool_name:
                continue
            schema = function.get("parameters") or {}
            properties = schema.get("properties") if isinstance(schema, dict) else {}
            required = set(schema.get("required") or []) if isinstance(schema, dict) else set()
            if not isinstance(properties, dict):
                properties = {}
            arg_keys = set(arguments.keys())
            property_keys = set(properties.keys())
            if required and not required.issubset(arg_keys):
                continue
            overlap = arg_keys & property_keys
            if not explicit_name and not overlap:
                continue
            unknown_keys = arg_keys - property_keys if property_keys else set()
            score = len(overlap) * 10 - len(unknown_keys)
            if required:
                score += len(required)
            candidates.append((score, tool_name, {key: value for key, value in arguments.items() if not property_keys or key in property_keys}))

        if not candidates:
            return []
        candidates.sort(key=lambda item: item[0], reverse=True)
        _, tool_name, arguments = candidates[0]
        return [{"id": f"call_{tool_name}", "name": tool_name, "arguments": arguments}]

    @staticmethod
    def _parse_json_object(content: Any) -> dict[str, Any] | None:
        if isinstance(content, dict):
            return content
        if not isinstance(content, str) or not content.strip():
            return None
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    async def _finalize_tool_answer(
        self,
        state: ManagerState,
        client: LLMClient,
        messages: list[dict[str, Any]],
    ) -> str | None:
        final_messages = [
            *messages,
            {
                "role": "user",
                "content": (
                    "请根据上面的工具返回结果，直接回答用户问题。"
                    "如果工具返回了搜索结果，请引用搜索结果中的具体信息来回答。"
                    "如果工具没有返回有效信息，请如实说明。"
                ),
            },
        ]
        # Don't use json_object mode — let model answer naturally with tool results.
        if hasattr(client, "_post_json"):
            final = await client._post_json(
                "/chat/completions",
                {
                    "model": client.model_id,
                    "messages": final_messages,
                    "temperature": 0.3,
                },
                observation_name="chat.final",
                observation_type="generation",
                observation_metadata={"surface": state.surface},
            )
        else:
            final = await client.chat(final_messages, temperature=0.3, observation_name="chat.final")
        choices = final.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return self._extract_answer(final)

    @staticmethod
    def _extract_answer(response: dict) -> str | None:
        if isinstance(response, dict) and "answer" in response:
            return str(response["answer"]).strip() or None
        if isinstance(response, dict) and "text" in response:
            return str(response["text"]).strip() or None
        content = response.get("content") if isinstance(response, dict) else None
        if isinstance(content, dict):
            answer = content.get("answer") or content.get("text") or ""
            return str(answer).strip() or None
        choices = response.get("choices") if isinstance(response, dict) else None
        if isinstance(choices, list) and choices:
            content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            try:
                data = json.loads(content)
                answer = data.get("answer") or data.get("text") or ""
                return str(answer).strip() or None
            except Exception:
                return content.strip()[:1000] or None
        return None

    # ── prompts ──

    @staticmethod
    def _history_text(state: ManagerState) -> str:
        if not state.history_messages:
            return ""
        lines = []
        for m in state.history_messages[-10:]:
            role = "用户" if m.get("role") == "user" else "助手"
            content = str(m.get("content") or "")[:300]
            if content:
                lines.append(f"{role}：{content}")
        return "\n".join(lines) if lines else ""

    @staticmethod
    def _general_prompt(state: ManagerState) -> str:
        """General chat prompt — keep it simple: just history + query, no old artifacts."""
        parts = []
        hist = ChatExecutor._history_text(state)
        if hist:
            parts.append(f"对话历史：\n{hist}")
        parts.append(f"用户问题：{state.original_query}")
        return "\n\n".join(parts)

    @staticmethod
    def _compose_prompt(state: ManagerState) -> str:
        """Compose final answer — only include current-iteration artifacts, not stale ones."""
        parts = []
        hist = ChatExecutor._history_text(state)
        if hist:
            parts.append(f"对话历史：\n{hist}")
        parts.append(f"用户问题：{state.original_query}")
        parts.append(f"场景：{state.surface}")
        rag_context = ChatExecutor._rag_prompt_context(state)
        if rag_context:
            parts.append(rag_context)

        # Only include artifacts from the current iteration (not all session history)
        prev_count = state.last_artifact_counts[-2] if len(state.last_artifact_counts) >= 2 else 0
        current_artifacts = state.artifacts[prev_count:]
        current_observations = state.observations[prev_count:]

        if current_observations:
            obs_text = "\n".join(
                f"- [{o.capability_key}] {o.status}: {o.summary}"
                for o in current_observations
                if o.capability_key != "chat.response.compose"
            )
            if obs_text:
                parts.append(f"当前步骤：\n{obs_text}")
        if current_artifacts:
            for art in current_artifacts:
                if art.type in {"composed_response", "rag_hits"}:
                    continue
                content = json.dumps(art.content or {}, ensure_ascii=False, default=str)[:2000]
                parts.append(f"{art.type} 结果：{content}")
        if state.errors:
            parts.append(f"错误：{'; '.join(e.get('message', '') for e in state.errors)}")
        if state.selected_rag_space:
            parts.append(
                "回答要求：如果上面有 RAG 证据，请优先结合证据回答，并在使用证据的句子后标注引用编号，例如 [RAG-1]。"
                "如果 RAG 未检索到可用片段或证据不足，仍然要继续回答用户问题；但必须明确说明当前选中的知识库没有提供可引用依据，后续内容基于模型通用能力生成，不要伪造知识库引用。"
            )
        else:
            parts.append("请根据以上所有信息，生成最终的自然语言回复。")
        return "\n\n".join(parts)

    @staticmethod
    def _rag_prompt_context(state: ManagerState) -> str:
        rag_artifacts = [art for art in state.artifacts if art.type == "rag_hits"]
        if not rag_artifacts and not state.selected_rag_space:
            return ""

        content = dict((rag_artifacts[-1].content if rag_artifacts else {}) or {})
        hits = [item for item in list(content.get("hits") or []) if isinstance(item, dict)]
        selected = state.selected_rag_space or {}
        space_name = str(content.get("rag_space_name") or selected.get("name") or selected.get("id") or "selected RAG space")
        if not hits:
            return f"RAG 证据（{space_name}）：未检索到可用片段。"

        lines = [f"RAG 证据（{space_name}）："]
        for index, hit in enumerate(hits[:5], start=1):
            title = str(hit.get("title") or hit.get("document_name") or f"片段 {index}")
            source = str(hit.get("source") or hit.get("full_path") or "")
            score = hit.get("score")
            quote = ChatExecutor._hit_quote(hit)[:800]
            meta = f"[RAG-{index}] {title}"
            if source:
                meta += f" | {source}"
            if score is not None:
                meta += f" | score={score}"
            lines.append(f"{meta}\n{quote}")
        return "\n\n".join(lines)

    @staticmethod
    def _hit_quote(hit: dict[str, Any]) -> str:
        for key in ("quote", "text", "content", "chunk_text", "summary"):
            value = hit.get(key)
            if value:
                return str(value).strip()
        payload = hit.get("payload")
        if isinstance(payload, dict):
            for key in ("quote", "text", "content"):
                value = payload.get(key)
                if value:
                    return str(value).strip()
        return ""

    # ── compose helpers ──

    @staticmethod
    def _compose_from_model(state: ManagerState, answer: str) -> dict[str, Any]:
        status, blocked = ChatExecutor._resolve_status(state)
        reason = state.route_plan.reason if state.route_plan else ""
        mt = "assistant_text"
        if status == "blocked":
            mt = "action_blocked"
        elif reason == "image_understanding":
            mt = "image_analysis"
        elif reason in {"file_summary", "file_qa"}:
            mt = "file_answer"
        elif reason == "quality_report_query":
            mt = "report_answer"
        elif reason == "quality_task_status":
            mt = "task_status"
        elif reason == "inspection_execute":
            mt = "task_result"
        return {
            "answer": answer,
            "summary": answer[:200] if answer else "",
            "message_type": mt,
            "surface": state.surface,
            "status": status,
            "blocked": blocked,
        }

    @staticmethod
    def _resolve_status(state: ManagerState) -> tuple[str, bool]:
        if state.errors or state.missing_inputs:
            return "blocked", True
        if state.route_plan and state.route_plan.reason == "action_blocked":
            return "blocked", True
        if state.final_action == "fail":
            return "failed", False
        return "completed", False

    @staticmethod
    def _build_fallback(state: ManagerState) -> str:
        if state.errors or state.missing_inputs:
            return "模型暂不可用，无法完成请求。请检查后台模型配置。"
        rag_context = ChatExecutor._rag_prompt_context(state)
        if rag_context and state.selected_rag_space:
            if "未检索到可用片段" in rag_context:
                return "当前选中的知识库没有检索到可用依据；同时模型回复生成失败，因此暂时无法给出可靠回答。请稍后重试或补充知识库资料。"
            return rag_context[:500]
        if state.observations:
            for obs in reversed(state.observations):
                if obs.summary and obs.capability_key != "chat.response.compose":
                    return obs.summary[:500]
        return "模型暂不可用，请稍后重试或检查后台配置。"
