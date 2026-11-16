# Issue #4 — real Ollama evidence, Windows-hosted runner

**This is a real integration test, not a stable-release certification.** The separate workflow
[Real Ollama inference (Windows)](../../.github/workflows/real-ollama.yml)
runs on `main` pushes that modify either the workflow or its real inference test;
it can also be started manually via GitHub Actions → **Run workflow**.
Unrelated commits do not repeatedly download gigabytes of models.

## What it verifies

- Downloads the official Windows Ollama `v0.40.11` CLI archive and verifies its
  pinned SHA-256 **before extraction/execution**.
- Starts a real local Ollama service at `127.0.0.1:11434`, with cloud inference disabled.
- Pulls `qwen2.5:1.5b` for structured action planning and
  `qwen3-vl:2b-instruct` for image interpretation.
- Calls Piko's real `OllamaProvider` against the actual Ollama server. The
  model must produce a schema-valid plan that clicks the observed Save button;
  image inference must identify the visible Save control and status text.
- Fails if either model is missing, Ollama is unavailable, inference is invalid,
  or either test fails. It does **not** treat skipped vision tests as PASS.
- Attaches a JUnit test report and sanitized runner/model metadata, even when
  a preceding step fails. An absent JUnit report is **not** successful inference.

The test may take substantial time and downloads multiple gigabytes. It uses
GitHub-hosted **Windows Server**, not clean Windows 10/11 desktop machines.
Results must be classified **`real Ollama / hosted Windows`** and not
misreported as **`Windows 10`** or **`Windows 11`** acceptance.

## Separate release blockers

The following still require independent, witnessed tests on clean Windows 10
(22H2 x64) and Windows 11 x64 test VMs:

1. Installer SHA verification, installation, WebView2 prerequisite behavior,
   launch, sidecar IPC and termination.
2. Upgrade from an earlier prerelease, reboot, persistence, and silent
   uninstall without user data loss.
3. Real foreground UIA with user-permission scope and observable UI outcome;
   verify rejection after switching to a foreign application.
4. Pause/resume and emergency cancellation while a user key/button is
   physically held, including native UIA callbacks that block.
5. Full 27-step controlled acceptance with **actual selected Ollama models**,
   demonstration recording, correction review, DRAFT Skill, user-approved
   execution, independent outcome, restart and fresh-permission replay.

Use `python -m pytest -q tests/windows/` on each workstation only when an
interactive session is available and `PIKO_GUI_SMOKE=1`; otherwise the
native tests skip. Check skipped counts. For actual local Ollama, explicitly
set `PIKO_REAL_OLLAMA=1`, `PIKO_OLLAMA_REASONING_MODEL` and
`PIKO_OLLAMA_VISION_MODEL`, then run
`python -m pytest -q -rs tests/real/test_ollama_inference.py`.

Record separately for each environment: Windows edition/build, timestamp,
source commit and installer SHA256, model names/digests, exact tests and results,
manual observations, failures and corrective retests. Redact screenshots,
window contents, user-entered text, OS account names and machine identifiers
before sharing evidence publicly. **No issue closure or stable release
claim is justified by a green hosted-runner result alone.**
