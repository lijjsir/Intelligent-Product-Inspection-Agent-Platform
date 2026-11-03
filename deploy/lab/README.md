# Ubuntu lab deployment

This deployment exposes only the web application on TCP 8080. MySQL, Redis,
MinIO, Qdrant, Neo4j, and the backend stay inside the Docker network.

The source bundle is made with `make_bundle.py`, which selects only runtime
source and deployment files from the current working tree. It excludes local
`.env` files, private keys, bundled model weights, tests, documentation,
generated files, node modules, Git metadata, and the design preview.

## First installation

On the server, from `~/Documents/agent_project`:

```sh
sudo sh deploy/lab/install-docker-ubuntu.sh
```

Reconnect SSH so `admin2` receives the Docker group membership. Then:

```sh
sh deploy/lab/init-secrets.sh
docker load -i piap-lab-images.tar.gz
docker compose --env-file .env.lab -f compose.lab.yml config -q
docker compose --env-file .env.lab -f compose.lab.yml up -d --no-build --pull never
docker compose --env-file .env.lab -f compose.lab.yml ps
docker compose --env-file .env.lab -f compose.lab.yml exec -T backend python scripts/init_memory_qdrant.py
curl -fsS http://127.0.0.1:8080/
```

`deploy/lab/init-secrets.sh` creates `.env.lab` and the JWT key pair on the
server. Keep these files on the server and back them up separately. Add your
model provider credentials to `.env.lab` when AI features are needed, then
recreate the backend and worker containers.

The local model is not deployed. The initial setup disables model-dependent
trust scoring while model credentials remain blank.

## Connecting a local model service

Deploy the inference service separately. It must expose an OpenAI-compatible
`/v1/models` and `/v1/chat/completions` API, or `/v1/embeddings` for an embedding
model. The application does not download weights or start a GPU server when
a model configuration is saved.

In **模型配置 / Base Model 注册**, select the provider `local_openai`, enter the
exact model identifier advertised by the service, and its base URL ending in
`/v1`. Select `chat`, `multimodal` (text plus images), or `embedding`. The API
also normalizes `vision` and `vlm` to `multimodal`. The model source address
records the model ID or weight path; it is separate from the HTTP endpoint.
API Key can be blank if this particular service does not require authentication.
If authentication is enabled, use this service's actual key.

For a service running directly on the same Linux host, use
`http://host.docker.internal:11434/v1` (Ollama) or, for example,
`http://host.docker.internal:8001/v1` (a separately configured vLLM service).
The backend, worker, and beat all include the Linux `host-gateway` mapping.
The inference server must listen on an interface reachable from Docker;
host-only loopback binding cannot accept connections from bridge containers.
Restrict access to the intended network. For a service in another container on
the same network, use its service name; for another machine, use its reachable IP.
An explicit endpoint is preferable to relying on default environment values.

Existing `.env.lab` files are preserved. If necessary, set:

```dotenv
PIAP_LOCAL_OPENAI_DOCKER_BASE_URL=http://host.docker.internal:11434/v1
PIAP_LOCAL_MODEL_TIMEOUT_SEC=120
PIAP_LOCAL_MODEL_REASONING_EFFORT=none
PIAP_LOCAL_MODEL_MAX_TOKENS=2048
```

These settings do not select the business model automatically. Register and
enable it in the model configuration page. Restart/recreate application
containers after changing deployment environment or `extra_hosts` settings.
`PIAP_LOCAL_MODEL_REASONING_EFFORT=none` is intended for an Ollama service
supporting the OpenAI reasoning control. It prevents short Qwen probes from
spending their entire output budget on thinking without returning a final
answer. Leave it blank for other local servers that do not support this field.
Use a separately recorded setting when conducting thinking-mode experiments.

### Pinned native inference runtime

`python3 deploy/lab/install-ollama-user.py` installs Ollama 0.40.13 into
`~/.local/lib/piap-ollama/0.40.13`, verifies the published archive SHA256, and
creates the `piap-ollama.service` user unit. Weights are stored in
`~/ai_models/ollama`. Both NVIDIA GPUs are visible, with a single inference
slot and a 16K context. The server binds only the specified Docker bridge
address (default `172.17.0.1:11434`), not the public LAN interface. Check the
host's Docker bridge address before installing.

The installer uses a temporary archive and removes it after extraction. It can
also consume a verified `--archive` copied from another computer. It does not
alter NVIDIA drivers, Conda, system curl, or experimental training environments.
Persistent runtime files, weights, and the service unit are required deployment
assets, not temporary files. Check the final `linger_configured` result: if
false, an administrator must enable lingering for the deployment user to start
its user service at boot without an interactive login.

Download and inspect the selected model with the installed binary:

```sh
export OLLAMA_HOST=http://172.17.0.1:11434
~/.local/lib/piap-ollama/0.40.13/bin/ollama pull qwen3.5:9b-q8_0
~/.local/lib/piap-ollama/0.40.13/bin/ollama list
~/.local/lib/piap-ollama/0.40.13/bin/ollama ps
```

**检测** now sends an actual small request for local models: text generation,
image input for multimodal models, or an embedding request. It is no longer
enough for the model's name to appear in `/models`. **接入验证** provides separate
checks for text, strict JSON output, an embedded test image, OpenAI tool calls,
and embeddings. It uses synthetic data, executes no business tools, and writes
no vectors. Some checks may fail on otherwise usable models that lack a
particular capability. Results validate protocol compatibility, not task accuracy.
The packaged web proxy allows 660 seconds for a response so a sequence of
local capability checks is not cut off by the previous 300-second proxy limit.

Before switching embedding models, migrate/rebuild the corresponding indexes;
equal vector dimensions alone do not make embeddings from different models
compatible. Capability checks only report the returned dimension and never
recreate existing collections.

The application URL is `http://<server-lan-ip>:8080/`. The first registered
user becomes the administrator of the new organization. Keep the port limited
to the intended lab network using the server's network policy.

## Updating

Create a new source bundle locally and extract it over the deployment directory.
The generated `.env.lab`, `deploy/lab/secrets`, and Docker volumes must remain
in place. Build and transfer new application images from the local computer,
load them on the server, then run:

```sh
docker compose --env-file .env.lab -f compose.lab.yml up -d --no-build --pull never
docker compose --env-file .env.lab -f compose.lab.yml ps
```

Never use `docker compose down -v` for a routine update; that removes the
persistent database and object storage volumes.

## Verified local model integration (2026-11-03)

The live deployment was verified with Ollama 0.40.13 and
`qwen3.5:9b-q8_0`, using two RTX 3060 12GB GPUs, a 16K context and one
inference slot. Text generation, strict JSON, image input and OpenAI tool-call
responses passed through the platform's authenticated verification API. The
application client returned `703` for `37*19` and correctly distinguished two
synthetic red/blue images. The algorithm engineer model configuration page
was checked against the live API without page errors.

These are protocol and basic functionality checks, not industrial accuracy or
concurrency benchmarks. The existing embedding configuration remains separate.
Actual fine-tuning still requires a training environment and real command
templates; installing an inference model alone does not configure training.

Keep machine-specific addresses, account details and private backup locations
in an internal operations record rather than publishing them with source code.

### Optional direct LAN API

Use the separate `compose.model-api.yml` gateway for applications on other
trusted LAN computers. Build `Dockerfile.model-api` from an existing local
PIAP web image using `--build-arg PIAP_WEB_BASE_IMAGE=<existing-web-image>`;
this requires no new runtime or GPU packages. Set `PIAP_MODEL_LAN_ADDRESS` to
the server's private LAN IP and start the gateway with Compose's `--env-file`
and `-f deploy/lab/compose.model-api.yml`. The internal Ollama service and
platform containers remain unchanged.

Clients use `http://<this-server-private-ip>:11434/v1`, model
`qwen3.5:9b-q8_0`, and `/chat/completions`. The gateway forwards only model
listing, chat completions and embeddings; native Ollama management routes are
not exposed. No additional API key is configured; SDKs requiring one may use
a local placeholder. For Qwen direct responses, set `reasoning_effort: none`.
The gateway is for the trusted LAN and is not intended for public forwarding.
