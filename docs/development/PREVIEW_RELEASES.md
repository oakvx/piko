# Windows previews — one installer per successful main commit

> **Status:** The repository `oakvx/piko` exists and GitHub Actions is active. Verify the latest workflow and Releases before claiming an installer exists. Successful compilation is not a clean Windows 10/11 installation test. An automated install/launch/uninstall test on the hosted Windows runner is additional evidence, not a substitute for both target OS clean-VM tests.

## Publishing contract

The [CI workflow](../../.github/workflows/ci.yml) runs on pushes to `main`, pull requests, and manual dispatches.

1. Run tests with Python 3.11 and 3.13 on Windows and Linux.
2. Compile the React frontend and validate TypeScript.
3. Build the Python agent as a Windows x64 executable using PyInstaller.
4. Include `piko-agent-x86_64-pc-windows-msvc.exe` in the NSIS installer via Tauri `externalBin`.
5. Compile the desktop wrapper, verify that a real setup EXE exists, and generate SHA-256 checksums.
6. Upload a CI artifact for any branch or PR build that succeeds.
7. On a GitHub-hosted Windows runner, download and checksum the produced installer, install NSIS silently for the runner's user, confirm the installed GUI executable starts its bundled Python sidecar, close the GUI, verify sidecar cleanup and uninstall. A failing lifecycle check blocks release publication.
8. For successful `main` pushes only, publish a GitHub **prerelease** tagged `preview-<12-character-commit-SHA>` targeting that exact commit.

A rerun updates assets on the same tag rather than duplicating a release. `contents: write` is scoped to the release job; other jobs are read-only. A failed build produces **no prerelease**. Workflow dispatch on `main` may republish the existing commit's assets.

**Scope:** Every commit pushed to `main` produces its own preview *if all verification and packaging jobs pass*. Pull requests can produce installer workflow artifacts after quality gates pass, but never publish a public prerelease. Merge the PR to publish the resulting main commit.

The installer version is stamped as `0.1.<workflow-run-number>` in CI only. No generated version commit is added to the source branch. A version number above 65535 currently requires a revised version scheme.

## Installed runtime

The installer contains the React UI, Rust host and PyInstaller Python backend. It does **not** silently install Ollama or download heavyweight AI models. On launch, a packaged Tauri app starts the sidecar on a randomly chosen local loopback port and sends an ephemeral token via the child process environment. Only the local frontend obtains the token through a Tauri IPC command. A normal app-window close terminates the sidecar.

Start Ollama if it is not running; open **System** to choose an installed reasoning model and, optionally, a model supporting vision. Models are not assumed to exist. In development, `piko serve` can still be started manually.

## Current repository and quality gates

The existing repository is [oakvx/piko](https://github.com/oakvx/piko) on `main`. Commits should be reviewed through a PR, and only validated merges on `main` trigger prerelease publication. Native input, application switching, real Ollama output, screenshot authorization and clean-install behavior still require controlled hands-on Windows verification.

npm, Cargo and Windows Python packaging now consume checked-in dependency locks. GitHub Actions use pinned upstream commit references. Dependency audits are required in the CI release gate; a successful audit does not replace the clean-machine hardware validation required before a stable release.

## Before recommending distribution

- Build and install on Windows 10 and 11 x64; test uninstall, upgrade and app relaunch.
- Test the bundled PyInstaller process, Tauri IPC, local API, and close cleanup on Windows.
- Test real Ollama inference with installed local models and desktop UI automation.
- Add executable code signing to minimize SmartScreen warnings.
- Keep npm, Cargo and Python dependency locks current through reviewed updates and CI security scans.
- Audit packages and verify non-GPU and multi-monitor behavior.

No hardware-dependent result is claimed from the authoring machine.
