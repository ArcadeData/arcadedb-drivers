from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.security_seed_request_fingerprints import SecuritySeedRequestFingerprints


T = TypeVar("T", bound="SecuritySeedRequest")


@_attrs_define
class SecuritySeedRequest:
    """What the caller wants seeded, and what it already holds

    Attributes:
        catch_up (bool | Unset): True when the caller is a node repairing ITSELF after coming back, false (or absent)
            for a node reporting on an admission it performed. What it changes is REUSE: a catch-up is never answered by a
            seed that completed for somebody else, while an admission may be, since its request follows the membership
            change that already seeded for it. A catch-up can still complete without anything being submitted - that is what
            the fingerprint comparison is for, and it answers upToDate before any seeder is asked.
        fingerprints (SecuritySeedRequestFingerprints | Unset): The caller's own document digests. When all three match
            the leader's, nothing is submitted and the answer is upToDate. Omit them to have every document seeded, which is
            what an admission does - the admitting node does not hold the joining peer's copies.
        reason (str | Unset): Why the seed was asked for, for the leader's log line. Optional.
    """

    catch_up: bool | Unset = UNSET
    fingerprints: SecuritySeedRequestFingerprints | Unset = UNSET
    reason: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        catch_up = self.catch_up

        fingerprints: dict[str, Any] | Unset = UNSET
        if not isinstance(self.fingerprints, Unset):
            fingerprints = self.fingerprints.to_dict()

        reason = self.reason

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if catch_up is not UNSET:
            field_dict["catchUp"] = catch_up
        if fingerprints is not UNSET:
            field_dict["fingerprints"] = fingerprints
        if reason is not UNSET:
            field_dict["reason"] = reason

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.security_seed_request_fingerprints import SecuritySeedRequestFingerprints

        d = dict(src_dict)
        catch_up = d.pop("catchUp", UNSET)

        _fingerprints = d.pop("fingerprints", UNSET)
        fingerprints: SecuritySeedRequestFingerprints | Unset
        if isinstance(_fingerprints, Unset):
            fingerprints = UNSET
        else:
            fingerprints = SecuritySeedRequestFingerprints.from_dict(_fingerprints)

        reason = d.pop("reason", UNSET)

        security_seed_request = cls(
            catch_up=catch_up,
            fingerprints=fingerprints,
            reason=reason,
        )

        security_seed_request.additional_properties = d
        return security_seed_request

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
