[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$versionPath = Join-Path $PSScriptRoot '..\app\VERSION'
$currentVersion = (Get-Content -LiteralPath $versionPath -Raw).Trim()

if ($currentVersion -notmatch '^v(?<major>\d+)\.(?<minor>\d+)\.(?<release>\d{2})$') {
    throw "Invalid version '$currentVersion'. Expected v<major>.<minor>.<two-digit release>."
}

$major = [int]$Matches.major
$minor = [int]$Matches.minor
$release = [int]$Matches.release

if ($release -eq 99) {
    $minor += 1
    $release = 0
} else {
    $release += 1
}

$nextVersion = 'v{0}.{1}.{2:D2}' -f $major, $minor, $release
Set-Content -LiteralPath $versionPath -Value $nextVersion -Encoding utf8NoBOM
Write-Output $nextVersion
