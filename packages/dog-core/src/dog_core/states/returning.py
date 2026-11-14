from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: returning")
    machine.returned()


def exit(machine: PrenMachine) -> None:
    pass
