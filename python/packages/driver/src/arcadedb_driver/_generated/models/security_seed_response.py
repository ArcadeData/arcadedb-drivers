from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SecuritySeedResponse")


@_attrs_define
class SecuritySeedResponse:
    """What the leader did about the request

    Attributes:
        seeded (bool): True when the documents were submitted to the cluster
        error (str | Unset): Why the seed could not be run or its outcome could not be read. Present only on the 503
            that carries no failedSeeds, since in that case which documents failed is exactly what is not known.
        failed_seeds (list[str] | Unset): The documents that did not commit, empty when all of them did
        up_to_date (bool | Unset): True when the caller's fingerprints already matched the leader's and nothing was
            submitted
    """

    seeded: bool
    error: str | Unset = UNSET
    failed_seeds: list[str] | Unset = UNSET
    up_to_date: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        seeded = self.seeded

        error = self.error

        failed_seeds: list[str] | Unset = UNSET
        if not isinstance(self.failed_seeds, Unset):
            failed_seeds = self.failed_seeds

        up_to_date = self.up_to_date

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "seeded": seeded,
            }
        )
        if error is not UNSET:
            field_dict["error"] = error
        if failed_seeds is not UNSET:
            field_dict["failedSeeds"] = failed_seeds
        if up_to_date is not UNSET:
            field_dict["upToDate"] = up_to_date

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        seeded = d.pop("seeded")

        error = d.pop("error", UNSET)

        failed_seeds = cast(list[str], d.pop("failedSeeds", UNSET))

        up_to_date = d.pop("upToDate", UNSET)

        security_seed_response = cls(
            seeded=seeded,
            error=error,
            failed_seeds=failed_seeds,
            up_to_date=up_to_date,
        )

        security_seed_response.additional_properties = d
        return security_seed_response

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
