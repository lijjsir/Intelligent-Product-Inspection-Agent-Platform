# macro-correct local model assets (legacy dev-only path)

For local non-container development, you may place model files here for quick testing.
However, the recommended approach per PAPER_REVIEW_6_ENGINE_STRICT_DEPLOYMENT.md is:

- **Host**: `.runtime/paper-assets/macro_correct/token/` and `punct/`
- **Container**: `/opt/piap-paper-assets/macro_correct/token/` and `punct/`

Models are downloaded by the `paper-assets-init` service (profile: `paper-check`) via:
```
docker compose --profile paper-check up paper-assets-init
```

The application reads models from paths configured via:
- `PIAP_PAPER_CHECK_PYCORRECTOR_MODEL_DIR=/opt/piap-paper-assets/macro_correct/token`
- `PIAP_PAPER_CHECK_MACRO_CORRECT_TOKEN_CONFIG=/opt/piap-paper-assets/macro_correct/token/csc.config`
- `PIAP_PAPER_CHECK_MACRO_CORRECT_PUNCT_CONFIG=/opt/piap-paper-assets/macro_correct/punct/sl.config`

Do NOT place large model files (pytorch_model.bin, etc.) in this directory —
they belong in `.runtime/paper-assets/` (gitignored, dockerignored).
