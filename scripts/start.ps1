param([int]$Port = 8765)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path ".venv\Scripts\python.exe")) { & "$PSScriptRoot\install.ps1" }
& ".venv\Scripts\python.exe" -m leads_workstation --db runtime\leads.db serve --host 127.0.0.1 --port $Port
