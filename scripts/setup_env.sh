#!/usr/bin/env bash
# Create the `rpcoding` conda environment and prepare MFA models/dictionaries.
# Usage:  bash scripts/setup_env.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="rpcoding"

if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda not found on PATH." >&2
    echo "Install Miniforge (https://github.com/conda-forge/miniforge) or activate conda first." >&2
    exit 1
fi

echo "==> Creating/updating conda env '$ENV_NAME' from environment.yml"
if conda env list | grep -qE "^\s*${ENV_NAME}\s"; then
    conda env update -n "$ENV_NAME" -f "$HERE/environment.yml" --prune
else
    conda env create -f "$HERE/environment.yml"
fi

echo "==> Downloading MFA acoustic model + dictionary (idempotent)"
conda run -n "$ENV_NAME" mfa model download acoustic english_us_arpa || true
conda run -n "$ENV_NAME" mfa model download dictionary english_us_arpa || true

echo "==> Installing the vendored custom lexical (nonword) dictionary"
# Implemented in feat/mfa-integration: `python -m rpcoding.core.mfa.models --install-dicts`
conda run -n "$ENV_NAME" python -m rpcoding.core.mfa.models --install-dicts 2>/dev/null \
    || echo "    (skipped — available once feat/mfa-integration lands)"

echo "==> Done. Activate with:  conda activate $ENV_NAME"
