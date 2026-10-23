from statemachine import StateMachine
from packages.core.shared import SharedContext

class StateTemplate:
    """Example state only; replace with actual logic."""

    def __init__(
        self,
        machine: "StateMachine",
        shared: SharedContext,
        next_event: str = "locate",
    ) -> None:
        self.machine = machine
        self.shared = shared
        self.next_event = next_event

        # Attributes private to this state's work, reset on each entry.
        self.attribute = None

    def enter(self) -> None:
        pass

    def doSometing(self) -> None:
        pass

    def exit(self) -> None:
        # Clean up resources owned only by this state here.
        pass
    