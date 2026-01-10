# EthelFlow

## Big picture

EthelFlow is a **LangGraph-based orchestration service** that runs *flows* (small, explicit state machines) which call a set of **agent microservices** (chunking, embeddings, reasoning, code execution, storage/retrieval, etc.). It also provides an **asset store** with:

- **S3-compatible object storage** (MinIO in local k8s) for file bytes
- **Postgres metadata + indexing** for versioned documents, extracted text, chunks, and embeddings

At runtime, routing to models is **catalog-driven**:

- A **model catalog YAML** defines **providers**, **tenants**, embedding **spaces**, and inference **classes**
- Flows and agents pass `tenant` (and optionally `embedding_space` / `inference_class`) so the system can pick the right provider/deployment and storage tables.

---

## Repository structure (high level)

- `ethelflow/` — the main FastAPI service (routes, flows, DB models, catalog loader)
- `ethelflow/agents/` — node adapters + per-agent microservice implementations
- `k8s/` — Kubernetes manifests (Deployments/Services/ConfigMaps/Secrets)
- `k8s/model_catalog.yaml` — **source of truth** for embedding spaces + tenant routing (typically packaged as a ConfigMap)

---

## Development

Use `uv` for managing the project Python virtual environment.

- Upgrading dependencies (respects semver ranges in `requirements.txt`):  
  `uv pip compile requirements.txt -o requirements_lock.txt --generate-hashes`
- Creating venv:  
  `uv venv .venv`

---

## Local setup

### Prerequisites

- Container runtime (Docker, etc.) installed and running
- A local Kubernetes cluster (Docker Desktop, minikube, microk8s, etc.)
- `kubectl` access to the cluster (or `microk8s kubectl`)
- Azure OpenAI API key(s) (see model catalog + secrets below)

### Deployment

Build the main service image from the repo root:

```bash
docker build -f ethelflow.Dockerfile -t ethelflow:latest .
```

Create the Azure OpenAI key secret manifest:

```bash
./scripts/make_azure_openai_secret.sh <secret-value>
```

Deploy everything into your cluster:

```bash
kubectl apply -f k8s/
```

This typically creates:

- Main `ethelflow` application service
- Agent services (e.g., `chunk-text`, `embedding`, `executor`, `file-to-text`, `reasoning`, `store-chunks`, `store-vectors`, etc.)
- PostgreSQL (main application DB) and MinIO (S3-compatible storage)

---

## Usage (port-forwarding)

Expose services to `localhost`:

```bash
kubectl port-forward svc/ethelflow 8080:8080
kubectl port-forward svc/postgres 5432:5432
```

Optionally, port-forward an agent directly if you want to test it in isolation:

```bash
kubectl port-forward svc/executor 8000:8000
# adjust service name/port for other agents
```

Open:

- Swagger UI: `http://localhost:8080/docs`
- Rendered service README: `http://localhost:8080/`

---

## Calling the main service

### Run a flow (single request)

`POST /flow` runs the flow and returns either the first output (non-streaming) or a streaming response (streaming mode).

Example:

```bash
curl -X POST "http://localhost:8080/flow" \
  -H "Content-Type: application/json" \
  -d '{
    "flow": "rag_chat",
    "tenant": "ethz",
    "context": {
      "prompt": "Summarize the key idea.",
      "document_ids": ["8fba5e0d-f076-4688-aa62-d2321dc0b871"],
      "top_k": 8
    },
    "stream": false
  }'
```

### Start/attach/continue flows (interactive runs)

Some flows may **interrupt** and require input later (LangGraph `interrupt(...)` + checkpointer).

1) Start the flow:

```bash
curl -X POST "http://localhost:8080/flow/start" \
  -H "Content-Type: application/json" \
  -d '{
    "flow": "quiz",
    "tenant": "ethz",
    "context": {"topic": "Gauss\u0027s law"},
    "stream": true
  }'
```

Response includes a `run_id`.

2) Attach via SSE:

```bash
curl -N "http://localhost:8080/flow/<run_id>/attach"
```

3) Continue after an interrupt:

```bash
curl -X POST "http://localhost:8080/flow/<run_id>/continue" \
  -H "Content-Type: application/json" \
  -d '{
    "data": "My answer goes here",
    "stream": false
  }'
```

(Exact continuation payload depends on how the flow calls `interrupt(...)`.)

---

## Assets API (upload/download/versioning)

EthelFlow exposes a **logical, versioned filesystem** under `/{tenant}/{collection}/{subpath...}/{filename}`.

- Upload creates a new version unless you request an explicit version like `foo.2.pdf`
- The bytes are stored in S3/MinIO under a UUID key
- Postgres stores `assets` and `etheldocuments` metadata; `assets.latest_document_id` points to the newest version

### Upload

`POST /assets?path=/tenant/collection/.../file.pdf`

```bash
curl -X POST "http://localhost:8080/assets?path=/ethz/physics/mechanics/angular.pdf" \
  -F "file=@angular.pdf"
```

### Download latest

```bash
curl -L "http://localhost:8080/assets?path=/ethz/physics/mechanics/angular.pdf" -o angular.pdf
```

### Download a specific version

```bash
curl -L "http://localhost:8080/assets?path=/ethz/physics/mechanics/angular.2.pdf" -o angular.2.pdf
```

### List directories

```bash
curl "http://localhost:8080/assets/ls?path=/ethz/physics"
```

---

## Model catalog + tenant routing

### What the model catalog does

The model catalog YAML is the **contract** that ties together:

- **Tenants** (e.g., `ethz`)
- **Embedding spaces** (dimension + DB table where vectors are stored)
- **Inference classes** (e.g., `"reasoning"`) and the provider/deployment to use per tenant
- **Providers** (endpoint + “kind”), with API keys supplied via environment variables/secrets (not stored in the YAML)

In the running cluster, the catalog is typically mounted into each service at:

- `/etc/ethelflow/catalog.yaml`

and pointed to by:

- `ETHELFLOW_MODEL_CATALOG_PATH=/etc/ethelflow/catalog.yaml`

Flows (and most agents) must include **`tenant`** in the state/context so routing works.

---

## Updating embedding tables (from the model catalog)

Embedding storage is **catalog-driven**: each embedding space declares a `store.table` name.
When you add a new embedding space (or change the table name), you must ensure Postgres has the matching table + vector index.

This repo includes:

- `update_embedding_dbs.py` — generates an Alembic revision that creates any *missing* embedding tables from the catalog.

### When do you need this?

Run it when:

- You add a new embedding space to `k8s/model_catalog.yaml` (`embeddings.spaces.*`)
- You change `store.table` for an existing space
- You want to switch indexing strategy (HNSW vs IVFFlat) for newly created tables

### What the script does

`update_embedding_dbs.py`:

1. Reads the catalog from `k8s/model_catalog.yaml`  
   (supports both “raw catalog.yaml” and “ConfigMap-wrapped” YAML containing `data: { catalog.yaml: ... }`)

2. Extracts each embedding space tuple: `(space_name, dimension, store.table)`

3. Connects to Postgres (unless `--no-db-check`) and checks whether each table exists

4. Generates a **new Alembic revision** to create missing tables + indexes
   - Always ensures `CREATE EXTENSION IF NOT EXISTS vector`
   - Index strategy:
     - `dimension <= 2000`: normal pgvector ANN opclasses on `vector`
     - `dimension > 2000`: expression index using `vector::halfvec(dim)` with `halfvec_*_ops`
       (workaround for ANN index dimensionality limits)

### Typical workflow

1) Edit `k8s/model_catalog.yaml` and add or modify an embedding space, e.g.:

```yaml
embeddings:
  spaces:
    ada3_large:
      dimension: 3072
      store:
        table: embeddings_ada3_large
```

2) Ensure Postgres is reachable. If you’re running locally:

```bash
kubectl port-forward -n default svc/postgres 5432:5432
```

3) Generate the Alembic revision:

```bash
./update_embedding_dbs.py
```

Optional flags:

- Use a specific host/port:
  ```bash
  ./update_embedding_dbs.py --host localhost --port 5432
  ```
- Choose index kind:
  ```bash
  ./update_embedding_dbs.py --index hnsw
  ./update_embedding_dbs.py --index ivfflat --lists 200
  ./update_embedding_dbs.py --index none
  ```
- Choose distance metric:
  ```bash
  ./update_embedding_dbs.py --distance cosine
  ./update_embedding_dbs.py --distance l2
  ```
- Skip DB existence checks (generate for all catalog spaces):
  ```bash
  ./update_embedding_dbs.py --no-db-check
  ```

4) Review the generated revision file under the Alembic versions directory, then apply:

```bash
alembic upgrade head
```

### How DB credentials are discovered

The script uses (in order):

1. `--database-url` or `DATABASE_URL`
2. `ETHELFLOW_POSTGRES_*` / `POSTGRES_*` environment variables
3. Otherwise it tries to read a Kubernetes Secret (defaults: `-n default secret/postgres-secret`)
   - keys: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

If Postgres is not reachable, it prints a port-forward hint and exits.

---

## Notes for developers

- **Flows** are orchestration: they wire node adapters together and must pass routing keys (`tenant`, optional `embedding_space`, optional `inference_class`).
- **Agents** do the work: chunking, embeddings, reasoning, storage, retrieval. Most are deployed as separate k8s Services.
- **Embedding tables** are not “static schema”: they are derived from the catalog, so keep Alembic + the catalog in sync.

---

## Alembic migrations (general)

The embedding-table generator produces an Alembic revision. Beyond that, normal schema changes follow standard Alembic workflows:

```bash
alembic revision -m "..."
alembic upgrade head
```
