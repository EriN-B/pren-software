"""Collects every log line for the viewer's log dock: sim host, dog core and UART traffic.

The viewer shows them in one list, filterable by source. Sources:

| source | from                                                         |
| ------ | ------------------------------------------------------------ |
| `core` | the core's own logger (``state_machine``)                    |
| `uart` | every command the core sends to the emulated Pico            |
| `sim`  | everything else logged in this process (sim host, libraries) |
"""

import logging
from collections import deque

#: Logger names with their own source; every other logger counts as "sim".
SOURCES = {"state_machine": "core", "dog_sim_host.uart": "uart"}


class LogBuffer(logging.Handler):
    """Keeps the newest log records as plain dicts, numbered so viewers can catch up.

    Args:
        size: How many entries to keep.
    """

    def __init__(self, size: int = 3000) -> None:
        super().__init__(logging.INFO)
        self.entries: deque[dict] = deque(maxlen=size)
        self._seq = 0
        self._last: logging.LogRecord | None = None

    def emit(self, record: logging.LogRecord) -> None:
        # Handler.handle holds self.lock here, so the core's thread and ours cannot clash.
        if (
            record is self._last
        ):  # reached us twice: through the filter and the root logger
            return
        self._last = record
        self._seq += 1
        self.entries.append(
            {
                "seq": self._seq,
                "time": round(record.created, 3),
                "source": SOURCES.get(record.name, "sim"),
                "level": record.levelname,
                "message": record.getMessage(),
            }
        )

    def since(self, seq: int) -> list[dict]:
        """Entries newer than `seq`, oldest first."""
        return [entry for entry in list(self.entries) if entry["seq"] > seq]

    @property
    def last_seq(self) -> int:
        return self._seq

    def attach(self) -> None:
        """Start collecting: this process's loggers, the core's and the UART log."""
        logging.getLogger().addHandler(self)
        # The core's logger does not propagate, and the core adds its console handler
        # only when the logger has none, so read it through a filter instead.
        logging.getLogger("state_machine").addFilter(
            lambda record: self.handle(record) or True
        )
        uart = logging.getLogger("dog_sim_host.uart")
        uart.propagate = False  # many lines a second: the viewer, not the terminal
        uart.setLevel(logging.INFO)
        uart.addHandler(self)
