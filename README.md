# Project Ethel  
## Flow Manager  

> **Flow Manager** is a lightweight orchestration layer for executing multi-step “flows” of micro-services (agents). It offers both streaming and non-streaming modes, mimicking the OpenAI Chat Completion API pattern, and is fully extensible via custom flows and agents.

## Table of Contents

1. [Overview](#overview)  
2. [Getting Started](#getting-started)  
3. [Flow Manager API](#flow-manager-api)  
4. [Asset Management](#asset-management)  
5. [Flows](#flows)  
6. [Agents](#agents)  
7. [Hot-Reloading Flows](#hot-reloading-flows)  
8. [Docker & Deployment](#docker--deployment)  
9. [Extending with New Flows & Agents](#extending-with-new-flows--agents)  
10. [Example: `test_flow` & `test_agent`](#example-test_flow--test_agent)  
11. [License](#license)  

---

## Overview

The Flow Manager exposes two endpoints:

- **POST /**: invoke a flow  
- **POST /upload**: upload a binary asset into MongoDB/GridFS  
- **GET /files/**: list collections, directories, or fetch files

Each flow is defined as a small DAG of “nodes” via [langgraph], and each node invokes an external micro-service (“agent”).  

## Getting Started

```bash
git clone <repo>
cd ethelflow
pip install -r flow_manager/requirements.txt
# build & tag your Docker images
docker-compose up --build
```

## Flow Manager API

### Invoke a Flow

```http
POST / HTTP/1.1
Content-Type: application/json

{
  "flow": "test_flow",
  "context": { "courseID":"CS101", "userID":"alice" },
  "query": { /* flow-specific params */ },
  "stream": true|false,        # defaults to false
  "flow_reload": true|false    # hot-reload your flow module
}
```

- **Non-streaming** (`stream=false`): returns a single JSON object (final state).  
- **Streaming** (`stream=true`): returns a chunked response; each chunk is a JSON update for a node.  

### Upload Assets

```http
POST /upload
Content-Type: multipart/form-data

Fields:
  - file: binary file  
  - collection: e.g. courseID or document set  
  - path: full relative path, e.g. "lectures/week1/slides.pdf"
```

Stores in MongoDB/GridFS under the given metadata. Re-uploading the same collection+path replaces the old file.

### List & Fetch Assets

- **List collections**: `GET /files`  
- **List directory**: `GET /files/{collection}/{optional_path}`  
- **Fetch file**: `GET /files/{collection}/{path_to_file}`  

Directory listing returns JSON:
```json
[
  { "type":"collection","name":"CS101" },
  …
]
```
or
```json
[
  { "type":"directory","name":"week1" },
  { "type":"file","name":"slides.pdf" }
]
```
Fetching a file returns the raw bytes with correct `Content-Type`.

## Asset Management

Assets live in MongoDB/GridFS, keyed by `metadata.collection` and `metadata.path`. The Flow Manager’s `asset_handler.py` encapsulates:

- upload: replace-old + store  
- listing: collection & directory traversal  
- file serving with MIME detection  

## Flows

Flows reside in `flow_manager/flows/`. Each flow module:

- Defines a TypedDict schema for its state  
- Builds a DAG via `StateGraph` (add_node/add_edge)  
- Exposes `run(context, query={}, stream=False)` as a generator

## Agents

Agents live in `agent_pool/agents/<agent_name>/`. Each directory contains:

- `agent.py`: HTTP server implementing `handle(request)` and optional `stream(request)`  
- `node_adapter.py`: client adapter invoked by Flow Manager  

Agents follow an OpenAI-like pattern:
- non-stream: return one JSON  
- stream: yield newline-joined JSON chunks

## Hot-Reloading Flows

Send `"flow_reload": true` in your POST body to force the Flow Manager to `importlib.reload(...)` your flow module before invocation. Great for rapid development without restarting the server.

## Docker & Deployment

A sample `docker-compose.yml` sets up:
- `flow_manager` service  
- your agents (e.g. `test_agent`)  
- MongoDB (with GridFS)  
- Milvus for embeddings  

Mount your local `flow_manager/flows` directory into the container for hot-updates:

```yaml
volumes:
  - ./flow_manager/flows:/app/flows:ro
```

## Extending with New Flows & Agents

### Add an Agent

1. Create `agent_pool/agents/<your_agent>/agent.py` with `handle` and/or `stream`.  
2. Create `agent_pool/agents/<your_agent>/node_adapter.py` to call your HTTP endpoint.  

### Add a Flow

1. In `flow_manager/flows/`, create `<your_flow>.py` and implement `run(...)`.  
2. Register your node-adapters in `flow_manager/flows/nodes.py`.  

Reinvoke flows with `"flow_reload": true` to pick up changes without restarting.

## Example: `test_flow` & `test_agent`

- **test_flow**: a one-node flow calling `test_agent`.  
- **test_agent**: echoes back with a timestamp; supports both streaming (char-by-char) and non-streaming.  

Use these as templates.

## License

```
# Project Ethel
# Flow Manager
#
# Copyright (C) 2025  Gerd Kortemeyer, ETH Zurich
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
```  
