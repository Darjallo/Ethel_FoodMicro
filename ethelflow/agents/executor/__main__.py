import ast
import base64
import uuid

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from kubernetes import client, config

from ethelflow.agents.executor.models import ExecutionRequest, ExecutionResult


NAMESPACE = "default"


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # setup kubeconfig
#     try:
#         config.load_incluster_config()
#         print("Kubernetes config loaded successfully.")
#     except config.ConfigException:
#         raise RuntimeError(
#             "Kubernetes config not found. Ensure running in cluster or set kubeconfig path."
#         )
#     yield


app = FastAPI()


@app.post("/execute")
async def execute_code(req: ExecutionRequest):
    try:
        config.load_incluster_config()
        print("Kubernetes config loaded successfully.")
        core_v1 = client.CoreV1Api()
        batch_v1 = client.BatchV1Api()
    except config.ConfigException:
        raise RuntimeError(
            "Kubernetes config not found. Ensure running in cluster or set kubeconfig path."
        )
    try:
        code = base64.b64decode(req.code_b64).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 encoding")

    # Check syntax (might add more checks later, e.g. check if executable at all)
    # This check doesn't catch most stuff
    try:
        ast.parse(code)
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Syntax error: {e.msg}")

    # TODO: dynamic command, depending on execution type
    command = ["python3", "/scripts/script.py"]

    execution_id = uuid.uuid4()
    print(f"Execution ID: {execution_id}")

    # Create ConfigMap
    execution_name = f"execution-{execution_id.hex[:8]}"
    config_map = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=execution_name),
        data={
            "script.py": code,
        },
    )
    core_v1.create_namespaced_config_map(namespace=NAMESPACE, body=config_map)

    # Create Job
    job = client.V1Job(
        metadata=client.V1ObjectMeta(name=execution_name),
        spec=client.V1JobSpec(
            backoff_limit=0,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={"ethel.ethz.ch/execution-id": str(execution_id)}
                ),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name="executor",
                            image=req.image,
                            command=command,
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="script-volume",
                                    mount_path="/scripts",
                                    read_only=True,
                                )
                            ],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="script-volume",
                            config_map=client.V1ConfigMapVolumeSource(
                                name=config_map.metadata.name
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    batch_v1.create_namespaced_job(namespace=NAMESPACE, body=job)

    # TODO: watch the job, and return the stdout and stderr
    return ExecutionResult(
        execution_id=execution_id, return_code=0, stdout="logs", stderr=""
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
