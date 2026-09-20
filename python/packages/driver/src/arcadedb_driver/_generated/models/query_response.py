from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.query_response_explain_plan import QueryResponseExplainPlan
    from ..models.query_response_result_type_0_item import QueryResponseResultType0Item
    from ..models.query_response_result_type_1 import QueryResponseResultType1


T = TypeVar("T", bound="QueryResponse")


@_attrs_define
class QueryResponse:
    """Query response object

    Attributes:
        limit (int): Effective row cap applied while serializing, -1 when uncapped. This is the serializer's cap, not
            the query's own LIMIT: a query stating a LIMIT below the server default reports the default here, and 'returned'
            with 'truncated' describe what the response actually carries.
        returned (int): Number of rows carried by this response. With the 'graph' serializer, whose cap counts graph
            elements rather than rows, it is the number of serialized vertices plus edges, and it can exceed 'limit': a
            single row can expand into several elements, and the expansion of the row that reaches the cap is not cut in
            half.
        truncated (bool): True when the cap stopped the serialization with rows still pending, so the response is
            incomplete
        explain (str | Unset): The execution plan as indented text, one line per step. Present on an EXPLAIN or PROFILE
            statement, and on any statement run with 'profileExecution'; absent otherwise. 'result' is then empty: the plan
            is the answer, and it is not also repeated as a row.
        explain_plan (QueryResponseExplainPlan | Unset): The same plan in structured form, for a caller that reads the
            steps rather than prints them. Present exactly when 'explain' is.
        result (list[QueryResponseResultType0Item] | QueryResponseResultType1 | Unset): The rows, shaped by the
            'serializer' the request asked for: an array with the default 'record' serializer, and one {vertices, edges}
            object - plus 'records' under 'studio' - with the two graph serializers.
    """

    limit: int
    returned: int
    truncated: bool
    explain: str | Unset = UNSET
    explain_plan: QueryResponseExplainPlan | Unset = UNSET
    result: list[QueryResponseResultType0Item] | QueryResponseResultType1 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        limit = self.limit

        returned = self.returned

        truncated = self.truncated

        explain = self.explain

        explain_plan: dict[str, Any] | Unset = UNSET
        if not isinstance(self.explain_plan, Unset):
            explain_plan = self.explain_plan.to_dict()

        result: dict[str, Any] | list[dict[str, Any]] | Unset
        if isinstance(self.result, Unset):
            result = UNSET
        elif isinstance(self.result, list):
            result = []
            for result_type_0_item_data in self.result:
                result_type_0_item = result_type_0_item_data.to_dict()
                result.append(result_type_0_item)

        else:
            result = self.result.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "limit": limit,
                "returned": returned,
                "truncated": truncated,
            }
        )
        if explain is not UNSET:
            field_dict["explain"] = explain
        if explain_plan is not UNSET:
            field_dict["explainPlan"] = explain_plan
        if result is not UNSET:
            field_dict["result"] = result

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.query_response_explain_plan import QueryResponseExplainPlan
        from ..models.query_response_result_type_0_item import QueryResponseResultType0Item
        from ..models.query_response_result_type_1 import QueryResponseResultType1

        d = dict(src_dict)
        limit = d.pop("limit")

        returned = d.pop("returned")

        truncated = d.pop("truncated")

        explain = d.pop("explain", UNSET)

        _explain_plan = d.pop("explainPlan", UNSET)
        explain_plan: QueryResponseExplainPlan | Unset
        if isinstance(_explain_plan, Unset):
            explain_plan = UNSET
        else:
            explain_plan = QueryResponseExplainPlan.from_dict(_explain_plan)

        def _parse_result(data: object) -> list[QueryResponseResultType0Item] | QueryResponseResultType1 | Unset:
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                result_type_0 = []
                _result_type_0 = data
                for result_type_0_item_data in _result_type_0:
                    result_type_0_item = QueryResponseResultType0Item.from_dict(result_type_0_item_data)

                    result_type_0.append(result_type_0_item)

                return result_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            result_type_1 = QueryResponseResultType1.from_dict(data)

            return result_type_1

        result = _parse_result(d.pop("result", UNSET))

        query_response = cls(
            limit=limit,
            returned=returned,
            truncated=truncated,
            explain=explain,
            explain_plan=explain_plan,
            result=result,
        )

        query_response.additional_properties = d
        return query_response

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
