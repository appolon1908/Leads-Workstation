param([string]$Source = "C:\Users\Usuario\03_LEADS_AND_DATA\01_CORE\Master\MASTER_SALES_LEADS_20260921.csv")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path ".venv\Scripts\python.exe")) { & "$PSScriptRoot\install.ps1" }
if (-not (Test-Path $Source)) { throw "Master lead file not found: $Source" }
& ".venv\Scripts\python.exe" -m leads_workstation --db runtime\leads.db import-csv $Source
& ".venv\Scripts\python.exe" -m leads_workstation --db runtime\leads.db stats
