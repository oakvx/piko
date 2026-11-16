# Piko

**Show me. I'll do it.**

Piko is an experimental, local-first computer-use agent for Windows 10/11 x64. Its control logic, permissions and local data model are purpose-built; it does **not** embed a generic agent framework or a prebuilt AI dashboard.

> **Development status:** `0.1.0a0`, an incomplete prototype, **not** a general-purpose autonomous desktop agent. The Python core is portable; Windows automation, Tauri packaging and Ollama model inference still require Windows-machine validation. Do not use it for sensitive, destructive or financial tasks.

## What works in the code today

- Explicit session state machine and SQLite session/event storage, with interrupted sessions marked failed after restart.
- User-scoped permission grants and safe, validated UI Automation actions.
- Local Ollama model discovery, structured JSON planning and optional screenshot interpretation.
- Observe → plan → user review → execute → verify control flow, with cancellable sessions.
- Opt-in 30-second screenshot demonstration recorder, **not** yet full learning from demonstration.
- Draft `SKILL.md` generation from reviewed plans. Drafts are never advertised as verified.
- Token-protected, loopback-only API, and the original Piko Workfield React/Tauri interface. The Windows installer pipeline exists in source, but has not yet executed on GitHub Actions or Windows hardware.

## Run on Windows

Install Python 3.11–3.13, a compatible Ollama build, and a local reasoning model with structured JSON output. The vision model is optional until a supported one is installed.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[windows,dev]"
ollama list
piko serve --model YOUR_INSTALLED_MODEL --vision-model YOUR_VISION_MODEL
```

In manual developer mode, the command prints a one-time token for the desktop UI. In an installed release, the desktop host launches the bundled backend automatically and supplies an ephemeral token through local IPC; no manual token entry is required. The API is loopback-only.

The Workfield desktop UI can be developed with `cd apps/desktop; npm install; npm run dev`. Run `npm run check` and `npm run build` to validate the TypeScript frontend. Build a Tauri executable with `npm run tauri build` after installing the Rust toolchain, Microsoft C++ build tools and WebView2. **The Windows installer is configured but has not yet been compiled or verified on real Windows hardware.**

**Build caveat:** the current authoring environment cannot resolve the npm registry, so a `package-lock.json` could not be generated and the React/Tauri frontend has **not** been compiled. CI temporarily uses `npm install`; once the lockfile is generated and committed, restore `npm ci` and dependency caching. No frontend build success is claimed. See [Workfield design](docs/architecture/WORKFIELD.md).

For a controlled Windows automation fixture, open a second PowerShell terminal and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File examples/testbench.ps1
```

Grant only the testbench executable for the task at hand, keep it foregrounded, review the returned plan, then explicitly execute. The testbench is not currently integrated into the CI GUI runner.

## Test locally

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q src tests
```

Running these tests on Linux proves contract, state, permission and persistence behavior **with test fakes only**. It does not validate real Windows input, screen capture or Ollama output.

## Security model

There is **no autonomous default**. No user action is dispatched without a session-scoped application permission and explicit plan approval. No cloud inference provider is configured. Screenshot capture is only performed on request. Credentials and password-field windows are blocked. See [Security constraints](docs/security/BOUNDARIES.md).

## Current limitations

- Visual capture uses a foreground-window `mss` fallback rather than Windows.Graphics.Capture. Occluded windows may be captured incorrectly.
- UIA semantics depend on accessibility metadata; generic OCR and coordinate-grounding are not implemented.
- Demonstration recording lacks keyboard/mouse input event capture, procedural induction and test-derived skill verification.
- Plans are generated once, not continually re-planned; verification requires matching UIA elements.
- Input actions run through Windows UIA and cannot guarantee immediate cancellation mid-OS call.
- No tested offline gaming adapter, continuous live screen streaming, or long-running autonomous execution.
- Workfield supports explicitly requested, permission-gated one-shot screenshot captures (not a background screen stream).
- Pause is requested at an action boundary; the next action is revalidated on resume. In-flight OS calls cannot be interrupted instantly.

See [Architecture](docs/architecture/DECISIONS.md) for design choices and [Windows preview releases](docs/development/PREVIEW_RELEASES.md) for CI, packaging and publishing instructions.

## Provenance

The orchestration, state-machine logic, Skill schema, user interface and mascot are authored specifically for Piko. Established components (Python, FastAPI, SQLite, Ollama API, Windows UI Automation, React and Tauri) are used as infrastructure, **not** as an existing agent implementation. No third-party mascot, agent prompt package or premade AI application theme is included.

## Windows previews

GitHub Actions is configured to build an NSIS Windows x64 installer with a bundled Python sidecar on every push and PR; successful `main` commits are tagged as separate **prereleases**. Each build attaches a SHA-256 checksum and an executable. This remains **unverified** until the intended GitHub repository exists and Windows CI completes. See [Preview releases](docs/development/PREVIEW_RELEASES.md). No cloud models are installed automatically.
