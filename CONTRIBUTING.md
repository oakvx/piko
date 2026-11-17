# Contributing

Use focused commits (`feat:`, `fix:`, `test:`, `docs:`). Preserve permission boundaries even when adding action primitives. New behavior requires executable tests and must document Windows-only or model-dependent checks separately. Prefer small typed interfaces over introducing third-party agent frameworks.

## Working on Piko

1. Open one issue or use an existing one when the change needs discussion.
2. Keep each commit focused on a real change, not on activity metrics. Explain the behavior in the commit message.
3. Add automated tests for code changes and run `python -m pytest -q` plus `python scripts/ci/check_docs.py`.
4. Run TypeScript checks for Workfield changes. Distinguish hosted Windows tests from Windows 10/11 hardware validation.
5. Open a pull request and complete the acceptance and permission-boundary checklist before merging to `main`.
6. Check Actions after merge: only a green, verified `main` build may produce a new installer prerelease.

Weekly read-only health checks are documented in [maintenance](docs/development/MAINTENANCE.md). GitHub Actions must never fabricate contributors or produce empty commits to maintain streaks.
