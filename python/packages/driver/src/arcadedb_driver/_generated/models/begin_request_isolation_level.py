from enum import Enum


class BeginRequestIsolationLevel(str, Enum):
    READ_COMMITTED = "READ_COMMITTED"
    REPEATABLE_READ = "REPEATABLE_READ"

    def __str__(self) -> str:
        return str(self.value)
