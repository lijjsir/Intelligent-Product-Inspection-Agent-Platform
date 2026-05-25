from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent.llm.client import LLMClient
from agent.llm.pricing import ModelPricing
from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPTS: dict[str, str] = {
    "chat.general.system": (
        'You are the PIAP workspace assistant. Respond in Chinese. '
        'Answer naturally, accurately, and concisely. '
        'If the prompt includes inspection history or platform context, use it only when it is relevant '
        'to the current user question. '
        'Return JSON in the form {"answer": "...", "summary": "..."}.'
    ),
    "chat.compose.system": (
        'You are composing the final PIAP chat reply. Respond in Chinese. '
        'Use the provided evidence, workflow observations, and inspection context when they are relevant. '
        'Do not invent standards, verdicts, risks, or trace details. '
        'If evidence is insufficient, say so plainly. '
        'Return JSON in the form {"answer": "...", "summary": "..."}.'
    ),
    "chat.rag_answer.system": (
        'You are the PIAP retrieval-answer assistant. Respond in Chinese. '
        'Answer from the retrieved evidence first, cite evidence markers when available, '
        'and do not fill gaps with unsupported assumptions. '
        'If the selected knowledge base does not contain the needed evidence, say so clearly. '
        'Return JSON in the form {"answer": "...", "summary": "..."}.'
    ),
    "chat.file_summary.system": (
        'You are the PIAP file-analysis assistant. Respond in Chinese. '
        'Answer from the parsed file content and extracted evidence only. '
        'Call out uncertainty when the uploaded material is incomplete. '
        'Return JSON in the form {"answer": "...", "summary": "..."}.'
    ),
}

TOOL_LOOP_INSTRUCTIONS = (
    "If you need tools, call them through tool_calls only. "
    "Do not print tool arguments as normal text. "
    'If tools are not needed, return JSON in the form {"answer": "...", "summary": "..."}.'
)

FORCE_WEB_TOOL_LOOP_INSTRUCTIONS = (
    "The user enabled web search. Prefer calling web.search first when fresh external information matters, "
    "then combine it with the available platform context or other tools. "
    "Pass only the essential search keywords to web.search. "
    'If tools are not needed, return JSON in the form {"answer": "...", "summary": "..."}.'
)


class ChatExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        if step.capability_key == "web.search":
            return await self._execute_web_search(step, state)

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
                use_tools=not state.force_web_search,
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

    async def _execute_web_search(
        self,
        step: AgentPlanStep,
        state: ManagerState,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        invoker = getattr(state, "tool_invoker", None)
        if invoker is None:
            return observation(step, status="failed", summary="ToolInvoker not available"), []

        args = dict(step.input or {})
        args["query"] = str(args.get("query") or state.original_query).strip()
        args["max_results"] = int(args.get("max_results") or 5)
        args["region"] = str(args.get("region") or "cn-zh")

        from agent.tools.contracts import ToolContext

        context = ToolContext(
            org_id=state.org_id,
            request_id=state.request_id,
            agent=getattr(state, "selected_agent", "") or "chat",
            surface=state.surface,
            user_id=state.user_id,
            session_id=state.session_id,
            workflow_run_id=state.workflow_run_id,
            allowed_modes=state.allowed_modes,
        )
        result = await invoker.invoke(tool_name="web.search", arguments=args, context=context)
        data = dict(result.data or {})
        results = [item for item in list(data.get("results") or []) if isinstance(item, dict)]
        content = {
            "query": data.get("query") or args["query"],
            "keywords": data.get("keywords"),
            "results": results,
            "total": int(data.get("total") or len(results)),
            "status": result.status,
            "error": result.error or data.get("error"),
        }
        art = artifact("web_search_results", "chat", content)
        status = "success" if result.status == "success" else result.status
        summary = f"联网搜索完成，命中 {len(results)} 条结果"
        if status != "success":
            summary = f"联网搜索失败：{content.get('error') or status}"
        state.used_tool_calls += 1
        return observation(step, status=status, summary=summary, artifact_ids=[art.artifact_id]), [art]

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
                    "必须返回 JSON：{\"answer\":\"...\",\"summary\":\"...\"}。"
                ),
            },
        ]
        post_json = getattr(client, "_post_json", None)
        if callable(post_json):
            final = await post_json(
                "/chat/completions",
                {
                    "model": getattr(client, "model_id", ""),
                    "messages": final_messages,
                    "temperature": 0.3,
                },
                observation_name="chat.final",
                observation_type="generation",
                observation_metadata=self._observation_metadata(state),
            )
        else:
            final = await client.chat(
                final_messages,
                temperature=0.3,
                observation_name="chat.final",
                observation_metadata=self._observation_metadata(state),
            )
        self._record_llm_meta(state, final)
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
            cleaned = ChatExecutor._strip_json_code_blocks(content)
            if cleaned and cleaned != content.strip():
                return cleaned[:1000] or None
            try:
                data = json.loads(content)
                answer = data.get("answer") or data.get("text") or ""
                return str(answer).strip() or None
            except Exception:
                return content.strip()[:1000] or None
        return None

    @staticmethod
    def _strip_json_code_blocks(content: str) -> str:
        return re.sub(
            r"```(?:json|JSON)?\s*\{[\s\S]*?\}\s*```",
            "",
            content,
        ).strip()

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
                trace_id=state.trace_id or state.workflow_run_id or state.request_id,
                org_id=request.org_id,
                input_price_per_million=runtime.get("input_price_per_million"),
                output_price_per_million=runtime.get("output_price_per_million"),
            )
            state.used_llm_calls += 1
            system_prompt = await self._resolve_system_prompt(
                state,
                request,
                compose=bool(state.route_plan and state.route_plan.reason != "general_chat"),
            )
            tools, tool_name_map = self._build_tools_for_llm(state)
            if use_tools and tools:
                return await self._run_tool_loop(
                    state,
                    client,
                    user_prompt,
                    tools,
                    tool_name_map,
                    system_prompt=system_prompt,
                )

            response = await client.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                observation_name="chat",
                observation_metadata=self._observation_metadata(state),
            )
            self._record_llm_meta(state, response)
            return self._extract_answer(response)
        except Exception as exc:
            logger.warning("Chat model call failed: %s", exc, exc_info=True)
            return None

    async def _run_tool_loop(
        self,
        state: ManagerState,
        client: LLMClient,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_name_map: dict[str, str] | None = None,
        system_prompt: str | None = None,
    ) -> str | None:
        invoker = getattr(state, "tool_invoker", None)
        tool_name_map = tool_name_map or {}

        first_tool_name = tools[0].get("function", {}).get("name") if tools else ""
        force_web = bool(first_tool_name and tool_name_map.get(first_tool_name, first_tool_name) == "web.search")
        base_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPTS["chat.general.system"]
        tool_instructions = FORCE_WEB_TOOL_LOOP_INSTRUCTIONS if force_web else TOOL_LOOP_INSTRUCTIONS
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": f"{base_system_prompt}\n\n{tool_instructions}"},
            {"role": "user", "content": user_prompt},
        ]

        async def invoke_tool_call(tool_call: dict[str, Any]) -> None:
            llm_tool_name = str(tool_call.get("name") or "")
            internal_tool_name = tool_name_map.get(llm_tool_name, llm_tool_name)
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tool_call.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": llm_tool_name,
                                "arguments": json.dumps(tool_call.get("arguments", {}), ensure_ascii=False),
                            },
                        }
                    ],
                }
            )

            if invoker:
                from agent.tools.contracts import ToolContext

                context = ToolContext(
                    org_id=state.org_id,
                    request_id=state.request_id,
                    agent=getattr(state, "selected_agent", "") or "",
                    surface=state.surface,
                    user_id=state.user_id,
                    session_id=state.session_id,
                    workflow_run_id=state.workflow_run_id,
                    allowed_modes=state.allowed_modes,
                )
                result = await invoker.invoke(
                    tool_name=internal_tool_name,
                    arguments=tool_call.get("arguments", {}),
                    context=context,
                )
                result_text = json.dumps(
                    {"status": result.status, "data": result.data, "error": result.error},
                    ensure_ascii=False,
                )
            else:
                result_text = json.dumps(
                    {"status": "skipped", "error": "ToolInvoker not available"},
                    ensure_ascii=False,
                )

            messages.append({"role": "tool", "tool_call_id": tool_call.get("id", ""), "content": result_text})
            state.used_tool_calls += 1

        max_rounds = min(state.max_tool_calls, 3)
        forced_tool_names = set(getattr(state, "forced_tool_names", []) or [])
        if "web.search" in forced_tool_names and force_web:
            await invoke_tool_call(
                {
                    "id": "call_forced_web_search",
                    "name": first_tool_name,
                    "arguments": {
                        "query": state.original_query,
                        "max_results": 5,
                        "region": "cn-zh",
                    },
                }
            )
            return await self._finalize_tool_answer(state, client, messages)

        used_tool = False
        for round_index in range(max_rounds):
            response = await client.chat_with_tools(
                messages,
                tools=tools,
                temperature=0.2,
                observation_name="chat.tool_loop",
                observation_metadata={**self._observation_metadata(state), "round": round_index},
            )
            self._record_llm_meta(state, response)

            tool_calls = response.get("tool_calls") or self._tool_calls_from_content(response.get("content"), tools)
            if not tool_calls:
                if response.get("content"):
                    if used_tool:
                        messages.append({"role": "assistant", "content": response["content"]})
                        return await self._finalize_tool_answer(state, client, messages)
                    answer = self._extract_answer(response)
                    if answer:
                        return answer
                    messages.append({"role": "assistant", "content": response["content"]})
                    return await self._finalize_tool_answer(state, client, messages)
                if used_tool:
                    return await self._finalize_tool_answer(state, client, messages)
                return "无法确定答案"

            for tool_call in tool_calls:
                await invoke_tool_call(tool_call)
                used_tool = True

            return await self._finalize_tool_answer(state, client, messages)

        if used_tool:
            return await self._finalize_tool_answer(state, client, messages)
        return "无法确定答案"

    async def _resolve_system_prompt(
        self,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        compose: bool,
    ) -> str:
        prompt_key = self._prompt_key_for_state(state, compose=compose)
        default_content = DEFAULT_SYSTEM_PROMPTS.get(prompt_key, DEFAULT_SYSTEM_PROMPTS["chat.compose.system"])
        try:
            from app.services.prompt_admin_service import PromptResolver
            from infra.database.session import get_session

            resolved = await PromptResolver(get_session).get(prompt_key, org_id=request.org_id)
            return str(resolved or default_content)
        except Exception as exc:
            logger.debug(
                "prompt resolve skipped prompt_key=%s org_id=%s: %s",
                prompt_key,
                request.org_id,
                exc,
            )
            return default_content

    @staticmethod
    def _prompt_key_for_state(state: ManagerState, *, compose: bool) -> str:
        if not compose:
            return "chat.general.system"
        reason = str(state.route_plan.reason if state.route_plan else "").strip().lower()
        if reason == "rag_qa":
            return "chat.rag_answer.system"
        if reason in {"file_summary", "file_qa"}:
            return "chat.file_summary.system"
        return "chat.compose.system"

    @staticmethod
    def _history_text(state: ManagerState) -> str:
        if not state.history_messages:
            return ""
        lines = []
        for message in state.history_messages[-10:]:
            role = "user" if message.get("role") == "user" else "assistant"
            content = str(message.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content[:300]}")
        return "\n".join(lines)

    @staticmethod
    def _general_prompt(state: ManagerState) -> str:
        parts: list[str] = []
        history_text = ChatExecutor._history_text(state)
        if history_text:
            parts.append(f"Conversation history:\n{history_text}")
        inspection_context = ChatExecutor._inspection_context_text(state)
        if inspection_context:
            parts.append(inspection_context)
        parts.append(f"Current user question:\n{state.original_query}")
        return "\n\n".join(parts)

    @staticmethod
    def _compose_prompt(state: ManagerState) -> str:
        parts: list[str] = []
        history_text = ChatExecutor._history_text(state)
        if history_text:
            parts.append(f"Conversation history:\n{history_text}")
        inspection_context = ChatExecutor._inspection_context_text(state)
        if inspection_context:
            parts.append(inspection_context)
        parts.append(f"Current user question:\n{state.original_query}")
        parts.append(f"Surface:\n{state.surface}")

        rag_context = ChatExecutor._rag_prompt_context(state)
        if rag_context:
            parts.append(rag_context)

        prev_count = state.last_artifact_counts[-2] if len(state.last_artifact_counts) >= 2 else 0
        current_artifacts = state.artifacts[prev_count:]
        current_observations = state.observations[prev_count:]

        if current_observations:
            observation_lines = "\n".join(
                f"- [{item.capability_key}] {item.status}: {item.summary}"
                for item in current_observations
                if item.capability_key != "chat.response.compose"
            )
            if observation_lines:
                parts.append(f"Current workflow observations:\n{observation_lines}")
        if current_artifacts:
            for artifact_item in current_artifacts:
                if artifact_item.type in {"composed_response", "rag_hits"}:
                    continue
                content = json.dumps(artifact_item.content or {}, ensure_ascii=False, default=str)[:2000]
                parts.append(f"{artifact_item.type} result:\n{content}")
        if state.errors:
            parts.append(
                "Errors:\n"
                + "; ".join(str(item.get("message") or "") for item in state.errors if item.get("message"))
            )
        if state.selected_rag_space:
            parts.append(
                "Answer requirements:\n"
                "Prefer the RAG evidence above when it is relevant, and cite evidence markers such as [RAG-1].\n"
                "If the selected knowledge base does not provide enough evidence, say so clearly and do not fill gaps with guesses.\n"
                "如果 RAG 证据不足，仍然要继续回答用户问题，但必须明确区分知识库证据和通用回答。\n"
                "如果 RAG 证据不足以回答用户问题，请明确说明当前选中的知识库没有提供该信息，不要凭常识补全，不要伪造知识库引用。"
            )
        else:
            parts.append("Answer requirements:\nWrite the final natural-language reply from the information above.")
        return "\n\n".join(parts)

    @staticmethod
    def _inspection_context_text(state: ManagerState) -> str:
        context = state.inspection_context or {}
        if not isinstance(context, dict):
            return ""

        stats = context.get("stats") if isinstance(context.get("stats"), dict) else {}
        latest_task = context.get("latest_task") if isinstance(context.get("latest_task"), dict) else None
        recent_tasks = [item for item in list(context.get("recent_tasks") or []) if isinstance(item, dict)]
        recent_failures = [item for item in list(context.get("recent_failures") or []) if isinstance(item, dict)]
        selected_tasks = [item for item in list(context.get("selected_tasks") or []) if isinstance(item, dict)]
        if not stats and latest_task is None and not recent_tasks and not recent_failures and not selected_tasks:
            return ""

        parts = [
            "Inspection context from recent platform tasks. Use it only when it helps answer the current question.",
        ]
        scope = str(context.get("scope") or "").strip()
        if scope:
            parts.append(f"scope={scope}")
        if stats:
            stat_text = ", ".join(f"{key}={value}" for key, value in stats.items() if value not in (None, "", 0))
            if stat_text:
                parts.append(f"recent_stats={stat_text}")
        if latest_task:
            parts.append(f"latest_task: {ChatExecutor._inspection_task_line(latest_task)}")
        if selected_tasks:
            parts.append("user_selected_tasks:")
            for item in selected_tasks[:6]:
                parts.append(f"- {ChatExecutor._inspection_task_line(item)}")
        items = recent_failures[:2] if recent_failures else recent_tasks[:4]
        if items:
            parts.append("recent_tasks:")
            for item in items:
                parts.append(f"- {ChatExecutor._inspection_task_line(item)}")
        return "\n".join(parts)

    @staticmethod
    def _inspection_task_line(item: dict[str, Any]) -> str:
        fields: list[str] = []
        for key in (
            "task_id",
            "product_id",
            "spec_code",
            "status",
            "verdict",
            "risk_level",
            "overall_score",
            "prompt_version",
            "trace_id",
            "created_at",
        ):
            value = item.get(key)
            if value not in (None, "", []):
                fields.append(f"{key}={value}")
        failed_rules = [str(rule) for rule in list(item.get("failed_rules") or []) if str(rule).strip()]
        if failed_rules:
            fields.append(f"failed_rules={'; '.join(failed_rules[:3])}")
        root_cause = str(item.get("root_cause") or "").strip()
        if root_cause:
            fields.append(f"root_cause={root_cause[:180]}")
        return ", ".join(fields)

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
    def _observation_metadata(state: ManagerState) -> dict[str, Any]:
        return {
            "surface": state.surface,
            "source_type": "chat",
            "org_id": state.org_id,
            "session_id": state.session_id,
            "assistant_message_id": state.assistant_message_id,
            "workflow_run_id": state.workflow_run_id,
        }

    @staticmethod
    def _record_llm_meta(state: ManagerState, response: dict[str, Any] | None) -> None:
        if not isinstance(response, dict):
            return
        meta = dict(response.get("__meta__") or {})
        if not meta:
            return
        state.llm_metas.append(meta)

        usage = LLMClient._normalize_usage(meta.get("usage"))
        if not usage:
            return
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        if total_tokens <= 0:
            return

        runtime = state.manager_model_runtime or {}
        pricing = dict(meta.get("pricing") or {})
        input_price = pricing.get("input_price_per_million")
        output_price = pricing.get("output_price_per_million")
        if input_price is None:
            input_price = runtime.get("input_price_per_million")
        if output_price is None:
            output_price = runtime.get("output_price_per_million")

        langfuse_meta = dict(meta.get("langfuse") or {})
        model_key = str(meta.get("model") or runtime.get("model_id") or "unknown")
        trace_id = str(
            langfuse_meta.get("trace_id")
            or state.trace_id
            or state.workflow_run_id
            or state.request_id
            or ""
        ).strip() or None
        observation_id = str(langfuse_meta.get("observation_id") or "").strip() or None
        event_key = str(meta.get("id") or observation_id or f"{model_key}:{len(state.llm_usage_events)}")
        if any(item.get("event_key") == event_key for item in state.llm_usage_events):
            return

        state.llm_usage_events.append(
            {
                "event_key": event_key,
                "model_key": model_key,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_amount": ModelPricing.estimate_cost(
                    model_key,
                    prompt_tokens,
                    completion_tokens,
                    input_price_per_million=float(input_price) if input_price is not None else None,
                    output_price_per_million=float(output_price) if output_price is not None else None,
                ),
                "trace_id": trace_id,
                "observation_id": observation_id,
            }
        )

    @staticmethod
    def _build_fallback(state: ManagerState) -> str:
        if state.errors or state.missing_inputs:
            return "模型暂不可用，无法完成请求。请检查后台模型配置。"
        rag_context = ChatExecutor._rag_prompt_context(state)
        if rag_context and state.selected_rag_space:
            if "未检索到可用片段" in rag_context:
                return "当前选中的知识库没有检索到可用于回答该问题的依据。"
            return rag_context[:500]
        if state.observations:
            for obs in reversed(state.observations):
                if obs.summary and obs.capability_key != "chat.response.compose":
                    return obs.summary[:500]
        return "模型暂不可用，请稍后重试或检查后台配置。"
