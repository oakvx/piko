# Issue #4: user-initiated, non-destructive Windows acceptance for Piko.
# Runs controlled WinForms/UIA and genuine local Ollama tests; NEVER installs or uninstalls.
# Execute in an interactive Windows 10/11 x64 session, from a trusted repository checkout.
[CmdletBinding()]
param(
    [switch]$RunGui,
    [switch]$RunRealOllama,
    [string]$ReasoningModel,
    [string]$VisionModel,
    [string]$Installer,
    [string]$ChecksumFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This acceptance script requires Windows.'
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'Windows x64 is required.'
}
if (-not ($RunGui -or $RunRealOllama -or $Installer)) {
    throw 'Specify -RunGui and/or -RunRealOllama, or -Installer for checksum verification.'
}

$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$out = Join-Path $env:TEMP "piko-acceptance-$stamp"
New-Item -ItemType Directory -Force -Path $out | Out-Null

$os = Get-CimInstance Win32_OperatingSystem
$metadata = [ordered]@{
    category = 'local Windows desktop acceptance (not independent certification)'
    windows_caption = $os.Caption
    windows_build = $os.BuildNumber
    windows_architecture = $os.OSArchitecture
    source_commit = 'unknown'
    collected_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    gui_requested = [bool]$RunGui
    real_ollama_requested = [bool]$RunRealOllama
    reasoning_model = $ReasoningModel
    vision_model = $VisionModel
    installer_sha256_verified = $false
    test_report = 'not run'
    note = 'Review local JUnit and metadata before sharing; passing tests do not cover reboot, upgrade, WebView2 or physical held input.'
}

if (Get-Command git -ErrorAction SilentlyContinue) {
    $commit = & git -C $root rev-parse HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and $commit -match '^[0-9a-f]{40}$') {
        $metadata.source_commit = $commit
    }
}

try {
    if ($Installer) {
        $setup = (Resolve-Path -LiteralPath $Installer).Path
        if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
            throw 'Installer must be a real local file.'
        }
        if (-not $ChecksumFile) { $ChecksumFile = "$setup.sha256" }
        $checksum = (Resolve-Path -LiteralPath $ChecksumFile).Path
        $line = (Get-Content -LiteralPath $checksum -TotalCount 1).Trim()
        if ($line -notmatch '^([a-fA-F0-9]{64})(?:\s+\*?(.+))?$') {
            throw 'Invalid SHA256 sidecar format. Expected: 64 hex characters and optional filename.'
        }
        $expected = $Matches[1].ToLowerInvariant()
        $sidecarFilename = $Matches[2]
        if ($sidecarFilename -and $sidecarFilename.Trim() -ne (Split-Path -Leaf $setup)) {
            throw 'SHA256 sidecar refers to a different installer.'
        }
        $actual = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw 'Installer checksum mismatch: DO NOT launch the installer.'
        }
        $metadata.installer_sha256_verified = $true
        Write-Host 'PASS: installer SHA256 matches its sidecar. No installation was attempted.'
    }

    if ($RunGui -or $RunRealOllama) {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if (-not $launcher) { throw 'Python launcher not found. Install Python 3.11 x64 with py launcher.' }
        $pythonVersion = & py -3.11 -c 'import sys; print(sys.version_info[:2] == (3, 11))'
        if ($LASTEXITCODE -ne 0 -or $pythonVersion.Trim() -ne 'True') {
            throw 'Python 3.11 is required for this isolated test environment.'
        }

        if ($RunRealOllama) {
            if (-not $ReasoningModel -or -not $VisionModel) {
                throw 'Both -ReasoningModel and -VisionModel are required for real Ollama.'
            }
            try {
                $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 6
            } catch {
                throw 'Ollama local service is unavailable on 127.0.0.1:11434.'
            }
            $names = @($tags.models | ForEach-Object { $_.name })
            if ($names -notcontains $ReasoningModel -or $names -notcontains $VisionModel) {
                throw 'Both named models must already be installed in Ollama. Check ollama list.'
            }
            $env:PIKO_REAL_OLLAMA = '1'
            $env:PIKO_OLLAMA_REASONING_MODEL = $ReasoningModel
            $env:PIKO_OLLAMA_VISION_MODEL = $VisionModel
        } else {
            Remove-Item Env:PIKO_REAL_OLLAMA -ErrorAction SilentlyContinue
        }

        if ($RunGui) {
            Write-Host 'Native tests will open and control a disposable WinForms testbench. Keep it in the foreground.'
            $env:PIKO_GUI_SMOKE = '1'
        } else {
            Remove-Item Env:PIKO_GUI_SMOKE -ErrorAction SilentlyContinue
        }

        $venv = Join-Path $out 'venv'
        & py -3.11 -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated Python 3.11 environment.' }
        $python = Join-Path $venv 'Scripts/python.exe'
        & $python -m pip install -e "$root[windows,dev]"
        if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

        $paths = @()
        if ($RunGui) { $paths += (Join-Path $root 'tests/windows') }
        if ($RunRealOllama) {
            $paths += (Join-Path $root 'tests/real/test_ollama_inference.py')
            if ($RunGui) {
                $agentTest = Join-Path $root 'tests/real/test_ollama_windows_agent.py'
                if (-not (Test-Path -LiteralPath $agentTest -PathType Leaf)) {
                    throw 'Model-driven native Agent E2E test is missing. Use a checkout with PR #24 merged.'
                }
                $paths += $agentTest
            }
        }

        $xml = Join-Path $out 'pytest-results.xml'
        & $python -m pytest -q -rs "--junitxml=$xml" @paths
        $code = $LASTEXITCODE
        $metadata.test_report = 'pytest-results.xml'
        if (-not (Test-Path -LiteralPath $xml -PathType Leaf)) {
            throw 'No JUnit test report was generated.'
        }
        [xml]$report = Get-Content -LiteralPath $xml -Raw
        $suites = @($report.SelectNodes('//testsuite'))
        $skipped = 0
        $executed = 0
        foreach ($suite in $suites) {
            $skipped += [int]$suite.skipped
            $executed += [int]$suite.tests
        }
        if ($code -ne 0 -or $executed -eq 0 -or $skipped -ne 0) {
            throw "Acceptance failed: pytest exit=$code, tests=$executed, skipped=$skipped. See JUnit."
        }
        Write-Host "PASS: $executed requested test cases, no skips; native/Ollama report at $xml"
    }
} finally {
    $metadata | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $out 'metadata.json') -Encoding UTF8
    Write-Host "Acceptance evidence (private, local): $out"
}
