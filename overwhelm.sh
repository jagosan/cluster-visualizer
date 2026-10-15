#!/usr/bin/env bash
# Trigger (or clear) an Overwhelm workload surge across both cv-kuberay (Viewport A)
# and cv-kuberay-kueue (Viewport B) without exhausting physical GKE node capacity:
#   - Deploys ray-serving01.yaml + ray-kueue-ft01.yaml + ray-overwhelm-burst.yaml
#   - Viewport A (cv-kuberay): All 3 fine-tuning gangs flood the 2-node Worker Deck at once,
#     causing noisy-neighbor contention (amber/red alerts) and severe floor spring separation.
#   - Viewport B (cv-kuberay-kueue):
#       1. [0s–9s]   Kueue holds ft02 & ft03 as Inadmissible in Cargo Containment Pallets
#                    while ComputeClass (kueue-spot-burst-cc) + Cluster Autoscaler provisions
#                    a B1 Ghost Node (worker-3 / g2-standard-48) with amber tractor beams.
#       2. [9s–13s]  Ghost Node ready -> Kueue QuotaReserved (Gantry Lock + Amber Beacons).
#       3. [13s–16s] Kueue Admitted -> High-Speed Emerald Mag-Rail Transit + Gang Burst.
#       4. [16s+]    Worker Deck widens from 2 -> 3 nodes (worker-3 g2-standard-48 Spot GPU)
#                    and runs all 3 gangs with In-Place VPA vertical pod resizing!
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
  echo "✓ Overwhelm burst cleared (worker-3 scaled back down to 2-node baseline)."
else
  SURGE_TS="$(date +%s)"
  echo "▶ Launching Overwhelm Surge + ComputeClass Autoscaling (ts=${SURGE_TS}) on cv-kuberay and cv-kuberay-kueue..."
  (
    kubectl --context=cv-kuberay apply -f "${SCRIPT_DIR}/ray-serving01.yaml"
    kubectl --context=cv-kuberay apply -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml"
    kubectl --context=cv-kuberay apply -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml"
  ) &
  (
    kubectl --context=cv-kuberay-kueue apply -f "${SCRIPT_DIR}/kueue-spot-burst-cc.yaml" >/dev/null 2>&1 || true
    kubectl --context=cv-kuberay-kueue apply -f "${SCRIPT_DIR}/kueue-queues.yaml" >/dev/null 2>&1 || true
    kubectl --context=cv-kuberay-kueue apply -f "${SCRIPT_DIR}/ray-serving01.yaml"
    kubectl --context=cv-kuberay-kueue apply -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml"
    kubectl --context=cv-kuberay-kueue delete job ray-kueue-ft02-job ray-kueue-ft03-job --ignore-not-found >/dev/null 2>&1 || true
    kubectl --context=cv-kuberay-kueue apply -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml"
    kubectl --context=cv-kuberay-kueue annotate pods -l app=ray-traffic-surge "clustervis.io/surge-ts=${SURGE_TS}" --overwrite >/dev/null 2>&1 || true
    kubectl --context=cv-kuberay-kueue annotate pods -l app=ray-kueue-ft02-head "clustervis.io/surge-ts=${SURGE_TS}" --overwrite >/dev/null 2>&1 || true
  ) &
  wait
  echo "✓ Overwhelm Surge active on both clusters!"
  echo "  • cv-kuberay (Viewport A): Unqueued batch stampede on 2 nodes -> floors heave apart (+6u ΔY, ~680ms p99)"
  echo "  • cv-kuberay-kueue (Viewport B): Watch Autopilot ComputeClass (EK VMs) + Cluster Autoscaler in action:"
  echo "      [0s–6s]    ft02 & ft03 held Inadmissible in Kueue Pallets; CA starts resizing EK VM worker-2 & provisioning B1 Ghost Node worker-3"
  echo "      [6s–11s]   ⚡ EK VM RUNTIME RESIZE: worker-2 expands in-place (ek-standard-16 -> ek-standard-48) & admits ft02! Meanwhile ft03 locks Gantry Crane (QuotaReserved)"
  echo "      [11s–15s]  ⚡ HORIZONTAL SCALE-OUT: ft03 rides Emerald Mag-Rail onto newly provisioned worker-3 (ek-standard-32)"
  echo "      [15s+]     Settled 3-node deck: worker-1 (16 vCPU) + EK-Resized worker-2 (48 vCPU) + Autoscaled worker-3 (32 vCPU)"
fi
