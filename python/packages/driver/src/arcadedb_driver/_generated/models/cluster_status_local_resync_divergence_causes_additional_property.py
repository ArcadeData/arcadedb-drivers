from enum import Enum


class ClusterStatusLocalResyncDivergenceCausesAdditionalProperty(str, Enum):
    APPLY_ERROR = "APPLY_ERROR"
    SNAPSHOT_INSTALL_INCOMPLETE = "SNAPSHOT_INSTALL_INCOMPLETE"
    UNDECODABLE_LOG_ENTRY = "UNDECODABLE_LOG_ENTRY"
    WAL_VERSION_GAP = "WAL_VERSION_GAP"

    def __str__(self) -> str:
        return str(self.value)
