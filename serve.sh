#!/usr/bin/env bash
# Deploy (or delete) canonical Ray Serve multi-stage inference DAG (ray-serving01.yaml)
# across both cv-kuberay (Viewport A) and cv-kuberay-kueue (Viewport B).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env.local" ]]; then
  set -a
  source "${SCRIPT_DIR}/.env.local"
  set +a
elif [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  source "${SCRIPT_DIR}/.env"
  set +a
fi

CTX_A="${CLUSTER_A_CONTEXT:-cv-kuberay}"
CTX_B="${CLUSTER_B_CONTEXT:-cv-kuberay-kueue}"

ACTION="${1:-apply}"
if [[ "$ACTION" == "stop" || "$ACTION" == "down" || "$ACTION" == "rm" ]]; then
  ACTION="delete"
fi

EXTRA_ARGS=()
if [[ "$ACTION" == "delete" ]]; then
  EXTRA_ARGS=(--ignore-not-found)
fi

echo "▶ Running 'kubectl ${ACTION}' for ray-serving01.yaml on ${CTX_A} and ${CTX_B}..."
kubectl --context="${CTX_A}" "$ACTION" "${EXTRA_ARGS[@]}" -f "${SCRIPT_DIR}/ray-serving01.yaml" &
kubectl --context="${CTX_B}" "$ACTION" "${EXTRA_ARGS[@]}" -f "${SCRIPT_DIR}/ray-serving01.yaml" &
wait
echo "✓ Done (ray-serving01.yaml -> cv-kuberay & cv-kuberay-kueue)."
