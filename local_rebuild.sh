#!/usr/bin/env bash
set -euo pipefail

# rebuild_reload_microk8s.sh
#
# Builds the ethelflow image from ethelflow.Dockerfile, imports it into MicroK8s containerd,
# updates the ethelflow Deployment to use the new image tag, and waits for rollout.
#
# Usage:
#   ./rebuild_reload_microk8s.sh
#
# Optional env vars:
#   NAMESPACE=default
#   DEPLOYMENT=ethelflow
#   DOCKERFILE=ethelflow.Dockerfile
#   IMAGE_REPO=ethelflow
#   TAG=20251229-185056        (defaults to current datetime)
#   CONTAINER_NAME=ethelflow   (if not set, script will auto-detect the first container name)
#   PORT_FORWARD_LOCAL=18080   (if set, will start a port-forward in background and print OpenAPI paths)
#   PORT_FORWARD_REMOTE=8080   (defaults to 8080)
#
# Notes:
# - Requires: docker, microk8s, python3
# - Uses sudo for docker save/build and microk8s ctr import (common on Ubuntu).

NAMESPACE="${NAMESPACE:-default}"
DEPLOYMENT="${DEPLOYMENT:-ethelflow}"
DOCKERFILE="${DOCKERFILE:-ethelflow.Dockerfile}"
IMAGE_REPO="${IMAGE_REPO:-ethelflow}"
TAG="${TAG:-$(date +%Y%m%d-%H%M%S)}"
IMAGE="${IMAGE_REPO}:${TAG}"
PORT_FORWARD_LOCAL="${PORT_FORWARD_LOCAL:-}"
PORT_FORWARD_REMOTE="${PORT_FORWARD_REMOTE:-8080}"

log() { echo "[$(date +'%H:%M:%S')] $*"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing command: $1" >&2; exit 1; }
}

require_cmd docker
require_cmd microk8s
require_cmd python3

if [[ ! -f "$DOCKERFILE" ]]; then
  echo "ERROR: Dockerfile not found: $DOCKERFILE" >&2
  exit 1
fi

# Detect container name if not provided
if [[ -z "${CONTAINER_NAME:-}" ]]; then
  CONTAINER_NAME="$(microk8s kubectl -n "$NAMESPACE" get deploy "$DEPLOYMENT" \
    -o jsonpath='{.spec.template.spec.containers[0].name}')"
  if [[ -z "$CONTAINER_NAME" ]]; then
    echo "ERROR: Could not detect container name for deploy/$DEPLOYMENT in ns/$NAMESPACE" >&2
    exit 1
  fi
fi

log "Building image: $IMAGE (Dockerfile: $DOCKERFILE)"
sudo docker build -f "$DOCKERFILE" -t "$IMAGE" .

log "Importing image into MicroK8s containerd: $IMAGE"
sudo docker save "$IMAGE" | sudo microk8s ctr image import -

log "Updating Deployment image: deploy/$DEPLOYMENT container/$CONTAINER_NAME -> $IMAGE"
microk8s kubectl -n "$NAMESPACE" set image "deploy/$DEPLOYMENT" "$CONTAINER_NAME=$IMAGE"

log "Waiting for rollout to complete..."
microk8s kubectl -n "$NAMESPACE" rollout status "deploy/$DEPLOYMENT"

log "Deployment is updated."
log "Current image:"
microk8s kubectl -n "$NAMESPACE" get deploy "$DEPLOYMENT" \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# Optional: port-forward and print OpenAPI paths
if [[ -n "$PORT_FORWARD_LOCAL" ]]; then
  log "Starting port-forward: localhost:${PORT_FORWARD_LOCAL} -> ${DEPLOYMENT}:${PORT_FORWARD_REMOTE}"
  # Run port-forward in background, capture PID, and ensure cleanup.
  microk8s kubectl -n "$NAMESPACE" port-forward "deploy/$DEPLOYMENT" \
    "${PORT_FORWARD_LOCAL}:${PORT_FORWARD_REMOTE}" >/tmp/ethelflow-portforward.log 2>&1 &
  PF_PID=$!
  trap 'log "Stopping port-forward (pid=$PF_PID)"; kill $PF_PID >/dev/null 2>&1 || true' EXIT

  # Give it a moment to come up
  sleep 1

  log "Printing OpenAPI paths from http://localhost:${PORT_FORWARD_LOCAL}/openapi.json"
  python3 - <<PY
import json, urllib.request
url = "http://localhost:${PORT_FORWARD_LOCAL}/openapi.json"
spec = json.load(urllib.request.urlopen(url, timeout=10))
for p in sorted(spec.get("paths", {}).keys()):
    print(p)
PY

  log "Port-forward is running (pid=$PF_PID). Press Ctrl+C to stop."
  wait "$PF_PID"
else
  log "Tip: to verify endpoints, run:"
  echo "  microk8s kubectl -n $NAMESPACE port-forward deploy/$DEPLOYMENT 18080:$PORT_FORWARD_REMOTE"
  echo "  python3 - <<'PY'"
  echo "import json, urllib.request"
  echo "spec=json.load(urllib.request.urlopen('http://localhost:18080/openapi.json'))"
  echo "print('\\n'.join(sorted(spec['paths'].keys())))"
  echo "PY"
fi

