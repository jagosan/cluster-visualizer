#!/usr/bin/env bash
# Deploy (or delete) canonical KubeRay + Kueue LoRA fine-tuning RayJob (ray-kueue-ft01.yaml)
# across both cv-kuberay (Viewport A) and cv-kuberay-kueue (Viewport B).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-apply}"
if [[ "$ACTION" == "stop" || "$ACTION" == "down" || "$ACTION" == "rm" ]]; then
  ACTION="delete"
fi

EXTRA_ARGS=()
if [[ "$ACTION" == "delete" ]]; then
  EXTRA_ARGS=(--ignore-not-found)
fi

echo "▶ Running 'kubectl ${ACTION}' for ray-kueue-ft01.yaml on cv-kuberay and cv-kuberay-kueue..."
kubectl --context=cv-kuberay "$ACTION" "${EXTRA_ARGS[@]}" -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml" &
kubectl --context=cv-kuberay-kueue "$ACTION" "${EXTRA_ARGS[@]}" -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml" &
wait
echo "✓ Done (ray-kueue-ft01.yaml -> cv-kuberay & cv-kuberay-kueue)."
