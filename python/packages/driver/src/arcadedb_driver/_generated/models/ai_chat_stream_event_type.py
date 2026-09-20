from enum import Enum


class AiChatStreamEventType(str, Enum):
    DONE = "done"
    TOOL_END = "tool_end"
    TOOL_START = "tool_start"

    def __str__(self) -> str:
        return str(self.value)
