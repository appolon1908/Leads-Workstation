$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Candidates = @(
  (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
  "C:\Users\Usuario\AppData\Local\Programs\Python\Python312\python.exe",
  "C:\Users\Usuario\AppData\Local\Programs\Python\Python311\python.exe"
) | Where-Object { $_ -and (Test-Path $_) }
if (-not $Candidates) { throw "Python 3.11+ not found." }
$Candidates = @($Candidates)
$Python = $Candidates[0]
Write-Host "Using Python: $Python"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $Python -m venv .venv }
& ".venv\Scripts\python.exe" -m pip install -e .
& ".venv\Scripts\python.exe" -m leads_workstation --db runtime\leads.db init-db
Write-Host "Installed. Run scripts\import-master.ps1 then scripts\start.ps1"
