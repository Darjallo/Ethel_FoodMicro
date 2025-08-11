import tempfile
import os
import subprocess
import uuid
import time
import base64

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from kubernetes import client, config
from ethelflow.agents.executor.models import ExecutionRequest, ExecutionResult

batch_v1 = client.BatchV1Api()
core_v1 = client.CoreV1Api()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # setup kubeconfig
    try:
        config.load_incluster_config()
    except config.ConfigException:
        raise RuntimeError(
            "Kubernetes config not found. Ensure running in cluster or set kubeconfig path."
        )
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/execute")
async def execute_code(req: ExecutionRequest):
    if not req.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are allowed")

    try:
        code_bytes = base64.b64decode(req.code_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 encoding")

    # Check syntax
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
        tmp.write(code_bytes)
        tmp_path = tmp.name

    try:
        subprocess.check_output(["python", "-m", "py_compile", tmp_path])
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=400, detail=f"Syntax error: {e.output.decode()}"
        )
    finally:
        os.unlink(tmp_path)

    # Create ConfigMap
    configmap_name = f"cm-{uuid.uuid4().hex[:6]}"
    job_name = f"job-{uuid.uuid4().hex[:6]}"

    config_map = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=configmap_name),
        data={req.filename: code_bytes.decode()},
    )
    core_v1.create_namespaced_config_map(namespace="default", body=config_map)

    job_manifest = client.V1Job(
        metadata=client.V1ObjectMeta(name=job_name),
        spec=client.V1JobSpec(
            backoff_limit=0,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"job-name": job_name}),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name="executor",
                            image=req.image,
                            command=["/bin/sh", "-c", req.command],
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
                                name=configmap_name
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    batch_v1.create_namespaced_job(namespace="default", body=job_manifest)

    # Wait for completion
    pod_name = None
    for _ in range(30):
        pods = core_v1.list_namespaced_pod(
            namespace="default", label_selector=f"job-name={job_name}"
        ).items
        if pods:
            pod = pods[0]
            pod_name = pod.metadata.name
            if pod.status.phase in ("Succeeded", "Failed"):
                break
        time.sleep(2)

    if not pod_name:
        raise HTTPException(status_code=500, detail="Pod not found")

    logs = core_v1.read_namespaced_pod_log(name=pod_name, namespace="default")

    try:
        pod = core_v1.read_namespaced_pod(name=pod_name, namespace="default")
        exit_code = pod.status.container_statuses[0].state.terminated.exit_code
    except Exception:
        exit_code = -1

    # Cleanup
    batch_v1.delete_namespaced_job(
        name=job_name,
        namespace="default",
        body=client.V1DeleteOptions(propagation_policy="Foreground"),
    )
    core_v1.delete_namespaced_config_map(name=configmap_name, namespace="default")

    return ExecutionResult(
        return_code=exit_code, stdout=logs, stderr="" if exit_code == 0 else logs
    )
