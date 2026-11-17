## Purpose

Describe the user-visible change, risk and affected subsystem.

## Verification

- [ ] Run portable tests: `python -m pytest -q`.
- [ ] Check local Markdown links: `python scripts/ci/check_docs.py`.
- [ ] For frontend edits, run `npm ci && npm run check && npm run build` in `apps/desktop`.
- [ ] For Windows-specific edits, record the actual Windows 10/11 test environment or mark it **not tested**.
- [ ] For Ollama changes, distinguish mocked tests from actual local inference.
- [ ] For packaging changes, inspect the NSIS installation / launch / uninstall workflow result.

## Safety / release impact

- [ ] No implicit app permissions, background screen capture or silent inputs.
- [ ] No API keys, personal screenshots, recordings or sensitive prompts in the diff.
- [ ] The proposal still requires review before execution.
- [ ] Update known limitations and documentation when behavior changes.

## Known gaps

State what remains unverified. A passing hosted Windows Server CI run does not establish compatibility with clean Windows 10/11 machines.
