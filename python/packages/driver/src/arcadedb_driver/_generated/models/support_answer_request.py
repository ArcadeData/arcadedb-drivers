from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.support_answer_request_result import SupportAnswerRequestResult


T = TypeVar("T", bound="SupportAnswerRequest")


@_attrs_define
class SupportAnswerRequest:
    """The answer to a support request

    Attributes:
        outcome (str): answered, declined or failed
        duration_ms (int | Unset): How long the query ran
        reason (str | Unset): declined, or failed: why, at most 500 characters
        result (SupportAnswerRequestResult | Unset): answered only: {columns: [{name, type}], rows: [[...]], truncated,
            masked: {cells: [[row, column]], columns: [name], mode: redact|hash}}. Masked values are replaced before they
            are sent; either result or text, not both
        text (str | Unset): answered only: pasted text instead of a result, at most 20000 characters
    """

    outcome: str
    duration_ms: int | Unset = UNSET
    reason: str | Unset = UNSET
    result: SupportAnswerRequestResult | Unset = UNSET
    text: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        outcome = self.outcome

        duration_ms = self.duration_ms

        reason = self.reason

        result: dict[str, Any] | Unset = UNSET
        if not isinstance(self.result, Unset):
            result = self.result.to_dict()

        text = self.text

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "outcome": outcome,
            }
        )
        if duration_ms is not UNSET:
            field_dict["durationMs"] = duration_ms
        if reason is not UNSET:
            field_dict["reason"] = reason
        if result is not UNSET:
            field_dict["result"] = result
        if text is not UNSET:
            field_dict["text"] = text

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.support_answer_request_result import SupportAnswerRequestResult

        d = dict(src_dict)
        outcome = d.pop("outcome")

        duration_ms = d.pop("durationMs", UNSET)

        reason = d.pop("reason", UNSET)

        _result = d.pop("result", UNSET)
        result: SupportAnswerRequestResult | Unset
        if isinstance(_result, Unset):
            result = UNSET
        else:
            result = SupportAnswerRequestResult.from_dict(_result)

        text = d.pop("text", UNSET)

        support_answer_request = cls(
            outcome=outcome,
            duration_ms=duration_ms,
            reason=reason,
            result=result,
            text=text,
        )

        support_answer_request.additional_properties = d
        return support_answer_request

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
