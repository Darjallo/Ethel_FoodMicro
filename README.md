# EthelFlow

## Development

Use `uv` for managing the project Python virtual environment.

- Upgrading dependencies (respects semver ranges in `requirements.txt`): `uv pip compile requirements.txt -o requirements_lock.txt --generate-hashes`
- Creating venv: `uv venv .venv`

## Local setup

### Prerequisites

- You have container runtime (e.g. Docker) installed and running
- You have a local Kubernetes cluster (Docker Desktop, minikube, microk8s, etc. should all work fine)
- Ensure that you can access your Kubernetes cluster with `kubectl`
- Ensure you have the Azure OpenAI service credentials and replace them with the placeholders in `k8s/embedding.yaml` and `k8s/reasoning.yaml`

### Deployment

You need to build the container image first, from the root of this repository, run `docker build -f ethelflow.Dockerfile -t ethelflow:latest .`

Using `kubectl` pointed to your local cluster, run `kubectl apply -f k8s/` from the root of this repository. This should create the following resources:

- Main `ethelflow` application
- Agents (currently `chunk-text`, `embedding`, `executor`, `file-to-text`, `reasoning`, `store-chunks`, `store-vectors`)
- PostgreSQL (main application database) and Minio (S3-compatible object storage for assets)

## Usage

Use port-forwarding feature of `kubectl` to expose the applications running in your local cluster to your `localhost`:

- `kubectl port-forward svc/ethelflow 8080:8080` (for `ethelflow`)
- `kubectl port-forward svc/executor 8000:8000` (for direct interaction with `executor` agent, adjust for other)
- `kubectl port-forward svc/postgres 5432:5432` (for Postgres, required to run Alembic migrations if necessary)

### Main EthelFlow application

- Running a flow:

```
curl -X POST "http://localhost:8080/flow" -H "Content-Type: application/json" -d '{"flow": "reasoning_test", "tenant": "ethz", "context": {"document_id": "8fba5e0d-f076-4688-aa62-d2321dc0b871", "prompt": "Can you please tell me what is the significance of this molecule in our society?", "reasoning_effort": "high", "stream": true, "content_type": "image/png", "deployment": "Ethel_o4_mini"}}'
```

- Creating an `etheldocument` (file from the current working directory, title is URL-encoded):

```
curl -X POST "http://localhost:8080/documents?title=grading" -F "file=@grading.png"
```

## Alembic migrations

TODO
