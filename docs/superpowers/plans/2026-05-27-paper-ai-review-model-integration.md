# Paper Ai-Review Model Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the paper-review report files use the Ai-Review model output generated from the Review Evidence Pack before reports are saved.

**Architecture:** Keep deterministic parsing and rule checks in `paper_format_checker`, then add a focused AI review module that selects a configured chat runtime, sends the Review Evidence Pack with `chat.paper_format_check.system`, parses the JSON response, and stores it as `ai_review_output`. `FileExecutor` calls this module before `paper_review_report_builder` saves Markdown/DOCX/PDF files, with a fallback report when no model is configured.

**Tech Stack:** Python, pytest, existing `ModelConfigService`, `LLMGateway`, `LLMClient`, object storage service, current chat prompt resolver.

---

### Task 1: Add AI Review Module and Unit Tests

**Files:**
- Create: `backend/agent/tools/paper_review_ai.py`
- Test: `backend/tests/test_paper_review_ai.py`

- [ ] **Step 1: Write failing tests**

Create tests that monkeypatch model listing, runtime selection, and `LLMClient.chat`. Verify the module passes Review Evidence Pack content to the model and returns `answer`, `summary`, `markdown_report`, and `issues`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_paper_review_ai.py -q`
Expected: FAIL because `agent.tools.paper_review_ai` does not exist.

- [ ] **Step 3: Implement minimal module**

Implement `generate_ai_review_output(...)`, `build_ai_review_messages(...)`, and `normalize_ai_review_output(...)`. The function should return a fallback object with an `ai_review_unavailable` limitation when no runtime or model call is available.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_paper_review_ai.py -q`
Expected: PASS.

### Task 2: Call AI Review Before Saving Report Files

**Files:**
- Modify: `backend/agent/router/executors/file_executor.py`
- Test: `backend/tests/test_paper_format_manager_flow.py`

- [ ] **Step 1: Write failing flow test**

Extend the manager-flow test so the fake AI review returns a unique `markdown_report`, then verify the saved Markdown object contains that unique text and the artifact contains `ai_review_output`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_paper_format_manager_flow.py::test_manager_loop_returns_paper_format_report -q`
Expected: FAIL because `FileExecutor` currently saves fallback reports before any Ai-Review output exists.

- [ ] **Step 3: Implement FileExecutor integration**

Call `generate_ai_review_output(...)` after `review_evidence_pack` is built and before `_save_report_files(...)`. Pass `db_session`, `state.original_query`, `request.org_id`, and trace/session metadata. Merge model limitations into the report only when the model is unavailable.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_paper_format_manager_flow.py::test_manager_loop_returns_paper_format_report -q`
Expected: PASS.

### Task 3: Verify Related Paper Review Tests

**Files:**
- Test only.

- [ ] **Step 1: Run targeted backend tests**

Run: `cd backend; python -m pytest tests/test_paper_review_ai.py tests/test_paper_format_manager_flow.py tests/test_paper_format_checker.py -q`
Expected: PASS.

- [ ] **Step 2: Inspect git diff**

Run: `git diff -- backend/agent/tools/paper_review_ai.py backend/agent/router/executors/file_executor.py backend/tests/test_paper_review_ai.py backend/tests/test_paper_format_manager_flow.py`
Expected: Diff only covers Ai-Review model integration and tests.
