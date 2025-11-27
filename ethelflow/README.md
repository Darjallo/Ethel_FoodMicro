```txt
# Project Ethel
# Node adapter for semantically chunking text
#
# Copyright (C) 2025  Gerd Kortemeyer, ETH Zurich
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
```

# ETHEL Flow

## main.py

```py
@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_checkpointer()
    await s3_manager.init()
    yield
    await s3_manager.close()
    await teardown_checkpointer()


app = FastAPI(lifespan=lifespan)
app.include_router(docs_router)
app.include_router(flows_router)
```

### Checkpointer Initialization

We use a custom `__init_checkpointer()` function to set up global checkpointing resources for the application.

1. **Async Connection Pool**
   We create an `AsyncConnectionPool` using the database URL provided by `postgres_settings` (e.g. `postgresql+asyncpg://user:password@host:5432/ethelflow/`).
   This pool manages all async PostgreSQL connections used for checkpointing.

2. **Async Postgres Saver**
   A `AsyncPostgresSaver` is initialized, which allocates and manages the required checkpointing tables in Postgres.
   This saver is responsible for writing and restoring LangGraph checkpoints.

3. **Global App State**
   Both objects are then stored on the FastAPI application instance:

   - `app.state.checkpointer` → the `AsyncPostgresSaver`
   - `app.state.checkpointer_pool` → the `AsyncConnectionPool`

   Storing them on `app.state` makes these components globally accessible throughout the application lifecycle without re-initializing them.

### S3 Manager

The `s3_manager` is initialized at startup and provides a shared interface for interacting with our S3-compatible storage. It handles tasks such as `uploading, downloading, and deleting assets`. By initializing it once and exposing it through the application, all routes and services can reliably access S3 without re-creating clients.

## routes/docs.py

`docs.py` defines the API endpoints for document handling. It validates uploaded files, detects their MIME type, uploads file bytes to S3 via `s3_manager`, and writes the associated metadata to PostgreSQL using the `EthelDocument` ORM model. All routes in this module are grouped under the `/docs` prefix and are connected to the main application through `app.include_router(docs_router)`.

```py
router = APIRouter(prefix="/docs", tags=["docs"])

@router.post("")
async def create_document(
    title: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    data = BytesIO(await file.read())
    object_name = str(uuid.uuid4())

    mime = magic.Magic(mime=True)
    content_type = mime.from_buffer(data.getvalue())

    await s3_manager.upload_file(data, object_name)

    # save the document to DB
    try:
        document = EthelDocument(id=object_name, title=title, content_type=content_type)
        session.add(document)
        await session.commit()
        await session.refresh(document)
        return document
    except Exception as e:
        # If DB operation fails, try to clean up the orphaned S3 object.
```

> Body parameter

```yaml
file: string
```

**Key steps:**

1. **Read file bytes**
   The uploaded file is read into memory (`BytesIO`) to allow MIME detection and S3 upload.

2. **Generate object ID**
   A UUID is created and used as the S3 object key and database primary key.

3. **Detect MIME type**
   `python-magic` inspects the raw bytes to determine the real content type (e.g., `application/pdf`, not based on extension).

4. **Upload to S3**
   The file is uploaded through the project’s `s3_manager`, which handles the storage backend.

5. **Persist metadata**
   An `EthelDocument` record is created and saved using an async SQLAlchemy session.
   Stored fields include:

   - `id` (UUID / S3 key)
   - `title` (user-provided)
   - `content_type` (detected MIME)

6. **Error handling**
   If database commit fails, the code attempts to clean up the previously uploaded S3 object to prevent orphaned files.

<h3 id="create_document_docs_post-parameters">Parameters</h3>

| Name  | In    | Type           | Required | Description |
| ----- | ----- | -------------- | -------- | ----------- |
| title | query | string         | true     | none        |
| body  | body  | string(binary) | true     | none        |

<h3 id="create_document_docs_post-responses">Responses</h3>

| Status | Meaning                                                                  | Description         | Schema                                            |
| ------ | ------------------------------------------------------------------------ | ------------------- | ------------------------------------------------- |
| 200    | [OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)                  | Successful Response | Inline                                            |
| 422    | [Unprocessable Entity](https://tools.ietf.org/html/rfc2518#section-10.3) | Validation Error    | [HTTPValidationError](#schemahttpvalidationerror) |

<h3 id="create_document_docs_post-responseschema">Response Schema</h3>

<aside class="success">
This operation does not require authentication
</aside>

### Endpoint Example - how to upload a document

The following example shows how to call the `POST /docs` endpoint from a frontend client.
The request must be sent as `multipart/form-data` and include both **required** fields: `title` and `file`.

```ts
async function uploadDocument() {
  const fileInput = document.querySelector("#file");
  const file = fileInput.files[0];

  const formData = new FormData();
  formData.append("title", "My Document");
  formData.append("file", file);

  const res = await axios.post("http://localhost:8000/docs", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
```

## routes/flows.py

This module defines all endpoints related to **LangGraph flows**, which represent the execution of AI agent graphs.
A _flow_ can:

- start running immediately
- pause while waiting for user input
- resume from a saved checkpoint
- stream intermediate updates
- store and restore state using Postgres-based checkpointing

All endpoints in this module are mounted into the main application via:

```python
app.include_router(flows_router)
```

The module contains **six endpoints**: **three POST** and **three GET**:

- The **POST** endpoints perform actions that _start_, _run_, or _continue_ a flow.
  They all use one of two request models:

  - **`FlowRequest`** — used when starting or running a **new** flow
  - **`FlowContinueRequest`** — used when **continuing** a paused flow that is waiting for user input

  When a POST endpoint uses **`FlowRequest`**, the signature looks like:

  ```python
  flow_request: FlowRequest
  checkpointer = Depends(get_checkpointer)
  ```

  When a POST endpoint uses **`FlowContinueRequest`**, it includes:

  ```python
  run_id: UUID
  flow_request: FlowRequest
  checkpointer = Depends(get_checkpointer)
  ```

  This is required to identify which existing flow run should be resumed.

- The **GET** endpoints are read-only and return information about an existing flow run — its status, full checkpoint history, or live streamed updates.

  For most GET endpoints, the signature are:

  ```python
  run_id: UUID
  checkpointer: AsyncPostgresSaver = Depends(get_checkpointer)
  ```

  These parameters allow the endpoint to identify the flow run and load its state from the Postgres-backed checkpoint system.

  The **only exception** is:

  - **`GET /{run_id}/attach`** — this endpoint **does not** use the checkpointer.
    It streams live updates via SSE and does not need to read or restore checkpoints.

# POST Endpoints

## 1. `POST /flow`

Execute a flow to completion in a single request.

### Paramenters

| Name | In   | Type        | Required | Description |
| ---- | ---- | ----------- | -------- | ----------- |
| body | body | FlowRequest | true     | none        |

### Request Body (FlowRequest)

```json
{
  "flow": "flow_name",
  "tenant": "tenant_id",
  "context": {
    "key": "value"
  },
  "stream": false
}
```

#### Field Descriptions

- **flow** (string, required): Name of the flow to execute.
- **tenant** (string, required): Tenant identifier.
- **context** (object, optional): Context data for the flow.
- **stream** (boolean, optional, default `false`): Whether to stream the response.

### Response

| Status | Meaning                                                                  | Description         | Schema                                            |
| ------ | ------------------------------------------------------------------------ | ------------------- | ------------------------------------------------- |
| 200    | [OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)                  | Successful Response | Inline                                            |
| 422    | [Unprocessable Entity](https://tools.ietf.org/html/rfc2518#section-10.3) | Validation Error    | [HTTPValidationError](#schemahttpvalidationerror) |

`(stream = false)`
Returns the first output produced by the flow:

```json
{
  "run_id": "uuid",
  "status": "running or completed",
  "output": {},
  "metadata": {}
}
```

`(stream = true)`
Returns a StreamingResponse (`application/json`) that emits a sequence of JSON update objects:

```json
{
  "run_id": "uuid",
  "event": "update",
  "data": {}
}
```

Notes:

- run_id — the flow's thread ID
- status — flow status at the moment of the first output
- output — the flow’s first emitted result
- metadata — flow-specific metadata (timestamps, checkpoint info, etc.)

### Axios Example

```js
axios.post("/flow", {
  flow: "flow_name",
  tenant: "tenant_id",
  context: { key: "value" },
  stream: false,
});
```

<h3 id="attach_flow__run_id__attach_get-responseschema">Response Schema</h3>

<aside class="success">
This operation does not require authentication
</aside>

## 2. `POST /flow/start`

Start a new flow run.

### Parameter

| Name | In   | Type        | Required | Description |
| ---- | ---- | ----------- | -------- | ----------- |
| body | body | FlowRequest | true     | none        |

### Request Body (FlowRequest)

```json
{
  "flow": "flow_name",
  "tenant": "tenant_id",
  "context": {
    "key": "value"
  },
  "stream": false
}
```

### Response

| Status | Meaning                                                                  | Description         | Schema                                            |
| ------ | ------------------------------------------------------------------------ | ------------------- | ------------------------------------------------- |
| 200    | [OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)                  | Successful Response | Inline                                            |
| 422    | [Unprocessable Entity](https://tools.ietf.org/html/rfc2518#section-10.3) | Validation Error    | [HTTPValidationError](#schemahttpvalidationerror) |

Returns a new run identifier.

```json
{
  "run_id": "uuid"
}
```

<h3 id="attach_flow__run_id__attach_get-responseschema">Response Schema</h3>

<aside class="success">
This operation does not require authentication
</aside>

### Axios Example

```js
const res = await axios.post("/flow/start", {
  flow: "flow_name",
  tenant: "tenant_id",
  context: { key: "value" },
  stream: false,
});
const runId = res.data.run_id;
```

## 3. `POST /flow/{run_id}/continue`

Resume a paused flow.

### Parameter

| Name   | In   | Type                | Required | Description |
| ------ | ---- | ------------------- | -------- | ----------- |
| run_id | path | string(uuid)        | true     | none        |
| body   | body | FlowContinueRequest | true     | none        |

### Request Body (FlowContinueRequest)

```json
{
  "data": {},
  "stream": false
}
```

#### Field Descriptions

- **data** (object, required): Mapping of interrupt IDs to continuation values.
- **stream** (boolean, optional): Whether to stream the response.

### Response

| Status | Meaning                                                                  | Description         | Schema                                            |
| ------ | ------------------------------------------------------------------------ | ------------------- | ------------------------------------------------- |
| 200    | [OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)                  | Successful Response | Inline                                            |
| 422    | [Unprocessable Entity](https://tools.ietf.org/html/rfc2518#section-10.3) | Validation Error    | [HTTPValidationError](#schemahttpvalidationerror) |

`(stream = false)`
Returns the first output produced by the flow:

```json
{
  "run_id": "uuid",
  "status": "running or completed",
  "output": {},
  "metadata": {}
}
```

`(stream = true)`
Returns a StreamingResponse (`application/json`) that emits a sequence of JSON update objects:

```json
{
  "run_id": "uuid",
  "event": "update",
  "data": {}
}
```

Notes:

- run_id — the flow's thread ID
- status — flow status at the moment of the first output
- output — the flow’s first emitted result
- metadata — flow-specific metadata (timestamps, checkpoint info, etc.)

### Axios Example

```js
axios.post(`/flow/${runId}/continue`, {
  data: {
    interrupt_id: { key: "value" },
  },
  stream: false,
});
```

<h3 id="attach_flow__run_id__attach_get-responseschema">Response Schema</h3>

<aside class="success">
This operation does not require authentication
</aside>

# GET Endpoints

## 4. `GET /flow/{run_id}/attach`

Attach to a running flow and receive SSE stream updates.

### FIXME This will only work for flows with streaming enabled. needs a check for that

### FIXME Currently, if the flow has already completed, this will hang forever. needs a timeout or a check for completion

### Parameter

| Name   | In   | Type         | Required | Description |
| ------ | ---- | ------------ | -------- | ----------- |
| run_id | path | string(uuid) | true     | none        |

### Response

Server-Sent Events stream. No JSON.

| Status | Meaning                                                                  | Description         | Schema                                            |
| ------ | ------------------------------------------------------------------------ | ------------------- | ------------------------------------------------- |
| 200    | [OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)                  | Successful Response | Inline                                            |
| 422    | [Unprocessable Entity](https://tools.ietf.org/html/rfc2518#section-10.3) | Validation Error    | [HTTPValidationError](#schemahttpvalidationerror) |

<h3 id="attach_flow__run_id__attach_get-responseschema">Response Schema</h3>

<aside class="success">
This operation does not require authentication
</aside>

### Example Client

```js
const sse = new EventSource(`/flow/${runId}/attach`);
sse.onmessage = (e) => console.log(JSON.parse(e.data));
```

## 5. `GET /flow/{run_id}/history`

Retrieve all checkpoints for a flow run.

### Parameter

| Name   | In   | Type         | Required | Description |
| ------ | ---- | ------------ | -------- | ----------- |
| run_id | path | string(uuid) | true     | none        |

### Response

| Status | Meaning                                                                  | Description         | Schema                                            |
| ------ | ------------------------------------------------------------------------ | ------------------- | ------------------------------------------------- |
| 200    | [OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)                  | Successful Response | Inline                                            |
| 422    | [Unprocessable Entity](https://tools.ietf.org/html/rfc2518#section-10.3) | Validation Error    | [HTTPValidationError](#schemahttpvalidationerror) |

```json
{
  "run_id": "uuid",
  "checkpoints": [{}]
}
```

<h3 id="get_run_history_flow__run_id__history_get-responseschema">Response Schema</h3>

<aside class="success">
This operation does not require authentication
</aside>

### Axios Example

```js
axios.get(`/flow/${runId}/history`);
```

## 6. `GET /flow/{run_id}/status`

Retrieve the most recent checkpoint for a flow run.

### Parameter

| Name   | In   | Type         | Required | Description |
| ------ | ---- | ------------ | -------- | ----------- |
| run_id | path | string(uuid) | true     | none        |

### Response

Returns the latest checkpoint as the result of `checkpoints_asdict`.

| Status | Meaning                                                                  | Description         | Schema                                            |
| ------ | ------------------------------------------------------------------------ | ------------------- | ------------------------------------------------- |
| 200    | [OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)                  | Successful Response | Inline                                            |
| 422    | [Unprocessable Entity](https://tools.ietf.org/html/rfc2518#section-10.3) | Validation Error    | [HTTPValidationError](#schemahttpvalidationerror) |

```json
{
  "run_id": "uuid",
  "checkpoint": {}
}
```

<h3 id="get_run_status_flow__run_id__status_get-responseschema">Response Schema</h3>

<aside class="success">
This operation does not require authentication
</aside>

### Axios Example

```js
axios.get(`/flow/${runId}/status`);
```

<a id="schemavalidationerror"></a>
<a id="schema_ValidationError"></a>
<a id="tocSvalidationerror"></a>
<a id="tocsvalidationerror"></a>

# HTTPValidationError

### Properties

| Name   | Type                                        | Required | Restrictions | Description |
| ------ | ------------------------------------------- | -------- | ------------ | ----------- |
| detail | [[ValidationError](#schemavalidationerror)] | false    | none         | none        |

```json
{
  "loc": ["string"],
  "msg": "string",
  "type": "string"
}
```

# ValidationError

### Properties

| Name | Type    | Required | Restrictions | Description |
| ---- | ------- | -------- | ------------ | ----------- |
| loc  | [anyOf] | true     | none         | none        |

anyOf

| Name          | Type   | Required | Restrictions | Description |
| ------------- | ------ | -------- | ------------ | ----------- |
| » _anonymous_ | string | false    | none         | none        |

or

| Name          | Type    | Required | Restrictions | Description |
| ------------- | ------- | -------- | ------------ | ----------- |
| » _anonymous_ | integer | false    | none         | none        |

continued

| Name | Type   | Required | Restrictions | Description |
| ---- | ------ | -------- | ------------ | ----------- |
| msg  | string | true     | none         | none        |
| type | string | true     | none         | none        |

# Handler

This handler is used in **`/flow`** and **`/flow/{run_id}/continue`**.
It returns either a streaming response or the first output item produced by the flow.

### Behavior

- **If `stream=True`:**

Returns a `StreamingResponse` that streams all updates emitted by `mod.run(...)`.

- **If `stream=False`:**

Executes `mod.run(...)` and returns **the first output item** (or `{}` if none exists).

### Inputs

| Name           | Type               | Required | Description                                             |
| -------------- | ------------------ | -------- | ------------------------------------------------------- |
| `mod`          | Flow module        | yes      | The module that defines and runs the flow logic.        |
| `context`      | dict / model       | yes      | Input context passed to the flow.                       |
| `stream`       | bool               | yes      | Enables streaming mode when `True`.                     |
| `checkpointer` | AsyncPostgresSaver | yes      | Manages saving and restoring checkpoints.               |
| `command`      | any                | no       | Continuation instruction when resuming a paused flow.   |
| `thread_id`    | UUID               | no       | Flow run ID; required when continuing an existing flow. |

### Response

| Mode          | Type                | Media Type         | Description                                                              |
| ------------- | ------------------- | ------------------ | ------------------------------------------------------------------------ |
| Streaming     | `StreamingResponse` | `application/json` | Streams all updates produced by the running flow.                        |
| Non-streaming | JSON object         | `application/json` | Returns only the first output item from the flow (or `{}` if no output). |

# Flows

Flows define the actual **LangGraph agent logic** executed by the backend.
Each file inside the `flows/` directory represents a self-contained flow module
(e.g., chunk_and_embed.py, qa_from_docs.py, quiz.py).

The API endpoints in `flows.py` invoke these modules in two ways:

### **Via the handler**

Most endpoints pass the selected flow module (`mod`) to the handler, which executes the flow using:

```python
mod.run(...)
```

This is used for:

- `POST /flow`
- `POST /flow/{run_id}/continue`

Both support optional streaming and checkpointing.

### **Direct execution (no handler)**

The `POST /flow/start` endpoint calls the flow **directly**, initializes a new run,
and returns only the `run_id`.

Each flow module defines:

- The **state** layout
- The **node graph** (steps of the agent)
- Any **tools** used
- Whether the flow can **pause for user input**
- What the **final output** looks like

The rest of this section describes:

1. How flows are structured
2. What a typical flow file contains
3. Detailed documentation for **each flow** in this directory

You can jump to any category below:

## **Flow Categories**

| Category        | Flows Included                                                                                                                                                                                               | Description                                                |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| **Embedding**   | [`chunk_and_embed`](#1-chunk_and_embed-flow), [`e2e_embedding`](#2-e2e_embedding-flow)                                                                                                                       | Text/doc → chunks → embeddings → optional storage          |
| **Execution**   | [`executor_test`](#1-executor_test-flow), [`multi_math`](#2-multi_math-flow)                                                                                                                                 | Code/expression execution; multi-backend comparison        |
| **Reasoning**   | [`reasoning_multiprompt`](#1-reasoning_multiprompt-flow), [`reasoning_with_document`](#2-reasoning_with_document-flow), [`reasoning_multiprompt_with_document`](#3-reasoning_multiprompt_with_document-flow) | Single/multi-step reasoning with optional document context |
| **QA (RAG)**    | [`qa_from_docs`](#qa_from_docs-flow)                                                                                                                                                                         | Retrieval + reasoning over document chunks                 |
| **Interactive** | [`quiz`](#quiz-flow)                                                                                                                                                                                         | Multi-step reasoning with human input interrupts           |

# `qa_from_docs` Flow

### **Purpose**

This flow answers a user question based on document chunks stored in a vector database.
It embeds the question, retrieves relevant chunks, builds a context-aware prompt, and uses a reasoning agent to generate the answer.
It can start a new run or resume an interrupted one via a `Command`.

## Overview

The flow performs the following steps:

1. **Validate input / resume**

   - New run: validate `context["question"]` and build initial state
   - Resume: use a `Command` plus a checkpointer

2. **Embed question**
   Use the embedding agent to compute a vector for the question.

3. **Retrieve documents**
   Run a vector similarity search to fetch relevant chunks from the database.

4. **Build prompt**
   Combine retrieved chunks and the question into a single prompt.

5. **Answer question**
   Call the reasoning agent to generate an answer based on the constructed prompt.

The flow is defined in this module and executed through:

```python
mod.run(...)
```

## State Definition

```python
class QAState(TypedDict, total=False):
    question: list[str]
    deployment: str
    question_embeddings: list[list[float]]
    prompt: str
    answer: str
    method: str
    top_k: int
    threshold: float
    stream: bool
```

| Field                 | Type                | Description                                                         |
| --------------------- | ------------------- | ------------------------------------------------------------------- |
| `question`            | `list[str]`         | The user question as a single-element list (e.g. `[question]`)      |
| `deployment`          | `str`               | Reasoning model deployment name (e.g. `Ethel_5`)                    |
| `question_embeddings` | `list[list[float]]` | Embedding vector(s) for the question                                |
| `prompt`              | `str`               | Prompt constructed from retrieved chunks and the question           |
| `answer`              | `str`               | Final answer produced by the reasoning agent                        |
| `method`              | `str`               | Chunking / retrieval method name (used in retrieval config)         |
| `top_k`               | `int`               | Number of chunks to retrieve from the vector store                  |
| `threshold`           | `float`             | Distance threshold used in vector search                            |
| `stream`              | `bool`              | Whether the reasoning step should stream intermediate answer chunks |

> Note: `method`, `top_k`, `threshold`, and retrieval flags are read from `context` and passed into the retrieval step; not all are stored back into the state.

## Flow Structure

The flow is a three-step pipeline:

```
embed_question → retrieve_documents → answer_question → END
```

### Nodes

| Node                   | Function                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ |
| **embed_question**     | Embeds the question text and stores the result in `question_embeddings`                                            |
| **retrieve_documents** | Uses `question_embeddings[0]` to query the vector store and builds the `prompt` with retrieved chunks and question |
| **answer_question**    | Calls the reasoning agent with the `prompt` and writes the generated answer into `answer`                          |

Node origins:

- `embedding_node` imported from `agents/embedding` (wrapped as `"embed_question"`)
- `reasoning_node` imported from `agents/reasoning` (wrapped as `"answer_question"`)
- `retrieve_documents` defined inline and uses:

  - `get_session_ctx` from `data.db_utils`
  - `get_relevant_chunks` from `data.vectors`

## Execution Entry Point

```python
async def run(
    thread_id: uuid.UUID,
    context=None,
    stream=False,
    command: Command = None,
    checkpointer=None,
)
```

### Parameters

| Name           | Description                                                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| `thread_id`    | Unique ID used for checkpointing and tracking the run                                                   |
| `context`      | Input data for a new run; must include `context["question"]` and may include `top_k`, `threshold`, etc. |
| `stream`       | Whether to stream answer chunks or return a single final result                                         |
| `command`      | Used when resuming a flow after an interrupt; requires `checkpointer` to be set                         |
| `checkpointer` | Optional Postgres-based checkpoint manager; **required** when `command` is used                         |

**New run (no `command`):**

- Validates that `context` is a dict and `context["question"]` is a string.
- Reads `top_k`, `threshold`, `method`, `retrieve_entire_docs`, `retrieve_entire_docs_hits` from `context` (with defaults).
- Builds `initial_state`:

  ```python
  initial_state: QAState = {
      "deployment": "Ethel_5",
      "question": [question],
      "top_k": top_k,
      "stream": stream,
  }
  ```

**Resume (with `command`):**

- Requires a non-`None` `checkpointer`.
- Uses `command` as the graph input instead of `initial_state`.

In **streaming mode**, the flow:

- Calls `app.astream_events(input, config=config, version="v2")`
- Yields answer chunks from `on_chain_stream` events where `event["data"]["chunk"]["answer"]` is present and not yet finished.

In **non-streaming mode**, it returns the full final state via:

```python
await app.ainvoke(input, config=config)
```

## Final Output

| Output Field          | Description                                           |
| --------------------- | ----------------------------------------------------- |
| `question`            | The original question as a single-element list        |
| `question_embeddings` | The embedding vector(s) computed for the question     |
| `prompt`              | The constructed prompt with retrieved document chunks |
| `answer`              | The final answer generated by the reasoning agent     |
| `deployment`          | The reasoning model deployment used                   |

formatted according to `QAState`.

# `quiz` Flow

### **Purpose**

This flow runs an interactive quiz about a given topic.
It lets the model:

1. generate an explanation and a question,
2. wait for the user’s answer, and
3. provide corrected answer + feedback.

It uses LangGraph interrupts so the flow can pause for human input and then resume.

## Overview

The flow performs the following steps:

1. **Validate input / resume**

   - New run: validate `context["topic"]` and build initial state.
   - Resume: use a `Command` plus a checkpointer.

2. **Prepare topic prompt**
   Build a system prompt to generate an explanation and **one** quiz question.

3. **Generate quiz question**
   Call the reasoning agent to produce the explanation and question.

4. **Interrupt for user answer**
   Pause the flow and wait for the user’s answer via `interrupt(...)`.

5. **Prepare feedback prompt**
   Build a prompt with the original question and the user’s answer.

6. **Generate feedback**
   Call the reasoning agent again to provide the correct answer and feedback.

The flow is defined in this module and executed through:

```python
mod.run(...)
```

## State Definition

```python
class QuizState(TypedDict, total=False):
    topic: str
    deployment: str
    topic_prompt: str
    feedback_prompt: str
    question: str
    answer: str
    feedback: str
```

| Field             | Type  | Description                                                          |
| ----------------- | ----- | -------------------------------------------------------------------- |
| `topic`           | `str` | Topic of the quiz provided by the user                               |
| `deployment`      | `str` | Reasoning model deployment name (e.g. `Ethel_o4_mini`)               |
| `topic_prompt`    | `str` | Prompt instructing the model to explain the topic and ask a question |
| `feedback_prompt` | `str` | Prompt for evaluating the user’s answer and giving feedback          |
| `question`        | `str` | Generated explanation + question from the first reasoning step       |
| `answer`          | `str` | User’s answer captured via `interrupt(...)`                          |
| `feedback`        | `str` | Final feedback and correct answer from the second reasoning step     |

## Flow Structure

The flow is a linear interactive pipeline:

```
prepare_topic_prompt → prepare_quiz → human_answer → prepare_feedback_prompt → feedback → END
```

### Nodes

| Node                        | Function                                                                                                   |
| --------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **prepare_topic_prompt**    | Builds `topic_prompt` from `topic` with instructions for explanation + one question                        |
| **prepare_quiz**            | Calls the reasoning agent with `topic_prompt` and writes the result (explanation + question) to `question` |
| **human_answer**            | Interrupts the flow to get user input and stores it in `answer`                                            |
| **prepare_feedback_prompt** | Builds `feedback_prompt` from `question` and `answer`                                                      |
| **feedback**                | Calls the reasoning agent with `feedback_prompt` and writes the result to `feedback`                       |

Node origins:

- `reasoning_node` imported from `agents/reasoning` (used for `prepare_quiz` and `feedback`)
- `prepare_topic_prompt`, `human_answer`, and `prepare_feedback_prompt` are helper nodes defined in this module
- `interrupt` imported from `langgraph.types` is used to pause for human input in `human_answer`

## Execution Entry Point

```python
async def run(
    thread_id: uuid.UUID,
    context=None,
    stream=False,
    command: Command = None,
    checkpointer=None,
)
```

### Parameters

| Name           | Description                                                                     |
| -------------- | ------------------------------------------------------------------------------- |
| `thread_id`    | Unique ID used for checkpointing and tracking the run                           |
| `context`      | Input data for a new run; must include `context["topic"]`                       |
| `stream`       | Whether to stream raw events or return a single final state                     |
| `command`      | Used when resuming the flow after an interrupt; requires `checkpointer`         |
| `checkpointer` | Optional Postgres-based checkpoint manager; **required** when `command` is used |

**New run (no `command`):**

- Validates that `context` is a dict and `context["topic"]` is a string.
- Builds `initial_state`:

  ```python
  initial_state: QuizState = {"topic": topic, "deployment": "Ethel_o4_mini"}
  ```

**Resume (with `command`):**

- Requires `checkpointer` to be provided.
- Uses `command` as the graph input instead of `initial_state`.

In **streaming mode**, the flow:

- Calls `app.astream_events(input, config=config, version="v2")`
- Yields each event as a string (primarily useful for debugging or low-level inspection).

In **non-streaming mode**, it returns the final state via:

```python
await app.ainvoke(input, config=config)
```

## Final Output

| Output Field | Description                                                      |
| ------------ | ---------------------------------------------------------------- |
| `topic`      | The topic used to generate the explanation and quiz question     |
| `question`   | The explanation + quiz question generated by the model           |
| `answer`     | The user’s answer provided after the interrupt                   |
| `feedback`   | The model’s corrected answer and feedback on the user’s response |
| `deployment` | The reasoning model deployment used                              |

formatted according to `QuizState`.

# Execution Flows

The execution flows provide isolated code execution for Python and Maxima, and optionally compare results using a reasoning model. They rely on the **executor agent**, which runs code inside containerized environments and returns structured execution results.

There are **two** flows in this category:

1. **`executor_test`** – single-backend execution (Python or Maxima)
2. **`multi_math`** – evaluate one expression in both Python and Maxima and compare the outputs using an LLM

## 1. `executor_test` Flow

### **Purpose**

Run **one script** in a selected execution backend:

- **Python** (`type="python"`)
- **Maxima** (`type="maxima"`)

Useful for:

- basic executor testing
- verifying isolated runtime behavior
- running arbitrary code or symbolic expressions

### **Overview**

1. Validate inputs:

   - `type` must be `"python"` or `"maxima"`
   - Python → requires `context["code"]`
   - Maxima → requires `context["expr"]`

2. Select correct runtime image:

   - `"python:3.12-slim"`
   - `"maxima-executor:latest"`

3. Build the execution state:

   - stores script, type, image

4. Run the single executor node:

   - returns `execution_result` (stdout, stderr, exit code, etc.)

### **Flow Structure**

```
executor → END
```

### **State (`ExecutorTestState`)**

| Field              | Description                                      |
| ------------------ | ------------------------------------------------ |
| `image`            | Runtime image used for execution                 |
| `type`             | `"python"` or `"maxima"`                         |
| `code` / `expr`    | Code snippet or expression to execute            |
| `execution_result` | Structured result returned by the executor agent |

### **Final Output**

| Output Field       | Description                                              |
| ------------------ | -------------------------------------------------------- |
| `code` / `expr`    | The executed code or expression                          |
| `execution_result` | The full executor results (stdout, stderr, status, etc.) |
| `type`             | Execution backend used                                   |
| `image`            | Execution container image                                |

formatted according to `ExecutorTestState`.

## 2. `multi_math` Flow

### **Purpose**

Evaluate the **same mathematical expression** in **two different environments**:

- **Maxima**
- **Python**

Then generate an **LLM-based explanation** comparing both outputs.

Useful for:

- consistency checking between symbolic and numerical backends
- debugging complex expressions
- producing human-readable math comparisons

### **Overview**

1. **Normalize expression** → convert input into scripts for each backend:

   - Maxima script: `<expr>;`
   - Python script: `print(<expr>)`
   - (R script is generated but unused)

2. **Execute** in both environments using `executor_node`

3. **Build comparison prompt** based on:

   - `maxima_results.stdout`
   - `python_results.stdout`

4. **Call reasoning agent**

   - produce a comparison explaining whether the outputs match and why

### **Flow Structure**

```
norm → python ┐
      \       ├→ prompt → compare → END
       → maxima┘
```

### **State (`MultiMathState`)**

| Field              | Description                               |
| ------------------ | ----------------------------------------- |
| `expression`       | Original math expression                  |
| `maxima_script`    | Script formatted for Maxima execution     |
| `python_script`    | Script formatted for Python execution     |
| `maxima_results`   | Maxima executor output                    |
| `python_results`   | Python executor output                    |
| `prompt`           | Automatically generated comparison prompt |
| `reasoning_result` | LLM explanation comparing both outputs    |
| `deployment`       | LLM deployment name used for reasoning    |

### **Final Output**

| Output Field       | Description                                         |
| ------------------ | --------------------------------------------------- |
| `maxima_results`   | Execution result from the Maxima backend            |
| `python_results`   | Execution result from the Python backend            |
| `prompt`           | Comparison prompt used for reasoning                |
| `reasoning_result` | LLM-generated explanation of agreement/disagreement |

formatted according to `MultiMathState`.

# Embedding Flows

The embedding flows convert raw text or full documents into **vector embeddings** suitable for retrieval, search, and semantic indexing.
They rely on reusable agents for chunking, embedding, and (optionally) storing both chunks and vectors.

There are **two** flows in this category:

1. **`chunk_and_embed`** – simple text → chunks → embeddings
2. **`e2e_embedding`** – full document indexing pipeline (file → text → chunks → storage → embeddings → vector store)

## 1. `chunk_and_embed` Flow

### **Purpose**

Convert a block of input text into:

1. a list of clean, deterministic **chunks**, and
2. **embeddings** for each chunk.

This is typically used when the text is already available and no I/O or storage is required.

### **Overview**

1. Read raw input `.text` from context
2. **Chunk** text into smaller segments
3. **Embed** each chunk
4. Return final state (`texts`, `embeddings`)

### **Flow Structure**

```
START → chunk → embed → END
```

### **State (`ChunkAndEmbedState`)**

| Field        | Type        | Description                               |
| ------------ | ----------- | ----------------------------------------- |
| `text`       | `str`       | Raw input text                            |
| `texts`      | `list[str]` | List of generated text chunks             |
| `embeddings` | `dict`      | Embeddings for each chunk, keyed by index |

### **Final Output**

| Output Field | Description                           |
| ------------ | ------------------------------------- |
| `texts`      | The list of generated text chunks     |
| `embeddings` | Embedding vectors for each text chunk |

formatted according to `ChunkAndEmbedState`.

## 2. `e2e_embedding` Flow

### **Purpose**

This flow performs **full E2E document embedding**, including:

1. **file loading** using a document ID
2. **text extraction**
3. **chunking**
4. **chunk storage** (database)
5. **embedding generation**
6. **vector storage**

This is the complete pipeline used to index a document into your retrieval system.

### **Overview**

1. Extract text from file (`file_to_text_node`)
2. Chunk text using the configured method
3. Store chunks → receive `chunk_ids`
4. Embed chunks
5. Store embedding vectors with their corresponding `chunk_ids`

### **Flow Structure**

```
file_to_text → chunk_text → store_chunks → embedding → prepare_for_store_vectors → store_vectors → END
```

### **State (`E2EEmbeddingState`)**

| Field                    | Type                | Description                        |
| ------------------------ | ------------------- | ---------------------------------- |
| `document_id`            | `uuid.UUID`         | ID of the input document           |
| `text`                   | `str`               | Extracted text from the document   |
| `chunks`                 | `list[str]`         | List of chunked text segments      |
| `store_chunks_response`  | `dict`              | Response from storing chunks       |
| `chunk_ids`              | `list[uuid.UUID]`   | IDs assigned to each stored chunk  |
| `embeddings`             | `list[list[float]]` | Embeddings computed for each chunk |
| `store_vectors_response` | `dict`              | Result of storing vectors          |
| `method`                 | `str`               | Chunking method used               |

### **Final Output**

| Output Field             | Description                      |
| ------------------------ | -------------------------------- |
| `chunks`                 | The generated text chunks        |
| `chunk_ids`              | IDs of stored chunks             |
| `embeddings`             | Embedding vectors for each chunk |
| `store_chunks_response`  | Metadata from chunk storage      |
| `store_vectors_response` | Metadata from vector storage     |

formatted according to `E2EEmbeddingState`.

# Reasoning Flows

The reasoning flows provide structured access to the **reasoning agent**, optionally grounded in a document. They support:

- **single-step reasoning**
- **two-step chained reasoning**
- **document-aware reasoning**
- optional **streaming** of intermediate chunks

There are three flows in this category:

1. **`reasoning_multiprompt`** – two-step chained reasoning (prompt → response → new prompt → response)
2. **`reasoning_with_document`** – single-step document-aware reasoning
3. **`reasoning_multiprompt_with_document`** – two-step chained reasoning with document grounding (optional to include)

## 1. `reasoning_multiprompt` Flow

### **Purpose**

Run **two consecutive reasoning steps**:

1. First: respond to `prompt_1`
2. Then: prepend that response to `prompt_2` and reason again

This tests **chained reasoning**, prompt refinement, or back-and-forth reasoning patterns.

### **Overview**

1. Validate `prompt_1`, `prompt_2`, `deployment`
2. Call reasoning agent with `prompt_1` → `response_1`
3. Update `prompt_2 = response_1 + prompt_2`
4. Call reasoning agent with updated `prompt_2` → `response_2`

### **Flow Structure**

```
reasoning_1 → prepare_second_prompt → reasoning_2 → END
```

### **State (`ReasoningTestState`)**

| Field              | Description                             |
| ------------------ | --------------------------------------- |
| `deployment`       | Reasoning model name                    |
| `prompt_1`         | First reasoning prompt                  |
| `prompt_2`         | Follow-up prompt (updated after step 1) |
| `reasoning_effort` | Optional reasoning effort/mode          |
| `stream`           | Whether streaming is used               |
| `response_1`       | First reasoning response                |
| `response_2`       | Second reasoning response               |

### **Final Output**

| Output Field | Description                                    |
| ------------ | ---------------------------------------------- |
| `response_1` | Model’s answer to `prompt_1`                   |
| `response_2` | Model’s answer to the updated `prompt_2`       |
| `deployment` | Model deployment used for both reasoning steps |

formatted according to `ReasoningTestState`.

## 2. `reasoning_with_document` Flow

### **Purpose**

Run a **single reasoning pass** grounded in a specific document.

Used when the model needs:

- document content
- content type (e.g., pdf, html, text)
- a prompt describing what to extract or analyze

### **Overview**

1. Validate `prompt`, `document_id`, `content_type`, `deployment`
2. Build initial state with prompt + document metadata
3. Run one reasoning node with document grounding
4. Return model response (streamed or full)

### **Flow Structure**

```
reasoning → END
```

### **State (`ReasoningTestState`)**

| Field                | Description                             |
| -------------------- | --------------------------------------- |
| `deployment`         | Reasoning model deployment              |
| `document_id`        | ID of the document used as context      |
| `content_type`       | MIME type of the document               |
| `prompt`             | Reasoning prompt                        |
| `reasoning_effort`   | Optional reasoning mode                 |
| `stream`             | Whether streaming is enabled            |
| `reasoning_response` | Final response from the reasoning agent |

### **Final Output**

| Output Field         | Description                             |
| -------------------- | --------------------------------------- |
| `reasoning_response` | Model’s response to the provided prompt |
| `deployment`         | Model deployment used                   |
| `document_id`        | Document used as context                |
| `content_type`       | Content type used for document handling |

formatted according to `ReasoningTestState`.

## 3. `reasoning_multiprompt_with_document` Flow

> **Note:** This is the two-step version **with document grounding in the first step**, which was provided earlier.

### **Purpose**

Run **two chained reasoning steps**, where:

- The **first step** is grounded in a document
- The **second step** uses the combined prompt only (no document)

### **Flow Structure**

```
reasoning_1 (with document) → prepare_second_prompt → reasoning_2 → END
```

### **State (subset)**

| Field          | Description                         |
| -------------- | ----------------------------------- |
| `document_id`  | Document used for first reasoning   |
| `content_type` | Document MIME type                  |
| `prompt_1`     | First prompt                        |
| `prompt_2`     | Second prompt (updated dynamically) |
| `response_1`   | Reasoning output from step 1        |
| `response_2`   | Reasoning output from step 2        |

### **Final Output**

| Output Field | Description                             |
| ------------ | --------------------------------------- |
| `response_1` | Response to `prompt_1` (document aware) |
| `response_2` | Response to updated `prompt_2`          |

# Summary Table (Recommendation for README)

You can include this simple table to give readers a quick overview:

| Flow Name                             | Steps | Uses Document? | Description                                   |
| ------------------------------------- | ----- | -------------- | --------------------------------------------- |
| `reasoning_multiprompt`               | 2     | No             | Chained prompts with two reasoning passes     |
| `reasoning_with_document`             | 1     | Yes            | Single-step document-grounded reasoning       |
| `reasoning_multiprompt_with_document` | 2     | Yes (step 1)   | Two-step reasoning w/ first step doc-grounded |
