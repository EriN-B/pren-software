from __future__ import annotations
from typing import TYPE_CHECKING
from dog_core.states import perform_auf

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: auf_before_such")
    perform_auf.stand_up(machine)
    machine.go_to_searching()


def exit(machine: PrenMachine) -> None:
    perform_auf.exit(machine)
