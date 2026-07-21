param(
    [string]$Repository = "\\NAS\docker\nas-stack",
    [string]$Remote = "origin",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Repository)) {
    Write-Error "NAS repository not found: $Repository"
    exit 1
}

$Status = & git -c maintenance.auto=false -C $Repository status --porcelain
if ($LASTEXITCODE -ne 0) {
    Write-Error "Unable to read NAS repository status."
    exit $LASTEXITCODE
}

if ($Status) {
    Write-Host "NAS repository has local changes; pull aborted:" -ForegroundColor Yellow
    $Status | ForEach-Object { Write-Host $_ }
    Write-Host "Stash or remove these changes before retrying."
    exit 2
}

Write-Host "Fetching $Remote without automatic maintenance..." -ForegroundColor Cyan
& git -c maintenance.auto=false -C $Repository fetch --no-auto-maintenance $Remote
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Fast-forwarding to $Remote/$Branch..." -ForegroundColor Cyan
& git -c maintenance.auto=false -C $Repository merge --ff-only "$Remote/$Branch"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$Head = & git -c maintenance.auto=false -C $Repository rev-parse HEAD
$RemoteHead = & git -c maintenance.auto=false -C $Repository rev-parse "$Remote/$Branch"
if ($LASTEXITCODE -ne 0 -or $Head -ne $RemoteHead) {
    Write-Error "NAS HEAD does not match $Remote/$Branch after pull."
    exit 3
}

Write-Host "NAS repository is up to date: $Head" -ForegroundColor Green
