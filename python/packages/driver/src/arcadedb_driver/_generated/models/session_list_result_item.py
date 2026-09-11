from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SessionListResultItem")


@_attrs_define
class SessionListResultItem:
    """One active session

    Attributes:
        city (str | Unset): City reported by the proxy, when available
        country (str | Unset): Country reported by the proxy, when available
        created_at (int | Unset): Creation time as epoch milliseconds
        elapsed_ms (int | Unset): Milliseconds since last use
        issuer (str | Unset): Name of the cluster node that issued the session, when this node holds a copy of it;
            absent for a session this node issued
        last_update (int | Unset): Last use as epoch milliseconds
        source_ip (str | Unset): Client address
        token (str | Unset): Session token
        user (str | Unset): User the session belongs to
        user_agent (str | Unset): Client user agent
    """

    city: str | Unset = UNSET
    country: str | Unset = UNSET
    created_at: int | Unset = UNSET
    elapsed_ms: int | Unset = UNSET
    issuer: str | Unset = UNSET
    last_update: int | Unset = UNSET
    source_ip: str | Unset = UNSET
    token: str | Unset = UNSET
    user: str | Unset = UNSET
    user_agent: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        city = self.city

        country = self.country

        created_at = self.created_at

        elapsed_ms = self.elapsed_ms

        issuer = self.issuer

        last_update = self.last_update

        source_ip = self.source_ip

        token = self.token

        user = self.user

        user_agent = self.user_agent

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if city is not UNSET:
            field_dict["city"] = city
        if country is not UNSET:
            field_dict["country"] = country
        if created_at is not UNSET:
            field_dict["createdAt"] = created_at
        if elapsed_ms is not UNSET:
            field_dict["elapsedMs"] = elapsed_ms
        if issuer is not UNSET:
            field_dict["issuer"] = issuer
        if last_update is not UNSET:
            field_dict["lastUpdate"] = last_update
        if source_ip is not UNSET:
            field_dict["sourceIp"] = source_ip
        if token is not UNSET:
            field_dict["token"] = token
        if user is not UNSET:
            field_dict["user"] = user
        if user_agent is not UNSET:
            field_dict["userAgent"] = user_agent

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        city = d.pop("city", UNSET)

        country = d.pop("country", UNSET)

        created_at = d.pop("createdAt", UNSET)

        elapsed_ms = d.pop("elapsedMs", UNSET)

        issuer = d.pop("issuer", UNSET)

        last_update = d.pop("lastUpdate", UNSET)

        source_ip = d.pop("sourceIp", UNSET)

        token = d.pop("token", UNSET)

        user = d.pop("user", UNSET)

        user_agent = d.pop("userAgent", UNSET)

        session_list_result_item = cls(
            city=city,
            country=country,
            created_at=created_at,
            elapsed_ms=elapsed_ms,
            issuer=issuer,
            last_update=last_update,
            source_ip=source_ip,
            token=token,
            user=user,
            user_agent=user_agent,
        )

        session_list_result_item.additional_properties = d
        return session_list_result_item

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
