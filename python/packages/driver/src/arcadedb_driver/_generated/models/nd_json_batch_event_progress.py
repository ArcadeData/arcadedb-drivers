from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.nd_json_batch_event_progress_id_mapping import NdJsonBatchEventProgressIdMapping


T = TypeVar("T", bound="NdJsonBatchEventProgress")


@_attrs_define
class NdJsonBatchEventProgress:
    """A chunk acknowledgement, written while the request body is still being read. Emitted at every vertex commit and
    every 'commitEvery' edges. The counters are records ATTEMPTED, the same upper bound on what is durable that the
    partial-commit counters carry: vertices are committed at each flush, while edges are buffered and written when the
    load ends.

        Attributes:
            bytes_read (int | Unset): Bytes of the upload the server consumed, so a client can verify its whole file arrived
                - and, on a truncated load, how far the server got. Never more than the client sent.
            edges_created (int | Unset): Edges attempted so far
            id_mapping (NdJsonBatchEventProgressIdMapping | Unset): Temporary id to RID mapping of the vertices this chunk
                resolved, and only of those: the mapping is handed back one committed chunk at a time so neither end ever holds
                the whole load's worth of it (issue #7353). Concatenate the 'idMapping' of every line, in order, to obtain what
                the buffered encoding returns in one object, and check the total against 'idMappingSize' on the terminal line.
                Absent on an edge-phase acknowledgement, on a chunk whose vertices declared no @id under refMode=tempId, and
                when the request sent idMapping=false.
            lines_read (int | Unset): Lines the parser read, so 'linesRead' minus 'linesSkipped' can be checked against the
                records created
            lines_skipped (int | Unset): Lines that carried no record: blank lines, plus CSV headers and '---' separators
            phase (str | Unset): 'vertices' or 'edges'
            vertices_created (int | Unset): Vertices attempted so far
            vertices_without_id (int | Unset): Vertices created without an '@id' under refMode=id. They are loaded and
                durable, but no edge can reference them. Absent when zero.
    """

    bytes_read: int | Unset = UNSET
    edges_created: int | Unset = UNSET
    id_mapping: NdJsonBatchEventProgressIdMapping | Unset = UNSET
    lines_read: int | Unset = UNSET
    lines_skipped: int | Unset = UNSET
    phase: str | Unset = UNSET
    vertices_created: int | Unset = UNSET
    vertices_without_id: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        bytes_read = self.bytes_read

        edges_created = self.edges_created

        id_mapping: dict[str, Any] | Unset = UNSET
        if not isinstance(self.id_mapping, Unset):
            id_mapping = self.id_mapping.to_dict()

        lines_read = self.lines_read

        lines_skipped = self.lines_skipped

        phase = self.phase

        vertices_created = self.vertices_created

        vertices_without_id = self.vertices_without_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if bytes_read is not UNSET:
            field_dict["bytesRead"] = bytes_read
        if edges_created is not UNSET:
            field_dict["edgesCreated"] = edges_created
        if id_mapping is not UNSET:
            field_dict["idMapping"] = id_mapping
        if lines_read is not UNSET:
            field_dict["linesRead"] = lines_read
        if lines_skipped is not UNSET:
            field_dict["linesSkipped"] = lines_skipped
        if phase is not UNSET:
            field_dict["phase"] = phase
        if vertices_created is not UNSET:
            field_dict["verticesCreated"] = vertices_created
        if vertices_without_id is not UNSET:
            field_dict["verticesWithoutId"] = vertices_without_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.nd_json_batch_event_progress_id_mapping import NdJsonBatchEventProgressIdMapping

        d = dict(src_dict)
        bytes_read = d.pop("bytesRead", UNSET)

        edges_created = d.pop("edgesCreated", UNSET)

        _id_mapping = d.pop("idMapping", UNSET)
        id_mapping: NdJsonBatchEventProgressIdMapping | Unset
        if isinstance(_id_mapping, Unset):
            id_mapping = UNSET
        else:
            id_mapping = NdJsonBatchEventProgressIdMapping.from_dict(_id_mapping)

        lines_read = d.pop("linesRead", UNSET)

        lines_skipped = d.pop("linesSkipped", UNSET)

        phase = d.pop("phase", UNSET)

        vertices_created = d.pop("verticesCreated", UNSET)

        vertices_without_id = d.pop("verticesWithoutId", UNSET)

        nd_json_batch_event_progress = cls(
            bytes_read=bytes_read,
            edges_created=edges_created,
            id_mapping=id_mapping,
            lines_read=lines_read,
            lines_skipped=lines_skipped,
            phase=phase,
            vertices_created=vertices_created,
            vertices_without_id=vertices_without_id,
        )

        nd_json_batch_event_progress.additional_properties = d
        return nd_json_batch_event_progress

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
