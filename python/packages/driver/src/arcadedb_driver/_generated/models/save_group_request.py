from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.save_group_request_types import SaveGroupRequestTypes


T = TypeVar("T", bound="SaveGroupRequest")


@_attrs_define
class SaveGroupRequest:
    """A group to create or replace. Replaces any group of the same name on the same database outright - the members are
    not merged into the existing definition - and refreshes the cached permissions of every open database it applies to.

        Attributes:
            database (str): Database the group applies to. '*' means every database
            name (str): Group name
            access (list[str] | Unset): Server-level rights the group grants. Defaults to none
            read_timeout (int | Unset): Maximum milliseconds a member's read may take. Defaults to -1, no limit
            result_set_limit (int | Unset): Maximum rows a member may read in one result. Defaults to -1, no limit
            types (SaveGroupRequestTypes | Unset): Per-type permissions, keyed by type name. Defaults to none
    """

    database: str
    name: str
    access: list[str] | Unset = UNSET
    read_timeout: int | Unset = UNSET
    result_set_limit: int | Unset = UNSET
    types: SaveGroupRequestTypes | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database = self.database

        name = self.name

        access: list[str] | Unset = UNSET
        if not isinstance(self.access, Unset):
            access = self.access

        read_timeout = self.read_timeout

        result_set_limit = self.result_set_limit

        types: dict[str, Any] | Unset = UNSET
        if not isinstance(self.types, Unset):
            types = self.types.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "database": database,
                "name": name,
            }
        )
        if access is not UNSET:
            field_dict["access"] = access
        if read_timeout is not UNSET:
            field_dict["readTimeout"] = read_timeout
        if result_set_limit is not UNSET:
            field_dict["resultSetLimit"] = result_set_limit
        if types is not UNSET:
            field_dict["types"] = types

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.save_group_request_types import SaveGroupRequestTypes

        d = dict(src_dict)
        database = d.pop("database")

        name = d.pop("name")

        access = cast(list[str], d.pop("access", UNSET))

        read_timeout = d.pop("readTimeout", UNSET)

        result_set_limit = d.pop("resultSetLimit", UNSET)

        _types = d.pop("types", UNSET)
        types: SaveGroupRequestTypes | Unset
        if isinstance(_types, Unset):
            types = UNSET
        else:
            types = SaveGroupRequestTypes.from_dict(_types)

        save_group_request = cls(
            database=database,
            name=name,
            access=access,
            read_timeout=read_timeout,
            result_set_limit=result_set_limit,
            types=types,
        )

        save_group_request.additional_properties = d
        return save_group_request

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
