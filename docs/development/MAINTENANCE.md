# Sustainable maintenance and contribution activity

Piko is a Windows-first local computer-use agent in alpha. Prefer **small, verified
changes** over high-volume cosmetic commits. A commit is useful when it improves
behavior, safety, tests, documentation accuracy or release reproducibility.

## Weekly unattended checks

[Scheduled repository maintenance](../../.github/workflows/maintenance.yml)
runs every Wednesday at 15:37 UTC and can be started manually with
**Actions > Scheduled repository maintenance > Run workflow**.

It runs Python regression tests on hosted Linux and Windows, checks local
documentation links, verifies TypeScript and production npm dependencies, and
reproduces the source-locked CycloneDX SBOM.

The scheduled workflow uses `contents: read` only. It intentionally does **not**
commit files, create tags, publish a preview, install external agents on Windows
desktop sessions or change issue states. Failures must be investigated before
claiming a green maintenance result.

The normal [preview pipeline](../../.github/workflows/ci.yml) still runs on
real changes to `main` and pull requests; it remains the only route to a
new installer prerelease.

## Suggested recurring work

1. Review failed Actions runs and actual test results. Fix one reproducible cause.
2. Check new third-party advisories and update one locked dependency only when
   the upgrade has passed the relevant build and regression checks.
3. Review issues for reproducible defects. Add regression tests before fixes.
4. Improve one stale instruction or documented limitation against the running app.
5. Run a controlled Windows 10/11 acceptance test and report the exact OS build,
   model and result without attaching private desktop content.

## Contribution activity versus GitHub streaks

GitHub contribution credit is based on qualifying activity on calendar days, not
on a raw number of commits. Commits normally need an author email associated
with the account and inclusion on the repository's default branch (`main`).
A pull request branch alone is not enough until those commits are merged.
GitHub uses UTC for the profile contribution calendar.

**Scheduled workflow runs and commits authored as `github-actions[bot]` are not
reliable contributions for an individual developer's streak.** Never spoof an
author identity or make empty commits solely to fill the calendar. If you want
a daily streak, make a real contribution yourself, verify it appears on the
GitHub profile, and review the commit's author email if it is missing.

References:
- [GitHub contribution criteria](https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference)
- [Troubleshooting missing contributions](https://docs.github.com/en/account-and-profile/how-tos/contribution-settings/troubleshooting-missing-contributions)
- [Scheduled workflow limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
