"""Independent authorization gate: never trust plans, screenshots or Skills."""
from datetime import datetime, timezone

from piko.contracts import AccessProfile, Action, ActionKind, Grant


class PermissionDenied(PermissionError):
    pass


SAFE_HOTKEYS = frozenset({("ctrl", "a"), ("ctrl", "c"), ("ctrl", "v"), ("ctrl", "w"), ("tab",), ("escape",)})


class PermissionManager:
    def __init__(self) -> None:
        self._grants: dict[str, Grant] = {}

    def grant(self, grant: Grant) -> None:
        self._grants[grant.executable] = grant

    def revoke(self, executable: str) -> None:
        self._grants.pop(executable.casefold(), None)

    def check_observe(self, executable: str, session_id: str) -> None:
        grant = self._grants.get(executable.casefold())
        if grant is None:
            raise PermissionDenied(f"No permission grant for {executable}")
        if grant.session_id is not None and grant.session_id != session_id:
            raise PermissionDenied("Grant is scoped to a different session")
        if grant.expires_at is not None and grant.expires_at <= datetime.now(timezone.utc):
            raise PermissionDenied("Permission grant expired")
    def check(self, executable: str, session_id: str, action: Action) -> None:
        self.check_observe(executable, session_id)
        grant = self._grants[executable.casefold()]
        if grant.profile == AccessProfile.OBSERVE:
            raise PermissionDenied("Observe profile cannot dispatch inputs")
        if action.kind == ActionKind.HOTKEY and tuple(k.casefold() for k in action.keys) not in SAFE_HOTKEYS:
            raise PermissionDenied("Hotkey not on safe allowlist")
        # Hard block shell commands and privileged execution, even under Full Access.
        if action.kind not in set(ActionKind):
            raise PermissionDenied("Unsupported action")
