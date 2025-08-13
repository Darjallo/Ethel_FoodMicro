import ast
import base64
from multiprocessing.pool import AsyncResult
import uuid

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from kubernetes import client, config

from ethelflow.agents.executor.models import ExecutionRequest, ExecutionResult
import time

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

    job_manifest = client.V1Job(
        metadata=client.V1ObjectMeta(
            name=execution_name,
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={"ethel.ethz.ch/execution-id": str(execution_id)}
                ),
                spec=client.V1PodSpec(
                    # TODO: resource limits, security context, etc.
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
                                name=execution_name
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    job_result: AsyncResult = batch_v1.create_namespaced_job(
        namespace=NAMESPACE, body=job_manifest, async_req=True
    )

    config_map_manifest = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=execution_name,
            owner_references=[
                client.V1OwnerReference(
                    api_version="batch/v1",
                    kind="Job",
                    name=job_result.get().metadata.name,
                    uid=job_result.get().metadata.uid,
                    controller=False,
                    block_owner_deletion=True,
                )
            ],
        ),
        data={
            "script.py": code,
        },
    )
    core_v1.create_namespaced_config_map(namespace=NAMESPACE, body=config_map_manifest)

    print(f"Job created with uid: {job_result.get().metadata.uid}")

    # watch the job, and return the stdout and stderr
    pod_name = None
    for _ in range(30):
        pods = core_v1.list_namespaced_pod(
            namespace=NAMESPACE,
            label_selector=f"ethel.ethz.ch/execution-id={execution_id}",
        ).items
        if pods:
            pod = pods[0]
            pod_name = pod.metadata.name
            print(f"Found pod: {pod_name}")
            break

    # wait for the pod to complete
    if not pod_name:
        raise HTTPException(status_code=500, detail="Pod not found")

    for _ in range(30):
        pod = core_v1.read_namespaced_pod(name=pod_name, namespace=NAMESPACE)
        if pod.status.phase in ("Succeeded", "Failed"):
            print(f"Pod {pod_name} completed with status: {pod.status.phase}")
            break
        time.sleep(2)
    else:
        raise HTTPException(status_code=500, detail="Pod did not complete in time")

    try:
        pod = core_v1.read_namespaced_pod(name=pod_name, namespace=NAMESPACE)
        exit_code = pod.status.container_statuses[0].state.terminated.exit_code
        logs = core_v1.read_namespaced_pod_log(name=pod_name, namespace=NAMESPACE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading pod logs: {str(e)}")

    return ExecutionResult(
        execution_id=execution_id, return_code=exit_code, stdout=logs, stderr=logs
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
