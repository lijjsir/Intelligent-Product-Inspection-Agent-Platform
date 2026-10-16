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
