# Security boundary

Piko is not currently intended for unattended operation on sensitive accounts.

- The Python API binds to loopback, requires an ephemeral bearer token, and disallows remote Ollama endpoints by default.
- The user grants access per executable; grants are memory-only and optionally session-bound. Revocation is available at any time. An active session's next action will be denied after revocation.
- Plans are typed, selectors are checked against accessible controls, and dangerous hotkeys are disallowed.
- Password fields prevent both image capture and task actions. This is a defense-in-depth filter, not a complete detection mechanism for all secret-bearing applications.
- Screen images and typed text are omitted from session/event logs. Demonstration PNGs are stored locally and must be deleted by the user when no longer required.
- No Skill-supplied scripts are executed. Imported procedures have no independent authorization.
- Emergency stop sets cancellation flags, but synchronous UI Automation actions cannot be preempted while inside an OS call; this needs further hardening before advanced access modes.
- No remote model integration, hidden telemetry, protected-process bypass or anti-cheat bypass is present.

**Security caveat:** UIA values may still contain sensitive application data. They are sent to the *local* configured model during planning. Operate only in explicitly authorized, non-sensitive windows.
