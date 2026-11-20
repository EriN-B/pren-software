from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_core.machine import PrenMachine


def enter(machine: PrenMachine) -> None:
    machine.shared.logger.info("Currently in state: perform_brav")
    machine.shared.uart.brav()
    machine.go_to_standing_idle()


def exit(machine: PrenMachine) -> None:
    pass
