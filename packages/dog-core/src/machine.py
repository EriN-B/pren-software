from shared import SharedContext
from states import waiting_for_command, found, perform_auf, perform_hier, perform_platz, returning, searching, startup
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

    start = startup.to(waiting_for_command)

    search = waiting_for_command.to(searching)
    locate = searching.to(found)
    return_back = found.to(returning)
    returned = returning.to(waiting_for_command)

    hier = waiting_for_command.to(perform_hier)
    platz = waiting_for_command.to(perform_platz)
    auf = waiting_for_command.to(perform_auf)

    command_finished = (
        perform_hier.to(waiting_for_command)
        | perform_platz.to(waiting_for_command)
        | perform_auf.to(waiting_for_command)
    )
    
    def __init_(self):
        self.shared = SharedContext()
        super().__init__()

    def on_enter_startup(self):
        startup.enter(self)

    def on_exit_startup(self):
        startup.exit(self)

    def on_enter_waiting_for_command(self):
        waiting_for_command.enter(self)

    def on_exit_waiting_for_command(self):
        waiting_for_command.exit(self)

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

    def on_enter_perform_platz(self):
        perform_platz.enter(self)

    def on_exit_perform_platz(self):
        perform_platz.exit(self)

    def on_enter_perform_auf(self):
        perform_auf.enter(self)

    def on_exit_perform_auf(self):
        perform_auf.exit(self)
