# Project Ethel  
## Flow Manager

> **Flow Manager** is a lightweight orchestration layer for executing multi-step “flows” of micro-services (agents). It offers both streaming and non-streaming modes, mimicking the OpenAI Chat Completion API pattern, and is fully extensible via custom flows and agents.


## Table of Contents

1. [Overview](#overview)  
2. [Getting Started](#getting-started)  
3. [Flow Manager API](#flow-manager-api)  
4. [Flows](#flows)  
5. [Agents](#agents)  
6. [Extending with New Flows & Agents](#extending-with-new-flows--agents)  
7. [Example: \`test_flow\` & \`test_agent\`](#example-test_flow--test_agent)  
8. [License](#license)  

---

## Overview

The Flow Manager exposes a single HTTP endpoint (\`POST /\`) that accepts:

- **flow**: string name of the flow module under \`flows/\`  
- **context**: arbitrary JSON object (e.g., containing courseID, userID, sessionID, etc.)  
- **query**: flow-specific parameters  
- **stream**: boolean; when \`true\`, returns a chunked response with each node’s update as it completes, otherwise returns only the final result  

Under the hood, each flow is defined via a directed acyclic graph of “nodes,” where each node invokes an external micro-service (an “agent”).  

---

## Getting Started

1. **Clone** the repo.  
2. **Install** Python dependencies for the Flow Manager:
   \`\`\`bash
   pip install -r flow_manager/requirements.txt
   \`\`\`
3. **Build & run** your agents (each in its own container or process).  
4. **Launch** the Flow Manager:
   \`\`\`bash
   python flow_manager/flow_manager.py
   \`\`\`
5. **Test** with the example test script:
   \`\`\`bash
   python debug/send_test_flow.py
   \`\`\`

---

## Flow Manager API

### Request

\`\`\`http
POST / HTTP/1.1
Content-Type: application/json

{
  "flow": "test_flow",
  "context": { … },
  "query": { … },      # optional
  "stream": true|false  # optional, defaults to false
}
\`\`\`

### Response

- **Non-streaming** (\`stream=false\`):  
  A single JSON object with the final state.

- **Streaming** (\`stream=true\`):  
  An HTTP/1.1 chunked response. Each chunk is a line-delimited JSON object representing the output of each node, in order.  

---

## Flows

Flows live under \`flow_manager/flows/\`:

- Each flow module exports a \`run(context, session=None, query=None, stream=False)\` generator.
- Flows define a **state schema** (via \`TypedDict\`) and use \`langgraph\` to build a small DAG.
- Nodes in the graph map to adapter functions that call external agents.

---

## Agents

Agents live under \`agent_pool/agents/…\`:

- Each agent directory contains:
  - \`agent.py\`: a small HTTP server conforming to our “OpenAI-like” micro-service interface.
  - \`node_adapter.py\`: a thin client adapter that the Flow Manager uses to invoke the agent.
- Agents implement two methods:
  - \`handle(request_json) → dict\`: for non-streamed calls.
  - \`stream(request_json) → Iterable[str]\`: for streamed character-/token-by-character output.

---

## Extending with New Flows & Agents

1. **Add an Agent**  
   - Create \`agent_pool/agents/<your_agent>/agent.py\` and define \`handle\` and/or \`stream\`.  
   - Wire up \`agent_pool/agents/<your_agent>/node_adapter.py\` to call your HTTP micro-service.  

2. **Add a Flow**  
   - In \`flow_manager/flows/\`, create \`<your_flow>.py\`, define a \`run(...)\` generator using \`langgraph\`.  
   - In \`flow_manager/flows/nodes.py\`, register your new node adapters.  

3. **Deploy**  
   - Build & run each agent (e.g., as Docker containers exposing port 8000).  
   - Rebuild & run the Flow Manager.  

---

## Example: \`test_flow\` & \`test_agent\`

- **\`test_flow\`** in \`flow_manager/flows/test_flow.py\`:  
  A trivial one-node flow that calls \`test_agent\`.

- **\`test_agent\`** in \`agent_pool/agents/test_agent/agent.py\`:  
  Simulates an OpenAI chat completion:
  - **Non-stream**: returns a single JSON  
  - **Stream**: yields one character at a time in OpenAI chunk format  

Use these as templates when adding your own nodes and agents.

---

## License

This project is licensed under the GNU GPLv3.  

 Copyright (C) 2025  Gerd Kortemeyer, ETH Zurich

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

