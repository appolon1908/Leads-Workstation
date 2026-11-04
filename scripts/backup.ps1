param(
  [string]$DestinationRoot = "C:\Users\Usuario\Documents\Codestra-Backups\Leads-Workstation"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$db = Join-Path $Root "runtime\leads.db"
if (-not (Test-Path $db)) { throw "Runtime database not found. Run import-master.ps1 first." }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = Join-Path $DestinationRoot $stamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item $db (Join-Path $dest "leads.db") -Force
if (Test-Path (Join-Path $Root "data\manifests\private-local.json")) {
  Copy-Item (Join-Path $Root "data\manifests\private-local.json") (Join-Path $dest "private-local.json") -Force
}
Get-FileHash (Join-Path $dest "leads.db") -Algorithm SHA256 | Format-List
Write-Host "Backup created: $dest"

$global:LASTEXITCODE = 0
exit 0
