param(
    [string]$Destination,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
function Get-PackageHash([string]$Path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}
$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'CONTENTS.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.files) {
    $source = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $entry.path))
    if (-not $source.StartsWith($packageRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Package manifest contains a path outside the package.'
    }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing package file: $($entry.path)" }
    if ((Get-PackageHash $source) -ne $entry.sha256) {
        throw "Package file does not match manifest: $($entry.path)"
    }
}
if ($CheckOnly) {
    Write-Output "Package verified: $($manifest.files.Count) files. No installation performed."
    exit 0
}
if (-not $Destination -and (Get-Process -Name ingetrazo -ErrorAction SilentlyContinue)) {
    throw 'Close IngeTrazo, then run Install.cmd again. No files have been installed.'
}
if (-not $Destination) { $Destination = Join-Path $env:APPDATA 'ingetrazo/plugins/ingetrazo_d5_sync' }
$target = [IO.Path]::GetFullPath($Destination)
$dataRoot = Join-Path $env:LOCALAPPDATA 'IngeTrazo/d5_sync'
$backup = $null
if (Test-Path -LiteralPath $target) {
    $backup = Join-Path $dataRoot ('install-backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item -LiteralPath $target -Destination $backup -Recurse
    Write-Output "Previous plugin backed up to: $backup"
}
foreach ($entry in $manifest.files) {
    if (-not $entry.path.StartsWith('ingetrazo_d5_sync/')) { continue }
    $relative = $entry.path.Substring('ingetrazo_d5_sync/'.Length)
    $source = Join-Path $PSScriptRoot $entry.path
    $file = Join-Path $target $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $file) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $file -Force
    if ((Get-PackageHash $file) -ne $entry.sha256) {
        throw "Installed file verification failed: $relative"
    }
}
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
@{target=$target; backup=$backup; timestamp=(Get-Date -Format o); version=$manifest.version} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dataRoot 'last-install.json') -Encoding utf8
Write-Output "Installed connector: $target"
Write-Output 'Start IngeTrazo. D5 Render and the matching Python/LiveSync dependencies must already be installed.'
