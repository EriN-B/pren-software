from statemachine import Event, State, StateMachine

from dog_core.command_recognition import CommandRecognition
from dog_core.shared import SharedContext
from dog_core.states import (
    auf_before_brav,
    auf_before_hier,
    auf_before_such,
    found,
    perform_auf,
    perform_brav,
    perform_hier,
    platz,
    returning,
    searching,
    sitz,
    standing_idle,
    startup,
)


class PrenMachine(StateMachine):
    allow_event_without_transition = True

    startup = State(initial=True)
    standing_idle = State()
    searching = State()
    found = State()
    returning = State()
    perform_hier = State()
    platz = State()
    perform_auf = State()
    sitz = State()
    perform_brav = State()
    auf_before_such = State()
    auf_before_brav = State()
    auf_before_hier = State()

    such = (
        standing_idle.to(searching)
        | sitz.to(auf_before_such)
        | platz.to(auf_before_such)
    )
    signal = searching.to(found)
    return_back = found.to(returning)
    returned = returning.to(standing_idle)

    hier = (
        standing_idle.to(perform_hier)
        | sitz.to(auf_before_hier)
        | platz.to(auf_before_hier)
    )
    command_sitz = Event(
        standing_idle.to(sitz) | platz.to(sitz), id="sitz", name="Sitz"
    )
    command_platz = Event(
        standing_idle.to(platz) | sitz.to(platz), id="platz", name="Platz"
    )
    auf = sitz.to(perform_auf) | platz.to(perform_auf)
    brav = (
        standing_idle.to(perform_brav)
        | sitz.to(auf_before_brav)
        | platz.to(auf_before_brav)
    )

    go_to_standing_idle = (
        startup.to(standing_idle)
        | perform_hier.to(standing_idle)
        | perform_auf.to(standing_idle)
        | perform_brav.to(standing_idle)
    )
    go_to_searching = auf_before_such.to(searching)
    go_to_perform_brav = auf_before_brav.to(perform_brav)
    go_to_perform_hier = auf_before_hier.to(perform_hier)

    def __init__(self):
        self.shared = SharedContext()
        self.command_recognition = CommandRecognition()
        super().__init__()

    def on_enter_startup(self):
        startup.enter(self)

    def on_exit_startup(self):
        startup.exit(self)

    def on_enter_standing_idle(self):
        standing_idle.enter(self)

    def on_exit_standing_idle(self):
        standing_idle.exit(self)

    def on_enter_searching(self):
        searching.enter(self)

    def on_exit_searching(self):
        searching.exit(self)

    def on_enter_found(self):
        found.enter(self)

    def on_exit_found(self):
        found.exit(self)

    def on_enter_returning(self):
        returning.enter(self)

    def on_exit_returning(self):
        returning.exit(self)

    def on_enter_perform_hier(self):
        perform_hier.enter(self)

    def on_exit_perform_hier(self):
        perform_hier.exit(self)

    def on_enter_sitz(self):
        sitz.enter(self)

    def on_exit_sitz(self):
        sitz.exit(self)

    def on_enter_platz(self):
        platz.enter(self)

    def on_exit_platz(self):
        platz.exit(self)

    def on_enter_perform_auf(self):
        perform_auf.enter(self)

    def on_exit_perform_auf(self):
        perform_auf.exit(self)

    def on_enter_auf_before_such(self):
        auf_before_such.enter(self)

    def on_exit_auf_before_such(self):
        auf_before_such.exit(self)

    def on_enter_auf_before_brav(self):
        auf_before_brav.enter(self)

    def on_exit_auf_before_brav(self):
        auf_before_brav.exit(self)

    def on_enter_auf_before_hier(self):
        auf_before_hier.enter(self)

    def on_exit_auf_before_hier(self):
        auf_before_hier.exit(self)

    def on_enter_perform_brav(self):
        perform_brav.enter(self)

    def on_exit_perform_brav(self):
        perform_brav.exit(self)
