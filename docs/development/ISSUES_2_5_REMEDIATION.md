# Issue remediation — 16 November 2026

This document tracks **merged remediation from PR #6 and follow-up release hardening**, not a declaration that all product acceptance gates have passed. CI status is authoritative at [GitHub Actions](https://github.com/oakvx/piko/actions).

## Issue #2 — Windows input trust boundary

- Screenshots require existing scoped observation authorization before capture begins.
- Each Windows observation includes HWND/PID; native UIA dispatch rejects mismatched foreground window, process or executable.
- Global/unbound input calls on `WindowsDesktop` fail closed. Semantic UIA invocation is used rather than arbitrary pointer clicks.
- Owned keyboard chords reject keys already physically held by the user; only keys injected by Piko are released at cancellation and on failure.
- Negative tests cover foreign HWND/PID, unbound calls, held user keys and emergency cancellation.
- A follow-up input boundary also binds observed controls to Windows process creation time to reject PID reuse (same HWND/PID/executable but different process lifetime). Observation checks the same pinned window both after UIA enumeration and before/after screenshot capture to avoid returning pixels from a switched foreground application; regression fixtures simulate a switch during collection.
- Follow-up hardening separates serial chord ownership from its pressed-key ledger: an emergency stop immediately releases agent-owned keys even while a foreground/UIA validation callback is blocked. A concurrent-thread negative test asserts no new injection after that blocked callback eventually returns, and new sessions refuse while a previous chord is still running.
- A real Windows CI testbench exercises WinForms and an unauthorized foreground process switch.
- Native dispatch now has a cancellation signal that survives a hung UIA target lookup; after it returns, a stopped session cannot invoke the resolved control. The local event ledger records sanitized `action.verified` success and `action.failed` with phase/exception type, never typed values.
- **Still limited:** Native UIA COM operations may block and cannot guarantee an immediate hard kill. Windows security boundary requires stronger token-privilege isolation and long-running stress/hardware testing.

## Issue #3 — Teach and Skill persistence

- Recording supports opt-in, foreground HWND/PID-scoped mouse clicks, scrolls and selected navigation key names without typed-character capture; paired with timestamped screenshot/UIA timeline.
- Follow-up recording isolation binds the entire demonstration to the approved HWND, PID and process creation time, not just the executable name. The Windows capture bridge refuses foreign foreground identities **before** grabbing pixels; unexpected window changes/password controls end capture. A scoped grant is rechecked on each frame and each allowed input event; revocation/expiry terminates the recording.
- Every captured frame has a stable `frame_index`, `frame_file` and UTC `captured_at` timestamp for temporally linking image, UIA metadata and permitted OS events. Stop/skip reasons are also timestamped; raw typed characters, UIA labels and values remain excluded from the machine-readable event stream.
- A native scoped-capture denial ends the entire demonstration rather than silently retrying if the user later refocuses the former window. The API returns a sanitized stop reason, and Workfield automatically retrieves finished recordings when consent is revoked, the foreground changes, or the duration expires; each new recording requires fresh visible consent.
- Analysis emits only tentative element matches with uncertainties and requires user correction; does not claim automatic procedural intelligence.
- A guided correction editor exposes observed, redacted UIA targets and lets the user revise objectives, explanations, action types, selectors, typed-text parameter names and independently observable outcomes. Advanced strict JSON remains available, but the local client never automatically asserts a user has reviewed the result: a separate explicit confirmation is mandatory before saving.
- Corrected draft outcome selectors must also appear in the consented demonstration, preventing ungrounded verification targets. Imported ZIPs now reject duplicate metadata entries and typed-plan executable extensions/instructions.
- Corrected typed plans can become `DRAFT` Skills after explicit consent. Imported ZIPs cannot contain scripts or arbitrary additional entries.
- Skills must be separately reviewed, granted and approved at execution time, and executed outcomes are logged without automatically setting verification status.
- Runtime pauses do not count as failed Skill executions: attribution survives pause/resume until a terminal state. Per-run history now retains a sanitized verified-action count and wall-clock duration (including pause time), without storing user-entered text or captured pixels.
- Draft versions are archived with rollback and export/import. Verified revisions cannot be overwritten.
- A CI-gated interactive Windows WinForms test performs a real native mouse click during opt-in Teach recording, confirms a structural click event and tentative UIA step, requires explicitly corrected parameterized input/outcome, then executes the stored draft through the authenticated Agent API with fresh consent and independently observes the result. This controlled test-driver demonstration does not claim automatic free-form inference or human interaction.
- **Still limited:** free-form goal inference, generalized semantics and real cross-session Skill performance benchmarks need additional work. Raw pixels may include sensitive information even when timeline metadata is redacted.

## Issue #5 — Dependency reproducibility and scanning

- npm, Cargo and the Windows Python backend have generated lockfiles, consumed by `npm ci`, locked Cargo metadata and the bundled sidecar packaging.
- Windows installer version stamping updates only the local package versions in package manifests and locks.
- Production npm audit, RustSec audit and pinned-Windows Python pip-audit are mandatory CI checks. Fix actual dependency vulnerabilities; never suppress audit failures for a release.
- GitHub's dependency-review-action could not run because its repository dependency graph is unavailable, so independent scans are used instead.
- A dependency inventory SBOM (CycloneDX 1.6) is generated deterministically from the checked-in npm, Cargo and Windows Python locks for each source SHA. Main preview publication is now gated on SBOM reproduction; the JSON inventory is published alongside installer/checksum artifacts. It includes lock metadata and npm-reported licenses when available, but is **not** a comprehensive license compliance decision.
- The previous main-merge run 43938456193 failed only when the RustSec action attempted to write a GitHub Check with a read-only workflow token, despite reporting zero RustSec vulnerabilities. The scanner now runs directly against the locked Cargo dependency graph with a failing exit code on discovered vulnerabilities; the Check API permission is deliberately not granted.
- All official GitHub Actions workflow references are pinned to 40-character commit SHAs resolved from upstream v4/v5 tags, with a regression test rejecting moving tags.
- **Still limited:** Python lock pins versions without wheel hash verification; platform-specific SBOM analysis and full license compliance review remain open. RustSec advisory warnings about unmaintained or unsound packages are reported even when no vulnerabilities cause audit failure.

## Issue #4 — End-to-end Windows and Ollama acceptance

- Real Windows WinForms tests now execute through the CI runner on an interactive desktop when supported.
- A second real WinForms test exercises the full Agent session state machine with a deterministic (non-Ollama) planner, fresh grant and plan review, native UIA input and independently observed outcomes. It then persists a parameterized draft Skill, recreates the Agent and permission manager, refuses an ungranted replay, applies a new user value with fresh consent and verifies the final UI after execution. Passing this test is native GUI/Skill evidence, not proof of actual model inference.
- An opt-in `tests/real/test_ollama_inference.py` suite exercises actual local Ollama tags, structured reasoning and vision inference; it requires `PIKO_REAL_OLLAMA=1`, `PIKO_OLLAMA_REASONING_MODEL` and, for vision, `PIKO_OLLAMA_VISION_MODEL`. It does not download models or report simulated inference as successful.
- **Not performed:** clean Windows 10/11 installer installation, Windows reboot/upgrade/uninstall, real reasoning and vision inference using installed Ollama models, and the complete 27-step end-to-end acceptance sequence.
- Do not close #4 or declare stable release until the full controlled machine evidence is collected.

## Release and review gate

Before merging this branch require green Python 3.11/3.13 across Windows and Linux, frontend TypeScript/npm, all dependency scans, real WinForms smoke, bundled NSIS with SHA-256. Green CI alone does not prove stable product suitability.
