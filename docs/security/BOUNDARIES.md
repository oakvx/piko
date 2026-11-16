# Security boundary

Piko is not currently intended for unattended operation on sensitive accounts.

- The Python API binds to loopback, requires an ephemeral bearer token, and disallows remote Ollama endpoints by default.
- The user grants access per executable; grants are memory-only and optionally session-bound. Revocation is available at any time. An active session's next action will be denied after revocation.
- Plans are typed, selectors are checked against accessible controls, and dangerous hotkeys are disallowed.
- A reviewed plan is bound in process memory to one foreground HWND, PID and (when available) process creation timestamp. An instance switch to another window of the *same executable* invalidates input; the bridge separately rechecks this identity before every native dispatch. Restart never restores these grants.
- UIA interactions use semantic Invoke/Value patterns, not raw mouse clicks; Piko does not hold mouse buttons. Only Piko-injected keyboard keys are tracked and released, without sending key-up events for user-held keys.
- Native UIA operations are serialized. Emergency stop can release owned keys and block re-arming while a pending COM lookup is still running; after it returns, cancellation prevents any subsequent input from that worker. A native invocation already inside Windows COM cannot be forcibly rolled back or interrupted in-process.
- Sanitized action-phase audit events record successful verification and refused dispatches without storing usernames, text input, screenshots or selector strings.
- Password fields prevent both image capture and task actions. This is a defense-in-depth filter, not a complete detection mechanism for all secret-bearing applications.
- Screen images and typed text are omitted from session/event logs. Demonstration PNGs are stored locally and must be deleted by the user when no longer required.
- No Skill-supplied scripts are executed. Imported procedures have no independent authorization.
- Emergency stop sets cancellation flags, but synchronous UI Automation actions cannot be preempted while inside an OS call; this needs further hardening before advanced access modes.
- No remote model integration, hidden telemetry, protected-process bypass or anti-cheat bypass is present.

**Security caveat:** UIA values may still contain sensitive application data. They are sent to the *local* configured model during planning. Operate only in explicitly authorized, non-sensitive windows.
