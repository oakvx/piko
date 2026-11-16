# Architecture decisions — Piko 0.1.0a0

1. **Modular monolith.** One local Python process owns the desktop input lock, permissions and state. The UI is a separate local-only client. This prevents duplicate input owners and avoids a premature microservice topology.
2. **Semantic actions first.** The planner receives redacted UI Automation elements and produces a strictly validated plan. Selector identities must exist in a fresh observation. Pixel coordinates are deliberately absent from the first milestone.
3. **No generic agent framework.** A typed finite-state orchestration loop and a minimal provider protocol give direct control over security checks, cancellations and verification.
4. **Model output is untrusted.** Ollama is used only to describe scenes and propose typed plans. The permission manager and executor are deterministic Python code; the model cannot grant itself permissions.
5. **Observable success only.** An action dispatch is never sufficient; the verifier checks a fresh UIA property after the action and fails closed on mismatch.
6. **Local-first storage.** Session state and sanitized events live in SQLite. Raw demonstration PNGs live in a dedicated local folder and can be explicitly deleted.
7. **Original user interface.** Piko uses a custom cockpit layout and custom SVG character rather than an imported agent UI template. Functional status comes only from the backend.

## Known gaps before accepting a real Windows release

- Windows hardware-in-loop tests; proof of `mss` window capture correctness under DPI scaling.
- OS-level cancellation and reliable release for future held-input operations.
- Input-event recorder restricted to an authorized foreground app, with secure-field redaction.
- Skill validation/versioning and review + test workflow prior to declaring generalization.
- Re-planning after interface changes and independent visual/OCR verification.
- Working signed or unsigned Windows installer and startup lifecycle management of the Python backend.
