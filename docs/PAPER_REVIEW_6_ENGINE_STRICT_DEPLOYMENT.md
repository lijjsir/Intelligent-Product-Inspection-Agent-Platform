# Paper Review Strict Deployment

This document describes the current strict paper-review runtime. The Chinese
correction layer is provided by macro_correct token and macro_correct punct.

## Required Engines

- enhanced DOCX/PDF parser: `python-docx`, `lxml`, `PyMuPDF`
- macro_correct token: Chinese spelling and wording suggestions
- macro_correct punct: Chinese punctuation suggestions
- LanguageTool: grammar and language-rule checks
- Vale: writing-style checks
- AI Review and report generation: final review card and downloadable report

The runtime is strict. If any required engine is unavailable, paper review must
fail with `paper_review_error_v1`; it must not return rule-only results as a
successful report.

## Model Assets

Host paths:

```text
.runtime/paper-assets/macro_correct/token/
.runtime/paper-assets/macro_correct/punct/
```

Container paths:

```text
/opt/piap-paper-assets/macro_correct/token/
/opt/piap-paper-assets/macro_correct/punct/
```

Required environment:

```text
PIAP_PAPER_CHECK_MACRO_CORRECT_TOKEN_CONFIG=/opt/piap-paper-assets/macro_correct/token/csc.config
PIAP_PAPER_CHECK_MACRO_CORRECT_PUNCT_CONFIG=/opt/piap-paper-assets/macro_correct/punct/sl.config
PIAP_PAPER_CHECK_LANGUAGETOOL_URL=http://languagetool:8010
PIAP_PAPER_CHECK_VALE_BIN=/usr/local/bin/vale
PIAP_PAPER_CHECK_ENGINE_TIMEOUT_SEC=60
PIAP_PAPER_CHECK_MACRO_CORRECT_BATCH_SIZE=8
PIAP_PAPER_REVIEW_TASK_SOFT_TIME_LIMIT_SEC=840
PIAP_PAPER_REVIEW_TASK_TIME_LIMIT_SEC=900
PIAP_CHAT_STREAM_TOKEN_TTL_SEC=900
```

Download and verify assets:

```bash
docker compose --profile paper-check up paper-assets-init
```

## Runtime Flow

1. The API process creates the user message, assistant placeholder, and
   `workflow_run_id`, then enqueues the paper-review workflow to the
   `paper_review` Celery queue.
2. The dedicated paper worker performs runtime checking, parsing, required
   text-engine checks, AI Review, and report generation.
3. Progress is written to the same assistant message and emitted over SSE.
4. `message_final` is emitted only after final success or failure.

The normal Celery worker should listen to the default queue. The paper worker
should listen only to `paper_review` with concurrency 1, prefetch 1, and
`max-tasks-per-child=1`.

## Acceptance Checks

- `/api/v1/paper-review-runtime/health?load_models=true` returns only the
  current required engine names.
- `/api/v1/health/live` remains responsive while a large paper-review job runs.
- Normal pages continue to load `/users/me`, sessions, tasks, results, and
  inspection specs while paper review is running.
- A missing required engine produces `paper_review_error_v1` with the missing
  engine details.
- A successful run produces a paper-review card and report download links.
