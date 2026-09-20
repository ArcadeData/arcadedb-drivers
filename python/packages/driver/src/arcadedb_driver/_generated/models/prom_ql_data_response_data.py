from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.prom_ql_data_response_data_result_type import PromQLDataResponseDataResultType

if TYPE_CHECKING:
    from ..models.prom_ql_data_response_data_result_type_0_item import PromQLDataResponseDataResultType0Item
    from ..models.prom_ql_data_response_data_result_type_1_item import PromQLDataResponseDataResultType1Item


T = TypeVar("T", bound="PromQLDataResponseData")


@_attrs_define
class PromQLDataResponseData:
    """Evaluation result

    Attributes:
        result (list[Any] | list[PromQLDataResponseDataResultType0Item] | list[PromQLDataResponseDataResultType1Item]):
            Evaluation result, shaped by 'resultType': an array of instant samples when 'vector', an array of range series
            when 'matrix', and a single [timestamp, value] pair when 'scalar'.
        result_type (PromQLDataResponseDataResultType): Shape of 'result': a vector of instant samples, a matrix of
            range samples, or a scalar
    """

    result: list[Any] | list[PromQLDataResponseDataResultType0Item] | list[PromQLDataResponseDataResultType1Item]
    result_type: PromQLDataResponseDataResultType
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: list[Any] | list[dict[str, Any]]
        if isinstance(self.result, list):
            result = []
            for result_type_0_item_data in self.result:
                result_type_0_item = result_type_0_item_data.to_dict()
                result.append(result_type_0_item)

        elif isinstance(self.result, list):
            result = []
            for result_type_1_item_data in self.result:
                result_type_1_item = result_type_1_item_data.to_dict()
                result.append(result_type_1_item)

        else:
            result = self.result

        result_type = self.result_type.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
                "resultType": result_type,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.prom_ql_data_response_data_result_type_0_item import PromQLDataResponseDataResultType0Item
        from ..models.prom_ql_data_response_data_result_type_1_item import PromQLDataResponseDataResultType1Item

        d = dict(src_dict)

        def _parse_result(
            data: object,
        ) -> list[Any] | list[PromQLDataResponseDataResultType0Item] | list[PromQLDataResponseDataResultType1Item]:
            try:
                if not isinstance(data, list):
                    raise TypeError()
                result_type_0 = []
                _result_type_0 = data
                for result_type_0_item_data in _result_type_0:
                    result_type_0_item = PromQLDataResponseDataResultType0Item.from_dict(result_type_0_item_data)

                    result_type_0.append(result_type_0_item)

                return result_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                result_type_1 = []
                _result_type_1 = data
                for result_type_1_item_data in _result_type_1:
                    result_type_1_item = PromQLDataResponseDataResultType1Item.from_dict(result_type_1_item_data)

                    result_type_1.append(result_type_1_item)

                return result_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, list):
                raise TypeError()
            result_type_2 = cast(list[Any], data)

            return result_type_2

        result = _parse_result(d.pop("result"))

        result_type = PromQLDataResponseDataResultType(d.pop("resultType"))

        prom_ql_data_response_data = cls(
            result=result,
            result_type=result_type,
        )

        prom_ql_data_response_data.additional_properties = d
        return prom_ql_data_response_data

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
