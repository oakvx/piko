$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location $root
python -m pip install --disable-pip-version-check -r scripts/ci/backend-windows.lock
if ($LASTEXITCODE -ne 0) { throw 'Locked Python dependency install failed' }
python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Locked Python dependencies conflict' }
python -m PyInstaller --clean --noconfirm --onefile --console --name piko-agent --collect-all pywinauto --collect-all comtypes --collect-all mss --collect-all pynput --collect-all PIL --paths src scripts/ci/piko_sidecar.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
$target = 'x86_64-pc-windows-msvc'
$destination = Join-Path $root "apps/desktop/src-tauri/binaries/piko-agent-$target.exe"
New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
Copy-Item (Join-Path $root 'dist/piko-agent.exe') $destination -Force
& $destination --help
if ($LASTEXITCODE -ne 0) { throw 'Packed Python backend did not launch' }
Write-Host "Prepared sidecar: $destination"
