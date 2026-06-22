# Create the `rpcoding` conda environment and prepare MFA models/dictionaries.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
#Requires -Version 5
$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $PSScriptRoot
$EnvName = 'rpcoding'

function Find-Conda {
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:USERPROFILE\miniconda3\condabin\conda.bat",
        "$env:USERPROFILE\miniforge3\condabin\conda.bat",
        "$env:USERPROFILE\anaconda3\condabin\conda.bat",
        "D:\conda\miniconda3\condabin\conda.bat"
    )
    foreach ($p in $candidates) { if (Test-Path $p) { return $p } }
    return $null
}

$conda = Find-Conda
if (-not $conda) {
    Write-Error "conda not found. Install Miniforge or put conda on PATH, then re-run."
    exit 1
}
Write-Host "Using conda: $conda"

$envExists = (& $conda env list) -match "^\s*$EnvName\s"
Write-Host "==> Creating/updating conda env '$EnvName' from environment.yml"
if ($envExists) {
    & $conda env update -n $EnvName -f (Join-Path $Here 'environment.yml') --prune
} else {
    & $conda env create -f (Join-Path $Here 'environment.yml')
}

Write-Host "==> Downloading MFA acoustic model + dictionary (idempotent)"
& $conda run -n $EnvName mfa model download acoustic english_us_arpa
& $conda run -n $EnvName mfa model download dictionary english_us_arpa

Write-Host "==> Installing the vendored custom lexical (nonword) dictionary"
# Implemented in feat/mfa-integration: python -m rpcoding.core.mfa.models --install-dicts
try {
    & $conda run -n $EnvName python -m rpcoding.core.mfa.models --install-dicts
} catch {
    Write-Host "    (skipped — available once feat/mfa-integration lands)"
}

Write-Host "==> Done. Activate with:  conda activate $EnvName"
