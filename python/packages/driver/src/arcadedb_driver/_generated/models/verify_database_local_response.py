from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.verify_database_local_response_files_item import VerifyDatabaseLocalResponseFilesItem
    from ..models.verify_database_local_response_local_checksums import VerifyDatabaseLocalResponseLocalChecksums


T = TypeVar("T", bound="VerifyDatabaseLocalResponse")


@_attrs_define
class VerifyDatabaseLocalResponse:
    """One node's own checksums, for the leader to compare against. Answered by a follower, and by a leader whose request
    carried the already-forwarded marker.

        Attributes:
            files (list[VerifyDatabaseLocalResponseFilesItem]): Files with size and category
            local_checksums (VerifyDatabaseLocalResponseLocalChecksums): File name to checksum map, for a quick cross-peer
                comparison
            local_server (str): Server the checksums were taken on
            sealed_stores_included (bool): True when this build checksums the TimeSeries sealed stores as well (issue
                #7338). A peer on an older build omits the flag, and the leader then leaves its sealed files out of the
                comparison rather than reporting every one of them MISSING - a rolling upgrade must not make the divergence
                detector cry divergence over a file the other side was never asked to checksum. Stays true even when
                'sealedStoresComplete' is false: "my build checksums them" and "this answer covers them" are different
                statements.
            sealed_stores_complete (bool | Unset): Present and false when this answer did NOT cover every sealed store - an
                unreadable file, or a compaction pause the node could not take. Absent when coverage was complete.
    """

    files: list[VerifyDatabaseLocalResponseFilesItem]
    local_checksums: VerifyDatabaseLocalResponseLocalChecksums
    local_server: str
    sealed_stores_included: bool
    sealed_stores_complete: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        files = []
        for files_item_data in self.files:
            files_item = files_item_data.to_dict()
            files.append(files_item)

        local_checksums = self.local_checksums.to_dict()

        local_server = self.local_server

        sealed_stores_included = self.sealed_stores_included

        sealed_stores_complete = self.sealed_stores_complete

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "files": files,
                "localChecksums": local_checksums,
                "localServer": local_server,
                "sealedStoresIncluded": sealed_stores_included,
            }
        )
        if sealed_stores_complete is not UNSET:
            field_dict["sealedStoresComplete"] = sealed_stores_complete

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.verify_database_local_response_files_item import VerifyDatabaseLocalResponseFilesItem
        from ..models.verify_database_local_response_local_checksums import VerifyDatabaseLocalResponseLocalChecksums

        d = dict(src_dict)
        files = []
        _files = d.pop("files")
        for files_item_data in _files:
            files_item = VerifyDatabaseLocalResponseFilesItem.from_dict(files_item_data)

            files.append(files_item)

        local_checksums = VerifyDatabaseLocalResponseLocalChecksums.from_dict(d.pop("localChecksums"))

        local_server = d.pop("localServer")

        sealed_stores_included = d.pop("sealedStoresIncluded")

        sealed_stores_complete = d.pop("sealedStoresComplete", UNSET)

        verify_database_local_response = cls(
            files=files,
            local_checksums=local_checksums,
            local_server=local_server,
            sealed_stores_included=sealed_stores_included,
            sealed_stores_complete=sealed_stores_complete,
        )

        verify_database_local_response.additional_properties = d
        return verify_database_local_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
