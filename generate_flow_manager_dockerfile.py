import os
from pathlib import Path

# Constants: update these if your structure changes
FLOW_MANAGER_DIR = Path("flow_manager")
AGENTS_DIR = Path("agent_pool/agents")
DOCKERFILE_PATH = FLOW_MANAGER_DIR / "Dockerfile"

# Find all node_adapter.py files
adapter_files = []
for agent_dir in AGENTS_DIR.iterdir():
    adapter_path = agent_dir / "node_adapter.py"
    if adapter_path.exists():
        # Want the destination to be: agent_pool/agents/AGENT_NAME/node_adapter.py
        dest_path = f"agent_pool/agents/{agent_dir.name}/node_adapter.py"
        adapter_files.append((str(adapter_path), dest_path))

# Compose the Dockerfile content
dockerfile_lines = [
    "FROM python:3.11-slim",
    "",
    "WORKDIR /app",
    "",
    "COPY flow_manager/requirements.txt .",
    "RUN pip install --no-cache-dir -r requirements.txt",
    "",
    "COPY flow_manager/flow_manager.py flow_manager.py",
    "COPY flow_manager/asset_handler.py asset_handler.py",
    "COPY flow_manager/async_agent_handler.py async_agent_handler.py",
    "COPY flow_manager/flow_resume.py flow_resume.py",
    "COPY flow_manager/flows flows",
    "",
    "COPY ../agent_pool/agents/__init__.py agent_pool/agents/__init__.py",
    "",
]

for src, dest in adapter_files:
    # Note: src is relative to project root, dest is relative to /app in container
    dockerfile_lines.append(f"COPY ../{src} {dest}")

dockerfile_lines += [
    "",
    "EXPOSE 8000",
    'CMD ["python", "flow_manager.py"]',
    ""
]

# Write the Dockerfile to flow_manager/Dockerfile
with open(DOCKERFILE_PATH, "w") as f:
    f.write("\n".join(dockerfile_lines))

print(f"Generated Dockerfile with {len(adapter_files)} adapter(s) in {DOCKERFILE_PATH}")

