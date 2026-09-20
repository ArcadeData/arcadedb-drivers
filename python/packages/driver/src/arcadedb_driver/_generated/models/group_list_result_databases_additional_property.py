from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.group_list_result_databases_additional_property_groups import (
        GroupListResultDatabasesAdditionalPropertyGroups,
    )


T = TypeVar("T", bound="GroupListResultDatabasesAdditionalProperty")


@_attrs_define
class GroupListResultDatabasesAdditionalProperty:
    """One database's groups

    Attributes:
        groups (GroupListResultDatabasesAdditionalPropertyGroups): The database's groups, keyed by group name
    """

    groups: GroupListResultDatabasesAdditionalPropertyGroups
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        groups = self.groups.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "groups": groups,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.group_list_result_databases_additional_property_groups import (
            GroupListResultDatabasesAdditionalPropertyGroups,
        )

        d = dict(src_dict)
        groups = GroupListResultDatabasesAdditionalPropertyGroups.from_dict(d.pop("groups"))

        group_list_result_databases_additional_property = cls(
            groups=groups,
        )

        group_list_result_databases_additional_property.additional_properties = d
        return group_list_result_databases_additional_property

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
