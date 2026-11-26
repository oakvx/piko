# Changelog

## Unreleased — Workfield UI consistency and redesign

- Translated the Italian window/app picker and scattered Italian strings
  to English so the whole Workfield interface uses one consistent language.
- Dropped misleading sequence numbering (01-05) from the lens nav, since
  the five lenses are independent modes, not a process.
- Replaced the pastel-light/neon-pink dual-theme stylesheet with a single
  warm, dark editorial theme (brass/violet accents, self-hosted IBM Plex
  Sans/Mono, flat hairline panels) and recolored the Piko mascot to match.

**Verification:** `pytest` (228 passed, 10 skipped) and the frontend
`tsc --noEmit` / `vite build` all pass in the authoring Linux environment.
Not verified: real Windows desktop rendering/appearance of the new theme.

## 0.1.0a0 — unreleased

- Initial local session/orchestration core, permissions, Ollama integration, UIA bridge, verification, demo capture, draft Skills, API and testbench.
- Explicit disclaimer: Windows desktop and Ollama end-to-end acceptance criteria are not yet verified.

## Unreleased — Windows packaging and preview automation

- Bundle Python desktop agent into a Tauri NSIS Windows installer using a PyInstaller sidecar.
- Generate a local control token and loopback port automatically in packaged Windows builds.
- Add in-app Ollama model-role selection with installed-model and vision capability checks.
- Compile each pushed commit/PR on Windows; publish a prerelease and checksums only for successful `main` commits.
- Add CI pipeline tests and release documentation.

**Verification:** Python tests pass in the authoring Linux environment; Windows packaging, GitHub Actions and real Ollama have not been executed here.
