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
- Pulls `qwen2.5:3b` for structured action planning and
  `qwen3-vl:2b-instruct` for image interpretation.
- Calls Piko's real `OllamaProvider` against the actual Ollama server. The
  model must produce a schema-valid plan that clicks the observed Save button;
  image inference must identify the visible Save control and status text.
- Launches a real controlled WinForms window, authorizes the foreground,
  lets the actual model plan a single click, requires a reviewed plan,
  executes it through the native Agent/UIA boundary, and independently checks
  the resulting `StatusLabel`. Planning alone cannot change the interface.
- Fails if either model is missing, Ollama is unavailable, inference is invalid,
  or any of the three tests fail. It does **not** treat skipped inference tests as PASS.
- Attaches a JUnit test report and sanitized runner/model metadata, even when
  a preceding step fails. An absent JUnit report is **not** successful inference.

The three real tests may take substantial time and download multiple gigabytes. It uses
GitHub-hosted **Windows Server**, not clean Windows 10/11 desktop machines.
Results must be classified **`real Ollama / hosted Windows`** and not
misreported as **`Windows 10`** or **`Windows 11`** acceptance.

## Structured plan compatibility (issue #35)

The real hosted Windows run on 19 November 2026
([run 44582336081](https://github.com/oakvx/piko/actions/runs/44582336081))
passed the three other model/Coach checks but failed when `qwen2.5:3b`
generated a UI action without the required discriminated `kind` or other
required fields (`missing`, `union_tag_not_found`). No action was dispatched.

The first Ollama generation attempt now uses a simpler **flat wire JSON
schema** that explicitly requires `kind` and `expected` but does not use
the union's JSON-Schema `oneOf`. This wire format is a *generation hint only*:
the resulting JSON is still parsed by the **original strict discriminated
`GeneratedPlan` schema**, revalidated as an executable `Plan`, checked
against freshly observed UIA control identifiers and governed by the normal
session review and permission gates. Missing selectors, absent kinds, extra
fields and invented UI targets still fail closed. At most one additional
JSON-only generation attempt is permitted, and raw model responses are not
logged or persisted.

This is a compatibility fix, **not a waiver of the live-model gate**. Close
issue #35 only if the pinned `qwen2.5:3b` real Windows acceptance run
demonstrates a valid reviewed plan and separately verified WinForms outcome.
A green offline transport-mock test is not sufficient. Hosted Windows Server
cannot certify clean Windows 10/11 desktop systems.

## Coach vision timing (issue #36)

The 17 November hosted run reported `analyzing-locally` after at least one
successfully interpreted frame. This was a test assertion race, **not evidence
of a permanently stalled Coach**: the next scheduled frame can already be
under analysis when the test inspects the current stage. Success now requires
a completed frame counter, non-empty observed advice and a sanitized
observation timestamp; the transient stage may be `watching` or
`analyzing-locally`.

For independent liveness protection, each local vision request is bounded
to 90 seconds (or the smaller remaining consent-session budget).
An expired request transitions to `temporarily-unavailable` with an explicit
`Local vision inference timed out` error; it does not persist screenshot
bytes or dispatch input. The status exposes `last_inference_ms` for the last
successful analysis, without retaining images, text or private prompts.

Portable regressions separately exercise a hanging vision coroutine and a
second frame in progress. The hosted real-Ollama run must still prove the
controlled WinForms screenshot can be interpreted on the runner. A failure
in the reasoning-model test (issue #35) is independent of Coach correctness.
Neither result certifies real games, fullscreen capture or clean Windows
10/11 release installations.

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
