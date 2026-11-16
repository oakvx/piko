# Issue #2 acceptance evidence — Windows native input boundary

This document maps [security issue #2](https://github.com/oakvx/piko/issues/2)
to source code and independently exercised tests. **A green CI result is required
before declaring the issue resolved.** It does not imply Piko is safe for
unattended or sensitive workflows.

| Acceptance criterion | Implementation and verification |
| --- | --- |
| Consent bound to HWND/PID/executable | `Agent._approved_windows` holds the window handle, PID and process creation time from the exact approved observation; `Agent._observation` rejects a different instance even if the executable is identical. `WindowsDesktop._assert_active` revalidates foreground HWND/PID/executable/creation time before dispatch. |
| Deny changed/reused/ambiguous/inaccessible/password controls | Windows bridge fails closed on mismatched HWND or recycled PID, UIA target resolution requires exactly one matching non-password element, disabled and non-invokable controls are rejected, and password-field observations cannot authorize actions. |
| Track and release only agent-owned inputs | `OwnedKeyboard` rejects physically held user keys, records injected key-downs, and issues matching key-ups in `finally` and on emergency stop. Semantic UIA Invoke/Value actions do not inject or hold mouse-button down events. |
| Real Windows foreground-switch negative tests | `tests/windows/test_real_gui.py` checks foreign executable rejection. `tests/windows/test_security_boundary_e2e.py` exercises **two real WinForms processes with the same PowerShell executable** and proves a previously approved session cannot click either after switching to the other, and records the refusal. |
| Hung native call / cancellation | `tests/test_windows_input_boundaries.py` blocks a deterministic native UIA target lookup on a separate thread: emergency stop is immediate, cannot re-arm a new session or launch another action, and the original worker refuses to Invoke once the simulated blocked lookup returns. Separate tests cover blocked foreground checks and UIA property retrieval. Actual Windows COM invocations cannot be safely interrupted in-process; no additional input is dispatched by Piko after cancellation, but an already-entered COM call may complete its current operation. |
| Sanitized outcomes | `LocalMemory.write_event` allowlists action metadata; `Agent.run` records `action.verified` and `action.failed` with phase and exception class, never input text, model output, screenshots or selector values. The real same-executable Windows negative test verifies this ledger. |

## Reproduction

GitHub Actions executes both the real Windows GUI suite and cross-platform
negative fixtures before installer build. For a controlled interactive Windows
session with development dependencies installed:

```powershell
$env:PIKO_GUI_SMOKE = '1'
python -m pytest -q tests/windows/test_real_gui.py tests/windows/test_security_boundary_e2e.py
python -m pytest -q tests/test_windows_input_boundaries.py tests/test_agent.py tests/test_runtime_safety_regressions.py
```

A separate Windows clean-VM, Windows 10/11 user-input stress and production
lifecycle test campaign remains part of issue #4. Closing #2 only certifies
the specifically listed input authorization and cancellation contract; it
does **not** certify a hard timeout/kill for arbitrary Windows COM calls,
privilege isolation, anti-cheat interaction, or protected-process automation.
