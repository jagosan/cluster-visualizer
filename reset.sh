#!/usr/bin/env bash
# Reset both cv-kuberay and cv-kuberay-kueue back to baseline by deleting
# ray-overwhelm-burst.yaml, ray-kueue-ft01.yaml, and ray-serving01.yaml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "▶ Resetting demo workloads on cv-kuberay and cv-kuberay-kueue..."
(
  kubectl --context=cv-kuberay delete --ignore-not-found \
    -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml" \
    -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml" \
    -f "${SCRIPT_DIR}/ray-serving01.yaml"
) &
(
  kubectl --context=cv-kuberay-kueue delete --ignore-not-found \
    -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml" \
    -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml" \
    -f "${SCRIPT_DIR}/ray-serving01.yaml"
) &
wait
echo "✓ Both cv-kuberay and cv-kuberay-kueue reset to clean baseline."
