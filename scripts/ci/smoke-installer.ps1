param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$Commit
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$distribution = Join-Path $root 'distribution'
$short = $Commit.Substring(0, 12)
$setups = @(Get-ChildItem -Path $distribution -File -Filter "Piko-*-$short-windows-x64-setup.exe")
if ($setups.Count -ne 1) { throw "Expected exactly one setup EXE for $short, found $($setups.Count)" }
$setup = $setups[0].FullName
$sidecarNames = @('piko-agent')
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'

function Get-PikoUninstallEntry {
    @(Get-ItemProperty "$uninstallKey\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -eq 'Piko' })
}

function Wait-Until([scriptblock]$Condition, [int]$Seconds = 30) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

if ((Get-PikoUninstallEntry).Count -gt 0) {
    throw 'Not a clean Windows test machine: Piko is already installed'
}

$setupProcess = Start-Process -FilePath $setup -ArgumentList '/S' -Wait -PassThru
if ($setupProcess.ExitCode -ne 0) { throw "NSIS silent setup failed with exit code $($setupProcess.ExitCode)" }

$appProcess = $null
$installedExecutable = $null
$uninstallExecutable = $null
try {
    if (-not (Wait-Until { (Get-PikoUninstallEntry).Count -eq 1 })) {
        throw 'NSIS setup completed, but a Piko uninstall registry record is missing'
    }
    $entries = @(Get-PikoUninstallEntry)
    $entry = $entries[0]
    if ($null -eq $entry.PSObject.Properties['UninstallString']) {
        throw 'NSIS registry record does not contain UninstallString'
    }
    $uninstallCommand = [string]$entry.UninstallString
    if ($uninstallCommand -match '^"([^"]+\.exe)"') {
        $uninstallExecutable = $Matches[1]
    } elseif ($uninstallCommand -match '^(.+?\.exe)(?:\s|$)') {
        $uninstallExecutable = $Matches[1]
    } else {
        throw "Unable to parse NSIS uninstall executable: $uninstallCommand"
    }
    if (-not (Test-Path -LiteralPath $uninstallExecutable -PathType Leaf)) {
        throw 'NSIS uninstall executable is missing from installation folder'
    }

    $folder = Split-Path -Parent $uninstallExecutable
    $installedExecutable = Join-Path $folder 'Piko.exe'
    if (-not (Test-Path -LiteralPath $installedExecutable -PathType Leaf)) {
        throw 'Piko.exe was not installed alongside the NSIS uninstaller'
    }
    Write-Host "Real installed executable found: $installedExecutable"

    $appProcess = Start-Process -FilePath $installedExecutable -PassThru
    if (-not (Wait-Until {
        $appProcess.Refresh()
        (-not $appProcess.HasExited) -and
        (@(Get-Process -Name $sidecarNames -ErrorAction SilentlyContinue).Count -gt 0)
    } 35)) {
        throw 'Installed Piko did not start its bundled Python sidecar'
    }
    Write-Host 'Installed Piko launched and the bundled sidecar is alive'

    $appProcess.Refresh()
    if (-not $appProcess.CloseMainWindow()) {
        throw 'Installed Piko did not expose a closable desktop window'
    }
    if (-not (Wait-Until { $appProcess.Refresh(); $appProcess.HasExited } 20)) {
        throw 'Desktop application did not exit when its window was closed'
    }
    if (-not (Wait-Until { @(Get-Process -Name $sidecarNames -ErrorAction SilentlyContinue).Count -eq 0 } 20)) {
        throw 'Bundled sidecar was not terminated on Piko window close'
    }
    Write-Host 'Closing the desktop window correctly stopped its sidecar'
} finally {
    if ($null -ne $appProcess) {
        $appProcess.Refresh()
        if (-not $appProcess.HasExited) {
            Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if ($null -ne $uninstallExecutable -and (Test-Path -LiteralPath $uninstallExecutable -PathType Leaf)) {
        $uninstallProcess = Start-Process -FilePath $uninstallExecutable -ArgumentList '/S' -Wait -PassThru
        if ($uninstallProcess.ExitCode -ne 0) {
            Write-Warning "NSIS silent uninstall exited $($uninstallProcess.ExitCode)"
        }
        if (-not (Wait-Until { (Get-PikoUninstallEntry).Count -eq 0 } 20)) {
            throw 'NSIS uninstall did not remove the Piko registry entry'
        }
        if ($null -ne $installedExecutable -and
            (Test-Path -LiteralPath $installedExecutable -PathType Leaf)) {
            throw 'NSIS uninstall did not remove Piko.exe'
        }
        Write-Host 'NSIS silent uninstall removed application executable and registration'
    }
}
