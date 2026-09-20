from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.mcp_config_update_principal_profiles_additional_property import (
    McpConfigUpdatePrincipalProfilesAdditionalProperty,
)

T = TypeVar("T", bound="McpConfigUpdatePrincipalProfiles")


@_attrs_define
class McpConfigUpdatePrincipalProfiles:
    """Tool profile assigned per principal (user or API token) name. Present only when at least one is configured."""

    additional_properties: dict[str, McpConfigUpdatePrincipalProfilesAdditionalProperty] = _attrs_field(
        init=False, factory=dict
    )

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.value

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        mcp_config_update_principal_profiles = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = McpConfigUpdatePrincipalProfilesAdditionalProperty(prop_dict)

            additional_properties[prop_name] = additional_property

        mcp_config_update_principal_profiles.additional_properties = additional_properties
        return mcp_config_update_principal_profiles

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> McpConfigUpdatePrincipalProfilesAdditionalProperty:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: McpConfigUpdatePrincipalProfilesAdditionalProperty) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
