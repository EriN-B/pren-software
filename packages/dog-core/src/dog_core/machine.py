from dog_core.shared import SharedContext
from dog_core.states import waiting_for_command, found, perform_auf, perform_hier, perform_platz, returning, searching, startup, perform_sitz, perform_brav
from statemachine import State, StateMachine


class PrenMachine(StateMachine):
    startup = State(initial=True)
    waiting_for_command = State()
    searching = State()
    found = State()
    returning = State()
    perform_hier = State()
    perform_platz = State()
    perform_auf = State()
    perform_sitz = State()
    perform_brav = State()

    wait_for_command = startup.to(waiting_for_command)

    such = waiting_for_command.to(searching)
    signal = searching.to(found)
    return_back = found.to(returning)
    returned = returning.to(waiting_for_command)

    hier = waiting_for_command.to(perform_hier)
    sitz = waiting_for_command.to(perform_sitz)
    platz = waiting_for_command.to(perform_platz)
    auf = waiting_for_command.to(perform_auf)
    brav = waiting_for_command.to(perform_brav)

    command_finished = (
        perform_hier.to(waiting_for_command)
        | perform_platz.to(waiting_for_command)
        | perform_auf.to(waiting_for_command)
        | perform_sitz.to(waiting_for_command)
        | perform_brav.to(waiting_for_command)
    )
    
    def __init__(self):
        self.shared = SharedContext()
        self.waiting_handler = waiting_for_command.WaitingForCommand()
        super().__init__()

    def on_enter_startup(self):
        startup.enter(self)

    def on_exit_startup(self):
        startup.exit(self)

    def on_enter_waiting_for_command(self):
        self.waiting_handler.enter(self)

    def on_exit_waiting_for_command(self):
        self.waiting_handler.exit(self)

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
        perform_sitz.exit(self)

    def on_enter_perform_sitz(self):
        perform_sitz.enter(self)

    def on_exit_perform_sitz(self):
        perform_hier.exit(self)

    def on_enter_perform_platz(self):
        perform_platz.enter(self)

    def on_exit_perform_platz(self):
        perform_platz.exit(self)

    def on_enter_perform_auf(self):
        perform_auf.enter(self)

    def on_exit_perform_auf(self):
        perform_auf.exit(self)

    def on_enter_perform_brav(self):
        perform_brav.enter(self)

    def on_exit_perform_brav(self):
        perform_brav.exit(self)
