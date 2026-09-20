from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.create_api_token_response_result import CreateApiTokenResponseResult


T = TypeVar("T", bound="CreateApiTokenResponse")


@_attrs_define
class CreateApiTokenResponse:
    """Result of issuing an API token

    Attributes:
        result (CreateApiTokenResponseResult): The issued token: every field the listing carries, plus the plaintext
            'token'. Read it now - the server stores only the hash, so this is the one and only time that value exists
            outside the caller's hands.
    """

    result: CreateApiTokenResponseResult
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = self.result.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_api_token_response_result import CreateApiTokenResponseResult

        d = dict(src_dict)
        result = CreateApiTokenResponseResult.from_dict(d.pop("result"))

        create_api_token_response = cls(
            result=result,
        )

        create_api_token_response.additional_properties = d
        return create_api_token_response

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
