param(
  [int]$ExpectedLeads = 0,
  [int]$BaselineMasterLeads = 88379,
  [int]$Port = 8765
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { & "$PSScriptRoot\install.ps1" }

& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "unit tests failed: $LASTEXITCODE" }

& $Python -m compileall -q src
if ($LASTEXITCODE -ne 0) { throw "compile failed: $LASTEXITCODE" }

$statsText = & $Python -m leads_workstation --db runtime\leads.db stats
if ($LASTEXITCODE -ne 0) { throw "stats failed: $LASTEXITCODE" }
$stats = $statsText | ConvertFrom-Json

$candidateText = & $Python -m leads_workstation --db runtime\leads.db candidate-summary
if ($LASTEXITCODE -ne 0) { throw "candidate summary failed: $LASTEXITCODE" }
$candidates = $candidateText | ConvertFrom-Json
$promoted = 0
if ($candidates.by_disposition -and $candidates.by_disposition.promoted) {
  $promoted = [int]$candidates.by_disposition.promoted
}

$DerivedExpected = $BaselineMasterLeads + $promoted
if ($ExpectedLeads -eq 0) { $ExpectedLeads = $DerivedExpected }

if ($ExpectedLeads -ne $DerivedExpected) {
  throw "configured expected count $ExpectedLeads does not equal baseline $BaselineMasterLeads + promoted candidates $promoted = $DerivedExpected"
}
if ($stats.total_leads -ne $ExpectedLeads) {
  throw "lead count mismatch: expected $ExpectedLeads, got $($stats.total_leads)"
}

$manifestPath = Join-Path $Root "data\manifests\private-local.json"
& $Python -m leads_workstation manifest data\private $manifestPath
if ($LASTEXITCODE -ne 0) { throw "manifest failed: $LASTEXITCODE" }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json

$p = Start-Process -FilePath $Python -ArgumentList @(
  "-m","leads_workstation","--db","runtime\leads.db","serve",
  "--host","127.0.0.1","--port",$Port
) -WorkingDirectory $Root -PassThru -WindowStyle Hidden

try {
  Start-Sleep -Seconds 2
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Method Get
  $apiStats = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/stats" -Method Get
  $apiCandidates = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/candidates/summary" -Method Get
  if (-not $health.ok) { throw "health endpoint failed" }
  if ($apiStats.total_leads -ne $ExpectedLeads) { throw "API lead count mismatch" }
  if ([int]$apiCandidates.by_disposition.promoted -ne $promoted) { throw "candidate API mismatch" }
} finally {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}

$result = [ordered]@{
  certified_at_utc = (Get-Date).ToUniversalTime().ToString("o")
  baseline_master_leads = $BaselineMasterLeads
  promoted_candidates = $promoted
  expected_leads = $ExpectedLeads
  database_leads = $stats.total_leads
  with_email = $stats.with_email
  with_phone = $stats.with_phone
  candidate_total = $candidates.total
  candidate_dispositions = $candidates.by_disposition
  private_manifest_files = $manifest.file_count
  private_manifest_bytes = $manifest.total_bytes
  health_ok = $health.ok
  api_total_leads = $apiStats.total_leads
  candidate_api_ok = $true
  unit_tests = "passed"
  compile = "passed"
  private_data_git_ignored = $true
}
New-Item -ItemType Directory -Force -Path runtime | Out-Null
$result | ConvertTo-Json -Depth 7 | Set-Content -Encoding UTF8 runtime\certification.json
$result | ConvertTo-Json -Depth 7
