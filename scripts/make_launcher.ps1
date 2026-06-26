<#
Create a double-clickable Desktop launcher for the GUI — no console window, with the brain icon —
using the 'rpcoding' conda environment. Run once:

    powershell -ExecutionPolicy Bypass -File scripts\make_launcher.ps1

(Command-line launch still works: `conda activate rpcoding; rpcoding-gui`  — or  `python -m rpcoding.gui.app`.)
#>
$ErrorActionPreference = "Stop"
$EnvName = "rpcoding"

function Get-CondaOutput([string]$code) {
    # Last non-empty stdout line from running Python in the env (ignores conda's own chatter).
    $out = conda run -n $EnvName python -c $code 2>$null
    return ($out | Where-Object { $_ -match '\S' } | Select-Object -Last 1).Trim()
}

Write-Host "Locating the '$EnvName' conda environment..."
$envPython = Get-CondaOutput "import sys; print(sys.executable)"
if (-not $envPython -or -not (Test-Path $envPython)) {
    throw "Couldn't find the '$EnvName' conda env. Run scripts\setup_env.ps1 first."
}
$envRoot = Split-Path $envPython
$guiExe = Join-Path $envRoot "Scripts\rpcoding-gui.exe"   # gui-script: launches without a console
$pythonw = Join-Path $envRoot "pythonw.exe"
$icon = Get-CondaOutput "from rpcoding.gui.assets import ico_path; print(ico_path())"

if (Test-Path $guiExe) {
    $target = $guiExe; $arguments = ""
} elseif (Test-Path $pythonw) {
    $target = $pythonw; $arguments = "-m rpcoding.gui.app"
} else {
    throw "Couldn't find rpcoding-gui.exe or pythonw.exe in the env."
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "Cogan Lab RP Coding Toolbox.lnk"
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = $target
if ($arguments) { $lnk.Arguments = $arguments }
if ($icon -and (Test-Path $icon)) { $lnk.IconLocation = "$icon,0" }
$lnk.Description = "Cogan Lab RP Coding Toolbox"
$lnk.WorkingDirectory = $envRoot
$lnk.Save()

Write-Host ""
Write-Host "Created launcher: $lnkPath"
Write-Host "Double-click it (or pin it to the taskbar) to open Cogan Lab RP Coding Toolbox."
