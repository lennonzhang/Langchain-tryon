Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remote = if ($args.Length -ge 1 -and $args[0]) { $args[0] } else { "origin" }
$pattern = if ($args.Length -ge 2 -and $args[1]) { $args[1] } else { "v*" }

git fetch $remote --tags --prune --quiet

$latestTag = git tag -l $pattern --sort=-v:refname | Select-Object -First 1

if (-not $latestTag) {
    Write-Error "No tags found matching pattern '$pattern' after fetching from $remote."
    exit 1
}

Write-Output $latestTag
