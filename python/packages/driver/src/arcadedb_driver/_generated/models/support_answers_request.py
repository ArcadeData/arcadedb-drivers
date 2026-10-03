from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.support_answers_request_responses import SupportAnswersRequestResponses


T = TypeVar("T", bound="SupportAnswersRequest")


@_attrs_define
class SupportAnswersRequest:
    """Several answers, written as one comment

    Attributes:
        responses (SupportAnswersRequestResponses): A list of 1 to 20 answers, each as SupportAnswerRequest with its
            requestId
    """

    responses: SupportAnswersRequestResponses
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        responses = self.responses.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "responses": responses,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.support_answers_request_responses import SupportAnswersRequestResponses

        d = dict(src_dict)
        responses = SupportAnswersRequestResponses.from_dict(d.pop("responses"))

        support_answers_request = cls(
            responses=responses,
        )

        support_answers_request.additional_properties = d
        return support_answers_request

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
