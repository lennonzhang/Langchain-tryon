Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = $null

try {
    $repoRoot = (& git -C $scriptDir rev-parse --show-toplevel 2>$null)
} catch {
    $repoRoot = $null
}

if (-not $repoRoot) {
    $repoRoot = Resolve-Path (Join-Path $scriptDir "..\\..\\..\\..")
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    Write-Host "Running $Label..."
    & $Command

    if ($LASTEXITCODE -ne 0) {
        Write-Error "code-change-verification: $Label failed with exit code $LASTEXITCODE."
        exit $LASTEXITCODE
    }
}

Set-Location $repoRoot
Invoke-Step -Label "backend tests" -Command {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
}

Set-Location (Join-Path $repoRoot "frontend-react")
Invoke-Step -Label "frontend tests" -Command { pnpm test }
Invoke-Step -Label "frontend e2e tests" -Command { pnpm test:e2e }
Invoke-Step -Label "frontend visual tests" -Command { pnpm test:visual }
Invoke-Step -Label "frontend build" -Command { pnpm run build }

Write-Host "code-change-verification: all commands passed."
