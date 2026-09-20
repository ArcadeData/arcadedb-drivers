from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ServerInfoSettingsItem")


@_attrs_define
class ServerInfoSettingsItem:
    """One server setting

    Attributes:
        default (Any): Default value, masked the same way as 'value'
        description (str): What the setting does
        key (str): Setting key, e.g. 'arcadedb.server.httpQueryMaxResultRows'
        overridden (bool): True when this server's context overrides the default rather than inheriting it
        value (Any): Current value, or '*****' when the setting is hidden or its key names a password
    """

    default: Any
    description: str
    key: str
    overridden: bool
    value: Any
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        default = self.default

        description = self.description

        key = self.key

        overridden = self.overridden

        value = self.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "default": default,
                "description": description,
                "key": key,
                "overridden": overridden,
                "value": value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        default = d.pop("default")

        description = d.pop("description")

        key = d.pop("key")

        overridden = d.pop("overridden")

        value = d.pop("value")

        server_info_settings_item = cls(
            default=default,
            description=description,
            key=key,
            overridden=overridden,
            value=value,
        )

        server_info_settings_item.additional_properties = d
        return server_info_settings_item

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
