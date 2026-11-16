# Windows previews — one installer per successful main commit

> **Status:** Pipeline source authored and Python checks passed. No installer has yet been compiled on a Windows runner; the intended GitHub repository `oakvx/Pico` has not been created.

## Publishing contract

The [CI workflow](../../.github/workflows/ci.yml) runs on pushes to any branch, pull requests, and manual dispatches.

1. Run tests with Python 3.11 and 3.13 on Windows and Linux.
2. Compile the React frontend and validate TypeScript.
3. Build the Python agent as a Windows x64 executable using PyInstaller.
4. Include `piko-agent-x86_64-pc-windows-msvc.exe` in the NSIS installer via Tauri `externalBin`.
5. Compile the desktop wrapper, verify that a real setup EXE exists, and generate SHA-256 checksums.
6. Upload a CI artifact for any branch or PR build that succeeds.
7. For successful `main` pushes only, publish a GitHub **prerelease** tagged `preview-<12-character-commit-SHA>` targeting that exact commit.

A rerun updates assets on the same tag rather than duplicating a release. `contents: write` is scoped to the release job; other jobs are read-only. A failed build produces **no prerelease**. Workflow dispatch on `main` may republish the existing commit's assets.

**Scope:** Every commit pushed to `main` produces its own preview *if all verification and packaging jobs pass*. A feature-branch push gets an installer as a workflow artifact, but not an unreviewed public release. Merge the PR to publish the resulting main commit.

The installer version is stamped as `0.1.<workflow-run-number>` in CI only. No generated version commit is added to the source branch. A version number above 65535 currently requires a revised version scheme.

## Installed runtime

The installer contains the React UI, Rust host and PyInstaller Python backend. It does **not** silently install Ollama or download heavyweight AI models. On launch, a packaged Tauri app starts the sidecar on a randomly chosen local loopback port and sends an ephemeral token via the child process environment. Only the local frontend obtains the token through a Tauri IPC command. A normal app-window close terminates the sidecar.

Start Ollama if it is not running; open **System** to choose an installed reasoning model and, optionally, a model supporting vision. Models are not assumed to exist. In development, `piko serve` can still be started manually.

## First publication

The connected GitHub toolset currently cannot create repositories. Once `Pico` is created under `oakvx` with an empty default `main` branch (do not auto-create a README), publish the existing history:

```bash
git remote add origin https://github.com/oakvx/Pico.git
git push -u origin main
```

To restore from the delivered bundle: `git clone piko-local-history.bundle pico`. The person who owns a repository is not automatically the author of commits. Do not rewrite history to falsify author information; leave commits attributed to their actual contributors or automation.

Make sure Actions are enabled and the repository permits the preview release job's scoped `contents: write` permission.

## Before recommending distribution

- Build and install on Windows 10 and 11 x64; test uninstall, upgrade and app relaunch.
- Test the bundled PyInstaller process, Tauri IPC, local API, and close cleanup on Windows.
- Test real Ollama inference with installed local models and desktop UI automation.
- Add executable code signing to minimize SmartScreen warnings.
- Generate and commit a `package-lock.json` on a network-enabled machine and replace `npm install` with `npm ci` in CI.
- Audit packages and verify non-GPU and multi-monitor behavior.

No hardware-dependent result is claimed from the authoring machine.
