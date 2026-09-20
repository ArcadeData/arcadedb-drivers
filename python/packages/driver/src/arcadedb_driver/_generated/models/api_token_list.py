from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.api_token_list_result_item import ApiTokenListResultItem


T = TypeVar("T", bound="ApiTokenList")


@_attrs_define
class ApiTokenList:
    """Every issued API token

    Attributes:
        count (int): Number of tokens returned
        result (list[ApiTokenListResultItem]): Tokens, metadata only
    """

    count: int
    result: list[ApiTokenListResultItem]
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
        from ..models.api_token_list_result_item import ApiTokenListResultItem

        d = dict(src_dict)
        count = d.pop("count")

        result = []
        _result = d.pop("result")
        for result_item_data in _result:
            result_item = ApiTokenListResultItem.from_dict(result_item_data)

            result.append(result_item)

        api_token_list = cls(
            count=count,
            result=result,
        )

        api_token_list.additional_properties = d
        return api_token_list

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
