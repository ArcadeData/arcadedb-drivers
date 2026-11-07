from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.facet_result_source import FacetResultSource
from ..models.facet_result_type import FacetResultType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.facet_bucket import FacetBucket


T = TypeVar("T", bound="FacetResult")


@_attrs_define
class FacetResult:
    """One facet. Terms, range, histogram and hierarchy facets carry 'buckets'; a distinct facet carries 'value' and
    'exact'; a stats facet carries 'count', 'min', 'max', 'sum' and 'avg'. A facet that could not be computed has source
    'unavailable', a 'reason' and no other result member.

        Attributes:
            source (FacetResultSource): How the facet was computed: 'index' from the columnar projection, 'scan' when at
                least one bucket of the type was read from the records, 'unavailable' when it could not be computed (see
                'reason').
            type_ (FacetResultType): Kind of the facet
            props (str | Unset): Present only when the request asked for type hints ('typeHints') and a member of the facet
                is of a type JSON does not round-trip (a date, a decimal, a long, a float, ...): comma separated entries in the
                form a result row's hint takes, 'value:<type id>' for the values of the property (bucket values, a stats facet's
                min and max, the cursor), 'sum:<type id>' and 'avg:<type id>' for a stats facet's sum and average, to restore
                each as a column of that type.
            after (Any | Unset): Cursor to pass to AFTER to get the next page of buckets: the last value of this page,
                written as a row's value of the property; null when no value follows. Present on every terms facet ordered by
                VALUE ASC (the default for VALUE, and implied by AFTER) without INCLUDE; a VALUE DESC facet has none. Echo it
                exactly as received: a value rewritten by the client, such as a date-time reformatted or truncated to its sub-
                second part, can start the next page elsewhere.
            avg (Any | Unset): STATS: the average of the values, the value and type SELECT avg() gives (a non-finite one by
                its name, as a row's); null for a date property or when no matching record has a value
            buckets (list[FacetBucket] | Unset): The buckets, ranked as the FACETS clause asked. Absent from distinct, stats
                and unavailable facets
            count (int | Unset): STATS: the number of matching records with a value
            exact (bool | Unset): DISTINCT: false when the number of distinct values is approximate
            max_ (Any | Unset): STATS: the largest value, a value of the type of the property written as a row's value of
                it; null when no matching record has a value
            min_ (Any | Unset): STATS: the smallest value, a value of the type of the property written as a row's value of
                it (a date in the database's date format); null when no matching record has a value
            missing (int | Unset): Number of matching records without a value for the faceted property
            other_count (int | Unset): Sum of the counts of the values not returned in 'buckets'. Written by terms and
                hierarchy facets only
            reason (str | Unset): Why the facet is unavailable. Present only when source is 'unavailable'
            sum_ (Any | Unset): STATS: the sum of the values, the value and type SELECT sum() gives (a non-finite one by its
                name, as a row's); null for a date property or when no matching record has a value
            value (int | Unset): DISTINCT: the number of distinct values
    """

    source: FacetResultSource
    type_: FacetResultType
    props: str | Unset = UNSET
    after: Any | Unset = UNSET
    avg: Any | Unset = UNSET
    buckets: list[FacetBucket] | Unset = UNSET
    count: int | Unset = UNSET
    exact: bool | Unset = UNSET
    max_: Any | Unset = UNSET
    min_: Any | Unset = UNSET
    missing: int | Unset = UNSET
    other_count: int | Unset = UNSET
    reason: str | Unset = UNSET
    sum_: Any | Unset = UNSET
    value: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source = self.source.value

        type_ = self.type_.value

        props = self.props

        after = self.after

        avg = self.avg

        buckets: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.buckets, Unset):
            buckets = []
            for buckets_item_data in self.buckets:
                buckets_item = buckets_item_data.to_dict()
                buckets.append(buckets_item)

        count = self.count

        exact = self.exact

        max_ = self.max_

        min_ = self.min_

        missing = self.missing

        other_count = self.other_count

        reason = self.reason

        sum_ = self.sum_

        value = self.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source": source,
                "type": type_,
            }
        )
        if props is not UNSET:
            field_dict["@props"] = props
        if after is not UNSET:
            field_dict["after"] = after
        if avg is not UNSET:
            field_dict["avg"] = avg
        if buckets is not UNSET:
            field_dict["buckets"] = buckets
        if count is not UNSET:
            field_dict["count"] = count
        if exact is not UNSET:
            field_dict["exact"] = exact
        if max_ is not UNSET:
            field_dict["max"] = max_
        if min_ is not UNSET:
            field_dict["min"] = min_
        if missing is not UNSET:
            field_dict["missing"] = missing
        if other_count is not UNSET:
            field_dict["otherCount"] = other_count
        if reason is not UNSET:
            field_dict["reason"] = reason
        if sum_ is not UNSET:
            field_dict["sum"] = sum_
        if value is not UNSET:
            field_dict["value"] = value

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.facet_bucket import FacetBucket

        d = dict(src_dict)
        source = FacetResultSource(d.pop("source"))

        type_ = FacetResultType(d.pop("type"))

        props = d.pop("@props", UNSET)

        after = d.pop("after", UNSET)

        avg = d.pop("avg", UNSET)

        _buckets = d.pop("buckets", UNSET)
        buckets: list[FacetBucket] | Unset = UNSET
        if _buckets is not UNSET:
            buckets = []
            for buckets_item_data in _buckets:
                buckets_item = FacetBucket.from_dict(buckets_item_data)

                buckets.append(buckets_item)

        count = d.pop("count", UNSET)

        exact = d.pop("exact", UNSET)

        max_ = d.pop("max", UNSET)

        min_ = d.pop("min", UNSET)

        missing = d.pop("missing", UNSET)

        other_count = d.pop("otherCount", UNSET)

        reason = d.pop("reason", UNSET)

        sum_ = d.pop("sum", UNSET)

        value = d.pop("value", UNSET)

        facet_result = cls(
            source=source,
            type_=type_,
            props=props,
            after=after,
            avg=avg,
            buckets=buckets,
            count=count,
            exact=exact,
            max_=max_,
            min_=min_,
            missing=missing,
            other_count=other_count,
            reason=reason,
            sum_=sum_,
            value=value,
        )

        facet_result.additional_properties = d
        return facet_result

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
