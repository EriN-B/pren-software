from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine
  

class StateTemplate:
    """Example state only; replace with actual logic."""

    def __init__(self):
        self.attribute = None

    def enter(machine: PrenMachine) -> None:
        pass

    def doSometing(self) -> None:
        pass

    def exit(machine: PrenMachine) -> None:
        # Clean up resources owned only by this state here.
        pass
    