from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.session_list_result_item import SessionListResultItem


T = TypeVar("T", bound="SessionList")


@_attrs_define
class SessionList:
    """Active authentication sessions

    Attributes:
        count (int): Number of active sessions
        result (list[SessionListResultItem]): Active sessions. Empty when this server holds none
    """

    count: int
    result: list[SessionListResultItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        result = []
        for result_item_data in self.result:
            result_item = result_item_data.to_dict()
            result.append(result_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
                "result": result,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.session_list_result_item import SessionListResultItem

        d = dict(src_dict)
        count = d.pop("count")

        result = []
        _result = d.pop("result")
        for result_item_data in _result:
            result_item = SessionListResultItem.from_dict(result_item_data)

            result.append(result_item)

        session_list = cls(
            count=count,
            result=result,
        )

        session_list.additional_properties = d
        return session_list

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
