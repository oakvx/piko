param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$Commit,
    [Parameter(Mandatory = $true)][ValidateRange(1, 65535)][int]$Build
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$nsis = Join-Path $root 'apps/desktop/src-tauri/target/release/bundle/nsis'
if (-not (Test-Path $nsis)) { throw "NSIS output directory missing: $nsis" }
$files = @(Get-ChildItem -Path $nsis -Filter '*setup.exe' -File)
if ($files.Count -ne 1) { throw "Expected one NSIS setup.exe, found $($files.Count)" }
if ($files[0].Length -lt 1048576) { throw 'Installer unexpectedly small; refusing to publish' }
$stream = [System.IO.File]::OpenRead($files[0].FullName)
try {
    if ($stream.ReadByte() -ne 0x4d -or $stream.ReadByte() -ne 0x5a) {
        throw 'Installer does not start with a Windows MZ executable header'
    }
} finally { $stream.Dispose() }
$out = Join-Path $root 'distribution'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$short = $Commit.Substring(0, 12)
$name = "Pico-0.1.$Build-$short-windows-x64-setup.exe"
Copy-Item $files[0].FullName (Join-Path $out $name) -Force
$hash = (Get-FileHash (Join-Path $out $name) -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText((Join-Path $out "$name.sha256"), "$hash  $name`n", [System.Text.UTF8Encoding]::new($false))
Write-Host "Verified installer: $name (SHA256 $hash)"
