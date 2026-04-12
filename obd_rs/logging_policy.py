from dataclasses import dataclass

from .config import LOG_MODE_CADENCE, LogMode, PollCadence


@dataclass
class LoggingPolicy:
    mode: LogMode = LogMode.CRUISE

    def cadence(self) -> PollCadence:
        return LOG_MODE_CADENCE[self.mode]

    def set_mode(self, mode: LogMode) -> None:
        self.mode = mode
