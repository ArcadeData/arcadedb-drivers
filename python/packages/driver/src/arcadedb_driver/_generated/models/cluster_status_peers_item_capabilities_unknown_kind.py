from enum import Enum


class ClusterStatusPeersItemCapabilitiesUnknownKind(str, Enum):
    ADDRESS_REFUSED = "ADDRESS_REFUSED"
    ROUTE_MISSING = "ROUTE_MISSING"
    STALE = "STALE"
    UNREACHABLE = "UNREACHABLE"

    def __str__(self) -> str:
        return str(self.value)
