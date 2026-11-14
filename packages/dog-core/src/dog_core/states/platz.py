from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: platz")
    machine.command_recognition.start(machine)


def exit(machine: PrenMachine) -> None:
    machine.command_recognition.stop(machine)
