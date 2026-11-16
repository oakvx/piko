<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:ff5c8a,100:ffb347&height=240&section=header&text=piko&fontSize=96&fontColor=ffffff&fontAlignY=38&desc=Show%20me.%20I'll%20do%20it.&descSize=24&descAlignY=60&animation=fadeIn" alt="Piko. Show me. I'll do it." width="100%">
</p>

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=20&pause=1000&color=FF5C8A&center=true&vCenter=true&width=640&height=40&lines=Observe.;Plan.;You+approve.;Execute.;Verify." alt="Observe. Plan. You approve. Execute. Verify.">
</p>

<p align="center">
  <a href="https://github.com/oakvx/piko/actions"><img alt="CI" src="https://github.com/oakvx/piko/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/oakvx/piko/releases"><img alt="Latest preview" src="https://img.shields.io/github/v/release/oakvx/piko?include_prereleases&label=preview&color=ff5c8a&style=flat-square"></a>
  <img alt="Status" src="https://img.shields.io/badge/status-alpha-ffb347?style=flat-square">
  <img alt="Platform" src="https://img.shields.io/badge/Windows-10%20%7C%2011%20x64-0078D4?logo=windows&logoColor=white&style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%E2%80%933.13-3776AB?logo=python&logoColor=white&style=flat-square">
  <img alt="Local first" src="https://img.shields.io/badge/inference-local%20only-2ea44f?style=flat-square">
  <img alt="Ollama" src="https://img.shields.io/badge/runs%20on-Ollama-000000?style=flat-square">
</p>

<h3 align="center">An agent that uses your PC like you do, and asks before it touches anything.</h3>

<!-- Uncomment once you have recorded it (ScreenToGif, 10-15s on the testbench), and upload it via an issue or put it in docs/:
<p align="center">
  <img src="docs/demo.gif" alt="Piko observing a window, proposing a plan and executing it after approval" width="860">
</p>
-->

Piko looks at the app in front of it, writes a plan with a local Ollama model, waits for you to read it, and only then clicks and types. No cloud, no background screen stream, no action without your approval.

> [!WARNING]
> **`0.1.0a0`, early prototype.** The Python core is tested on Linux with fakes. Windows automation, the Tauri app and real Ollama output still need validation on a real Windows machine. Don't point it at anything sensitive, destructive or financial.

## How it works

```mermaid
%%{init: {'theme':'dark','themeVariables':{'primaryColor':'#10141e','primaryBorderColor':'#ff5c8a','primaryTextColor':'#f5f6fa','lineColor':'#ffb347','fontFamily':'monospace'}}}%%
flowchart LR
    A["01 Observe<br/><sub>UI Automation</sub>"] --> B["02 Plan<br/><sub>local model, JSON</sub>"]
    B --> C{"03 Review<br/><sub>you approve</sub>"}
    C -- approve --> D["04 Execute<br/><sub>granted apps only</sub>"]
    C -- reject --> X(["Stop"])
    D --> E["05 Verify<br/><sub>UIA elements match</sub>"]
    E -- mismatch --> F(["Fail"])
    style C stroke:#ffb347,stroke-width:3px
```

| Step | What happens |
|---|---|
| **Observe** | Reads the foreground window through Windows UI Automation. Screenshots only when you ask. |
| **Plan** | The local model returns a structured JSON plan. |
| **Review** | You read it. Nothing runs until you approve. |
| **Execute** | Actions run only in apps you granted for this session. |
| **Verify** | Piko checks the expected UI elements are there afterwards. |

Cancel any time. Pause takes effect at the next action boundary.

## Quick start

Windows 10/11 x64, Python 3.11–3.13, Ollama, and a local model that can produce structured JSON. A vision model is optional.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[windows,dev]"
ollama list
piko serve --model YOUR_INSTALLED_MODEL --vision-model YOUR_VISION_MODEL
```

From source, `piko serve` prints a one-time token to paste into the UI. With an installed release the desktop app starts the backend itself and hands over the token through local IPC.

Or grab a build from [Releases](https://github.com/oakvx/piko/releases). Read [Windows installer](#windows-installer) first.

<details>
<summary><b>Desktop UI (Workfield) from source</b></summary>

```sh
cd apps/desktop
npm install
npm run dev
```

`npm run check` and `npm run build` validate the frontend. `npm run tauri build` also needs Rust, the Microsoft C++ build tools and WebView2. See [Workfield design](docs/architecture/WORKFIELD.md).

There is no `package-lock.json` yet, so JS installs aren't reproducible and CI uses `npm install`. Next step: commit a lockfile and move to `npm ci`.

</details>

<details>
<summary><b>Try it on a safe target</b></summary>

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File examples/testbench.ps1
```

Run it in a second terminal, grant Piko access to the testbench only, keep it in the foreground, read the plan, approve. The testbench isn't in the CI GUI runner yet.

</details>

## What's in the repo

- Session state machine on SQLite. Sessions interrupted by a restart are marked failed.
- Per-session, per-app permissions and validated UI Automation actions.
- Ollama model discovery, JSON planning, optional screenshot interpretation.
- Opt-in 30-second screenshot recorder for demonstrations.
- Draft `SKILL.md` files from reviewed plans, always labeled as drafts.
- Loopback-only, token-protected API.
- Workfield, the React/Tauri interface.

## Safety

| Rule | |
|---|---|
| No autonomous default | Every run needs an app permission for the session and explicit plan approval. |
| Local inference only | No cloud provider is configured. |
| Screenshots on request | One at a time. No background stream. |
| Credentials blocked | Password-field and credential windows are refused. |
| Loopback API | Not reachable from the network. |

Details: [Security constraints](docs/security/BOUNDARIES.md).

## Known limitations

- Capture uses `mss` on the foreground window, not Windows.Graphics.Capture. A partly covered window can be captured wrong.
- Depends on the accessibility metadata apps expose. No general OCR, no coordinate grounding.
- The demo recorder saves screenshots only. No keyboard or mouse capture, and no path from demonstration to a verified skill yet.
- Plans are made once, not revised mid-run. Verification needs matching UIA elements.
- Cancel and pause can't interrupt an OS call already in flight. A resumed session re-validates the next action.
- No offline gaming adapter, no live screen streaming, no long autonomous runs.

## Tests

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q src tests
```

These use fakes. They cover contracts, state, permissions and persistence, and say nothing about real Windows input, capture or Ollama output.

## Windows installer

Every push and PR builds an NSIS x64 installer with the Python backend bundled. Green builds on `main` are published as prereleases with a SHA-256 checksum.

A green build means it compiled, nothing more. Installing, uninstalling and running it on a clean Windows machine hasn't been signed off. Check [Actions](https://github.com/oakvx/piko/actions) and [Releases](https://github.com/oakvx/piko/releases) for what exists, and [Preview releases](docs/development/PREVIEW_RELEASES.md) for how the pipeline works.

## Credits

Orchestration, state machine, Skill schema, UI and mascot were written for Piko. It builds on Python, FastAPI, SQLite, the Ollama API, Windows UI Automation, React and Tauri. No third-party agent framework, prompt pack, mascot or UI template is included.

Design notes: [Architecture](docs/architecture/DECISIONS.md).

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:ffb347,100:ff5c8a&height=100&section=footer" width="100%" alt="">
</p>
