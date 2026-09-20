from enum import Enum


class McpConfigPrincipalProfilesAdditionalProperty(str, Enum):
    ADMIN = "admin"
    ALL = "all"
    RAG = "rag"

    def __str__(self) -> str:
        return str(self.value)
