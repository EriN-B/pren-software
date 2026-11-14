from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: perform_auf")
    stand_up(machine)
    machine.go_to_standing_idle()


def stand_up(machine: PrenMachine) -> None:
    machine.shared.uart.auf()


def exit(machine: PrenMachine) -> None:
    pass
