from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.group_definition_types import GroupDefinitionTypes


T = TypeVar("T", bound="GroupDefinition")


@_attrs_define
class GroupDefinition:
    """One group's permissions on one database. Stored normalized: a member the request omitted is written with the default
    below rather than left absent, so a group read back always carries all four.

        Attributes:
            access (list[str]): Server-level rights the group grants. Empty when it grants none
            read_timeout (int): Maximum milliseconds a member's read may take. -1 for no limit Example: -1.
            result_set_limit (int): Maximum rows a member of this group may read in one result. -1 for no limit Example: -1.
            types (GroupDefinitionTypes): Per-type permissions, keyed by type name. '*' is a legal key and covers every
                type. An open map because the keys are the schema's own type names.
    """

    access: list[str]
    read_timeout: int
    result_set_limit: int
    types: GroupDefinitionTypes
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        access = self.access

        read_timeout = self.read_timeout

        result_set_limit = self.result_set_limit

        types = self.types.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "access": access,
                "readTimeout": read_timeout,
                "resultSetLimit": result_set_limit,
                "types": types,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.group_definition_types import GroupDefinitionTypes

        d = dict(src_dict)
        access = cast(list[str], d.pop("access"))

        read_timeout = d.pop("readTimeout")

        result_set_limit = d.pop("resultSetLimit")

        types = GroupDefinitionTypes.from_dict(d.pop("types"))

        group_definition = cls(
            access=access,
            read_timeout=read_timeout,
            result_set_limit=result_set_limit,
            types=types,
        )

        group_definition.additional_properties = d
        return group_definition

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
