#!/usr/bin/env bash
# Trigger (or clear) an Overwhelm workload surge across both cv-kuberay (Viewport A)
# and cv-kuberay-kueue (Viewport B) without exhausting physical GKE node capacity:
#   - Deploys ray-serving01.yaml + ray-kueue-ft01.yaml + ray-overwhelm-burst.yaml
#   - Viewport A (cv-kuberay): All 3 fine-tuning gangs flood the Worker Deck at once,
#     causing noisy-neighbor contention (amber/red alerts) and severe floor spring separation.
#   - Viewport B (cv-kuberay-kueue): Kueue holds ft02 & ft03 in Staging Cargo Pallets
#     while llm-d routes the traffic surge across warm KV-cache replicas, keeping floors calm.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-apply}"
if [[ "$ACTION" == "stop" || "$ACTION" == "down" || "$ACTION" == "rm" || "$ACTION" == "clear" ]]; then
  ACTION="delete"
fi

if [[ "$ACTION" == "delete" ]]; then
  echo "▶ Clearing overwhelm burst (ray-overwhelm-burst.yaml) from cv-kuberay and cv-kuberay-kueue..."
  kubectl --context=cv-kuberay delete --ignore-not-found -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml" &
  kubectl --context=cv-kuberay-kueue delete --ignore-not-found -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml" &
  wait
  echo "✓ Overwhelm burst cleared."
else
  echo "▶ Launching Overwhelm Surge (serving + ft01 + ft02 + ft03 + traffic surge) on cv-kuberay and cv-kuberay-kueue..."
  (
    kubectl --context=cv-kuberay apply -f "${SCRIPT_DIR}/ray-serving01.yaml"
    kubectl --context=cv-kuberay apply -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml"
    kubectl --context=cv-kuberay apply -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml"
  ) &
  (
    kubectl --context=cv-kuberay-kueue apply -f "${SCRIPT_DIR}/ray-serving01.yaml"
    kubectl --context=cv-kuberay-kueue apply -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml"
    kubectl --context=cv-kuberay-kueue apply -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml"
  ) &
  wait
  echo "✓ Overwhelm Surge active on both clusters!"
  echo "  • cv-kuberay (Viewport A): Unqueued batch stampede -> floors heave apart (+6u ΔY, ~800ms p99)"
  echo "  • cv-kuberay-kueue (Viewport B): Kueue queues ft02/ft03 in Cargo Pallets + llm-d KV routing -> floors stay calm (~12ms p99)"
fi
