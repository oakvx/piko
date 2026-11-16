# Issue #4 — Windows 10/11 local acceptance

This is a **user-run test on a controlled interactive desktop**, not equivalent
to hosted Windows Server CI. Do not run against banking apps, personal files,
credentials, or production systems. Keep the WinForms testbench in the
foreground for live UIA tests.

## Requirements

- Windows 10/11 x64 and an interactive Windows desktop session.
- Checked-out Piko repository, including PR #24 changes for model-driven native UIA.
- Python 3.11 x64 with the Windows py launcher.
- Local Ollama running at 127.0.0.1:11434 with two already-installed models.
  Use 'ollama list' to verify exact names. The script never downloads models.

## Run native UIA and genuine model-driven acceptance

From the Piko checkout root, open PowerShell:

~~~powershell
# Install models explicitly ONLY if not already installed:
ollama pull qwen2.5:3b
ollama pull qwen3-vl:2b-instruct

# Real Windows GUI + real Ollama reasoning/vision + actual native Agent:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\acceptance\windows-local.ps1 -RunGui -RunRealOllama -ReasoningModel 'qwen2.5:3b' -VisionModel 'qwen3-vl:2b-instruct'
~~~

For native GUI tests only:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\acceptance\windows-local.ps1 -RunGui
~~~

The script uses a disposable Python 3.11 virtual environment under TEMP.
It exercises the WinForms and real-Ollama tests without mocks, and writes
a pytest JUnit report. Any failure, skip, or missing report fails acceptance.

## Verify a prerelease installer before manual installation

Download the setup EXE and its matching .sha256 sidecar from:
https://github.com/oakvx/piko/releases

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\acceptance\windows-local.ps1 -Installer 'C:\Path\To\The-Downloaded-Setup.exe'
~~~

The command checks the SHA256 against the adjacent sidecar; replace the
example path with the actual file location. Use -ChecksumFile if necessary.

The script does **not** automatically install, upgrade, uninstall, reboot,
modify user files or change the Windows registry.

## Manual gates on clean disposable Windows 10 and Windows 11 VMs

These must be witnessed independently on both target OS versions:

1. SHA-verified installation, launch and WebView2 installation/recovery.
2. Bundled Python sidecar starts and terminates on window close; Tauri IPC
   supplies a fresh local authorization token to the desktop frontend.
3. Actual local Ollama model discovery, selection, reasoning and vision.
4. Controlled WinForms form-filling, click, wait, error recovery and observed result.
5. Fresh per-app permissions, foreground-switch rejection, pause/resume.
6. Emergency cancellation while a user is physically holding a key or button.
7. Teach recording, review/corrections, draft Skill approval, execution,
   independently verified result, restart, reload and fresh-consent replay.
8. Upgrade from a prior preview, reboot, data persistence, silent uninstall.
9. Record source commit, Windows build, installer digest, model names/digests
   and outcomes, including failures and corrective retests.

The issue's full 27-step acceptance cannot be inferred from a smaller subset.
Record unperformed gates as NOT RUN rather than PASS.

## Evidence handling

Results are stored locally in
%TEMP%\piko-acceptance-YYYYMMDD-HHMMSS, with metadata.json and JUnit XML.
Review before sharing; failure tracebacks or diagnostic data may include
sensitive local information. Redact personally identifying information and
never publish raw screenshots or typed private content. Separate evidence into
Windows GUI, real Ollama and installer-specific Windows 10/11 categories.

Keep issue #4 open until the complete release gates have verified evidence.
