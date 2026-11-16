"""Platform protocol; Windows implementation lives behind a lazy import."""
from typing import Protocol

from piko.contracts import Action, Observation


class Desktop(Protocol):
    def observe(self, include_image: bool = False) -> Observation: ...

    def execute(self, action: Action) -> None: ...

    def emergency_release(self) -> None: ...
