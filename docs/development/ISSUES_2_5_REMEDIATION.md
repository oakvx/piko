# Issue remediation — 16 November 2026

This document describes **source changes proposed in PR #6**, not a declaration that all product acceptance gates have passed. CI status is authoritative at [GitHub Actions](https://github.com/oakvx/piko/actions).

## Issue #2 — Windows input trust boundary

- Screenshots require existing scoped observation authorization before capture begins.
- Each Windows observation includes HWND/PID; native UIA dispatch rejects mismatched foreground window, process or executable.
- Global/unbound input calls on `WindowsDesktop` fail closed. Semantic UIA invocation is used rather than arbitrary pointer clicks.
- Owned keyboard chords reject keys already physically held by the user; only keys injected by Piko are released at cancellation and on failure.
- Negative tests cover foreign HWND/PID, unbound calls, held user keys and emergency cancellation.
- A follow-up input boundary also binds observed controls to Windows process creation time to reject PID reuse (same HWND/PID/executable but different process lifetime). Observation checks the same pinned window both after UIA enumeration and before/after screenshot capture to avoid returning pixels from a switched foreground application; regression fixtures simulate a switch during collection.
- A real Windows CI testbench exercises WinForms and an unauthorized foreground process switch.
- **Still limited:** Native UIA COM operations may block and cannot guarantee an immediate hard kill. Windows security boundary requires stronger token-privilege isolation and long-running stress/hardware testing.

## Issue #3 — Teach and Skill persistence

- Recording supports opt-in, foreground HWND/PID-scoped mouse clicks, scrolls and selected navigation key names without typed-character capture; paired with timestamped screenshot/UIA timeline.
- Analysis emits only tentative element matches with uncertainties and requires user correction; does not claim automatic procedural intelligence.
- Corrected typed plans can become `DRAFT` Skills after explicit consent. Imported ZIPs cannot contain scripts or arbitrary additional entries.
- Skills must be separately reviewed, granted and approved at execution time, and executed outcomes are logged without automatically setting verification status.
- Draft versions are archived with rollback and export/import. Verified revisions cannot be overwritten.
- **Still limited:** free-form goal inference, a visual parameter editor, generalized semantics and real cross-session Skill performance benchmarks need additional work. Raw pixels may include sensitive information even when timeline metadata is redacted.

## Issue #5 — Dependency reproducibility and scanning

- npm, Cargo and the Windows Python backend have generated lockfiles, consumed by `npm ci`, locked Cargo metadata and the bundled sidecar packaging.
- Windows installer version stamping updates only the local package versions in package manifests and locks.
- Production npm audit, RustSec audit and pinned-Windows Python pip-audit are mandatory CI checks. Fix actual dependency vulnerabilities; never suppress audit failures for a release.
- GitHub's dependency-review-action could not run because its repository dependency graph is unavailable, so independent scans are used instead.
- **Still limited:** action workflow references are not all SHA-pinned, Python lock currently pins versions without wheel hash verification, and platform-specific SBOM/license compliance needs additional independent review.

## Issue #4 — End-to-end Windows and Ollama acceptance

- Real Windows WinForms tests now execute through the CI runner on an interactive desktop when supported.
- An opt-in `tests/real/test_ollama_inference.py` suite exercises actual local Ollama tags, structured reasoning and vision inference; it requires `PIKO_REAL_OLLAMA=1`, `PIKO_OLLAMA_REASONING_MODEL` and, for vision, `PIKO_OLLAMA_VISION_MODEL`. It does not download models or report simulated inference as successful.
- **Not performed:** clean Windows 10/11 installer installation, Windows reboot/upgrade/uninstall, real reasoning and vision inference using installed Ollama models, and the complete 27-step end-to-end acceptance sequence.
- Do not close #4 or declare stable release until the full controlled machine evidence is collected.

## Release and review gate

Before merging this branch require green Python 3.11/3.13 across Windows and Linux, frontend TypeScript/npm, all dependency scans, real WinForms smoke, bundled NSIS with SHA-256. Green CI alone does not prove stable product suitability.
