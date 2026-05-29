# macro-correct local model assets

For local, non-container runs, place the `macro-correct` model files here so paper review engines are usable at runtime without downloading from external model hubs.

Docker builds download these assets into `/opt/piap-paper-assets`, because `docker-compose.yml` bind-mounts `./backend` over `/app/backend` during development.

Expected layout:

```text
backend/agent/tools/assets/macro_correct/
  token/
    csc.config
    pytorch_model.bin
  punct/
    sl.config
    pytorch_model.bin
```

The application treats these as required assets when `PIAP_PAPER_CHECK_MACRO_CORRECT_ENABLED=true`.
