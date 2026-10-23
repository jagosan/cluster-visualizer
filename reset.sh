#!/usr/bin/env bash
# Reset both cv-kuberay and cv-kuberay-kueue back to baseline by deleting
# ray-overwhelm-burst.yaml, ray-kueue-ft01.yaml, and ray-serving01.yaml.
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

echo "▶ Resetting demo workloads on ${CTX_A} and ${CTX_B}..."
(
  kubectl --context="${CTX_A}" delete --ignore-not-found \
    -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml" \
    -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml" \
    -f "${SCRIPT_DIR}/ray-serving01.yaml"
) &
(
  kubectl --context="${CTX_B}" delete --ignore-not-found \
    -f "${SCRIPT_DIR}/ray-overwhelm-burst.yaml" \
    -f "${SCRIPT_DIR}/ray-kueue-ft01.yaml" \
    -f "${SCRIPT_DIR}/ray-serving01.yaml"
) &
wait
echo "✓ Both cv-kuberay and cv-kuberay-kueue reset to clean baseline."
