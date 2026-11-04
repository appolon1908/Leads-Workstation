$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Private = Join-Path $Root "data\private"
New-Item -ItemType Directory -Force -Path $Private | Out-Null
$WorkspaceSrc = "C:\Users\Usuario\03_LEADS_AND_DATA"
$IncomingSrc = "C:\Users\Usuario\Downloads\Evelin-Leads-2026-09-29"
$WorkspaceDst = Join-Path $Private "workspace"
$IncomingDst = Join-Path $Private "incoming\2026-09-29-appraisers"
if (Test-Path $WorkspaceSrc) {
  robocopy $WorkspaceSrc $WorkspaceDst /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XD "__pycache__" | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy workspace failed with $LASTEXITCODE" }
}
if (Test-Path $IncomingSrc) {
  robocopy $IncomingSrc $IncomingDst /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy incoming failed with $LASTEXITCODE" }
}
Write-Host "Private lead data staged under $Private"
Write-Host "This directory remains git-ignored until repository privacy is verified."
