from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.batch_edge_line_type import BatchEdgeLineType

T = TypeVar("T", bound="BatchEdgeLine")


@_attrs_define
class BatchEdgeLine:
    """An edge line. Its properties are the keys of this same object, flat beside the control keys below - they are NOT
    nested under a 'properties' key, and sending one carrying an object is refused with a 400.

        Attributes:
            class_ (str): Edge type to create the record in. The type must already exist: a bulk load creates records, never
                types.
            from_ (str): Source vertex. Under refMode=id (the default) this is the '@id' a vertex declared EARLIER IN THIS
                PAYLOAD, or an existing RID in #bucket:position form; each request resolves only the ids of its own payload.
                Under refMode=ordinal it is the vertex's 0-based position, offset by 'ordinalBase'.
            to (str): Destination vertex, named the same way as '@from'
            type_ (BatchEdgeLineType): Discriminator. 'e' is accepted as a synonym of 'edge'
    """

    class_: str
    from_: str
    to: str
    type_: BatchEdgeLineType
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        class_ = self.class_

        from_ = self.from_

        to = self.to

        type_ = self.type_.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "@class": class_,
                "@from": from_,
                "@to": to,
                "@type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        class_ = d.pop("@class")

        from_ = d.pop("@from")

        to = d.pop("@to")

        type_ = BatchEdgeLineType(d.pop("@type"))

        batch_edge_line = cls(
            class_=class_,
            from_=from_,
            to=to,
            type_=type_,
        )

        batch_edge_line.additional_properties = d
        return batch_edge_line

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
