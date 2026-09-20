from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.batch_response_id_mapping import BatchResponseIdMapping


T = TypeVar("T", bound="BatchResponse")


@_attrs_define
class BatchResponse:
    """Result of a bulk load

    Attributes:
        bytes_read (int): Bytes of the upload the server consumed, so a client can verify its whole file arrived - and,
            on a truncated load, how far the server got. Never more than the client sent.
        edges_created (int): Edges created
        elapsed_ms (int): Elapsed time in milliseconds
        lines_read (int): Lines the parser read, so 'linesRead' minus 'linesSkipped' can be checked against the records
            created
        lines_skipped (int): Lines that carried no record: blank lines, plus CSV headers and '---' separators
        vertices_created (int): Vertices created
        id_mapping (BatchResponseIdMapping | Unset): Temporary id to RID mapping, present only when temporary ids were
            used and the mapping was small enough to echo
        id_mapping_omitted (bool | Unset): True when the mapping was too large to return
        id_mapping_size (int | Unset): Number of entries in the omitted mapping
        vertices_without_id (int | Unset): Vertices created without an '@id' under refMode=id. They are loaded and
            durable, but no edge can reference them. Absent when zero.
    """

    bytes_read: int
    edges_created: int
    elapsed_ms: int
    lines_read: int
    lines_skipped: int
    vertices_created: int
    id_mapping: BatchResponseIdMapping | Unset = UNSET
    id_mapping_omitted: bool | Unset = UNSET
    id_mapping_size: int | Unset = UNSET
    vertices_without_id: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        bytes_read = self.bytes_read

        edges_created = self.edges_created

        elapsed_ms = self.elapsed_ms

        lines_read = self.lines_read

        lines_skipped = self.lines_skipped

        vertices_created = self.vertices_created

        id_mapping: dict[str, Any] | Unset = UNSET
        if not isinstance(self.id_mapping, Unset):
            id_mapping = self.id_mapping.to_dict()

        id_mapping_omitted = self.id_mapping_omitted

        id_mapping_size = self.id_mapping_size

        vertices_without_id = self.vertices_without_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "bytesRead": bytes_read,
                "edgesCreated": edges_created,
                "elapsedMs": elapsed_ms,
                "linesRead": lines_read,
                "linesSkipped": lines_skipped,
                "verticesCreated": vertices_created,
            }
        )
        if id_mapping is not UNSET:
            field_dict["idMapping"] = id_mapping
        if id_mapping_omitted is not UNSET:
            field_dict["idMappingOmitted"] = id_mapping_omitted
        if id_mapping_size is not UNSET:
            field_dict["idMappingSize"] = id_mapping_size
        if vertices_without_id is not UNSET:
            field_dict["verticesWithoutId"] = vertices_without_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_response_id_mapping import BatchResponseIdMapping

        d = dict(src_dict)
        bytes_read = d.pop("bytesRead")

        edges_created = d.pop("edgesCreated")

        elapsed_ms = d.pop("elapsedMs")

        lines_read = d.pop("linesRead")

        lines_skipped = d.pop("linesSkipped")

        vertices_created = d.pop("verticesCreated")

        _id_mapping = d.pop("idMapping", UNSET)
        id_mapping: BatchResponseIdMapping | Unset
        if isinstance(_id_mapping, Unset):
            id_mapping = UNSET
        else:
            id_mapping = BatchResponseIdMapping.from_dict(_id_mapping)

        id_mapping_omitted = d.pop("idMappingOmitted", UNSET)

        id_mapping_size = d.pop("idMappingSize", UNSET)

        vertices_without_id = d.pop("verticesWithoutId", UNSET)

        batch_response = cls(
            bytes_read=bytes_read,
            edges_created=edges_created,
            elapsed_ms=elapsed_ms,
            lines_read=lines_read,
            lines_skipped=lines_skipped,
            vertices_created=vertices_created,
            id_mapping=id_mapping,
            id_mapping_omitted=id_mapping_omitted,
            id_mapping_size=id_mapping_size,
            vertices_without_id=vertices_without_id,
        )

        batch_response.additional_properties = d
        return batch_response

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
