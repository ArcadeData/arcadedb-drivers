from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.batch_vertex_line_type import BatchVertexLineType
from ..types import UNSET, Unset

T = TypeVar("T", bound="BatchVertexLine")


@_attrs_define
class BatchVertexLine:
    """A vertex line. Its properties are the keys of this same object, flat beside the control keys below - they are NOT
    nested under a 'properties' key, and sending one carrying an object is refused with a 400. '@from' and '@to' name an
    edge's endpoints and a vertex has none: carrying either here is refused with a 400 naming the line, not dropped.

        Attributes:
            class_ (str): Vertex type to create the record in. The type must already exist: a bulk load creates records,
                never types.
            type_ (BatchVertexLineType): Discriminator. 'v' is accepted as a synonym of 'vertex'
            id (str | Unset): Temporary id, resolved only against the edges of THIS request. Optional - a vertex needs one
                only if an edge in the same payload references it, and one that declares none is counted in 'verticesWithoutId'.
                Ignored under refMode=ordinal, where an edge names a vertex by its 0-based position instead.
    """

    class_: str
    type_: BatchVertexLineType
    id: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        class_ = self.class_

        type_ = self.type_.value

        id = self.id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "@class": class_,
                "@type": type_,
            }
        )
        if id is not UNSET:
            field_dict["@id"] = id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        class_ = d.pop("@class")

        type_ = BatchVertexLineType(d.pop("@type"))

        id = d.pop("@id", UNSET)

        batch_vertex_line = cls(
            class_=class_,
            type_=type_,
            id=id,
        )

        batch_vertex_line.additional_properties = d
        return batch_vertex_line

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
