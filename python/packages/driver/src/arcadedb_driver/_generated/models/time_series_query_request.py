from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.time_series_query_request_aggregation import TimeSeriesQueryRequestAggregation
    from ..models.time_series_query_request_tags import TimeSeriesQueryRequestTags


T = TypeVar("T", bound="TimeSeriesQueryRequest")


@_attrs_define
class TimeSeriesQueryRequest:
    """Time-series query definition

    Attributes:
        type_ (str): Time-series type name
        aggregation (TimeSeriesQueryRequestAggregation | Unset): Bucketed aggregation. Present only when the caller
            wants buckets rather than raw rows.
        fields (list[str] | Unset): Fields to project. All fields when omitted.
        from_ (int | Unset): Inclusive lower bound of the timestamp range. Unbounded when omitted.
        limit (int | Unset): Maximum rows to return for a raw (non-aggregated) query. Defaults to 20000. Ignored when
            'aggregation' is present.
        tags (TimeSeriesQueryRequestTags | Unset): Tag filter as name to value pairs. All pairs must match. A name that
            is no TAG column of the type is refused with 400 rather than ignored.
        to (int | Unset): Inclusive upper bound of the timestamp range. Unbounded when omitted.
    """

    type_: str
    aggregation: TimeSeriesQueryRequestAggregation | Unset = UNSET
    fields: list[str] | Unset = UNSET
    from_: int | Unset = UNSET
    limit: int | Unset = UNSET
    tags: TimeSeriesQueryRequestTags | Unset = UNSET
    to: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        aggregation: dict[str, Any] | Unset = UNSET
        if not isinstance(self.aggregation, Unset):
            aggregation = self.aggregation.to_dict()

        fields: list[str] | Unset = UNSET
        if not isinstance(self.fields, Unset):
            fields = self.fields

        from_ = self.from_

        limit = self.limit

        tags: dict[str, Any] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags.to_dict()

        to = self.to

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
            }
        )
        if aggregation is not UNSET:
            field_dict["aggregation"] = aggregation
        if fields is not UNSET:
            field_dict["fields"] = fields
        if from_ is not UNSET:
            field_dict["from"] = from_
        if limit is not UNSET:
            field_dict["limit"] = limit
        if tags is not UNSET:
            field_dict["tags"] = tags
        if to is not UNSET:
            field_dict["to"] = to

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.time_series_query_request_aggregation import TimeSeriesQueryRequestAggregation
        from ..models.time_series_query_request_tags import TimeSeriesQueryRequestTags

        d = dict(src_dict)
        type_ = d.pop("type")

        _aggregation = d.pop("aggregation", UNSET)
        aggregation: TimeSeriesQueryRequestAggregation | Unset
        if isinstance(_aggregation, Unset):
            aggregation = UNSET
        else:
            aggregation = TimeSeriesQueryRequestAggregation.from_dict(_aggregation)

        fields = cast(list[str], d.pop("fields", UNSET))

        from_ = d.pop("from", UNSET)

        limit = d.pop("limit", UNSET)

        _tags = d.pop("tags", UNSET)
        tags: TimeSeriesQueryRequestTags | Unset
        if isinstance(_tags, Unset):
            tags = UNSET
        else:
            tags = TimeSeriesQueryRequestTags.from_dict(_tags)

        to = d.pop("to", UNSET)

        time_series_query_request = cls(
            type_=type_,
            aggregation=aggregation,
            fields=fields,
            from_=from_,
            limit=limit,
            tags=tags,
            to=to,
        )

        time_series_query_request.additional_properties = d
        return time_series_query_request

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
