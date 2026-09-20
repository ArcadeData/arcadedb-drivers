from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SessionListResultItem")


@_attrs_define
class SessionListResultItem:
    """One active session

    Attributes:
        city (None | str): City reported by the proxy. Null when no proxy reported one
        country (None | str): Country reported by the proxy. Null when no proxy reported one
        created_at (int): Creation time as epoch milliseconds
        elapsed_ms (int): Milliseconds since last use
        last_update (int): Last use as epoch milliseconds
        source_ip (None | str): Client address, as this server saw it
        token (str): Session token
        user (str): User the session belongs to
        user_agent (None | str): Client user agent. Null when the request carried none
        issuer (str | Unset): Name of the cluster node that issued the session, when this node holds a copy of it;
            absent for a session this node issued
    """

    city: str | None
    country: str | None
    created_at: int
    elapsed_ms: int
    last_update: int
    source_ip: str | None
    token: str
    user: str
    user_agent: str | None
    issuer: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        city: str | None
        city = self.city

        country: str | None
        country = self.country

        created_at = self.created_at

        elapsed_ms = self.elapsed_ms

        last_update = self.last_update

        source_ip: str | None
        source_ip = self.source_ip

        token = self.token

        user = self.user

        user_agent: str | None
        user_agent = self.user_agent

        issuer = self.issuer

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "city": city,
                "country": country,
                "createdAt": created_at,
                "elapsedMs": elapsed_ms,
                "lastUpdate": last_update,
                "sourceIp": source_ip,
                "token": token,
                "user": user,
                "userAgent": user_agent,
            }
        )
        if issuer is not UNSET:
            field_dict["issuer"] = issuer

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_city(data: object) -> str | None:
            if data is None:
                return data
            return cast(None | str, data)

        city = _parse_city(d.pop("city"))

        def _parse_country(data: object) -> str | None:
            if data is None:
                return data
            return cast(None | str, data)

        country = _parse_country(d.pop("country"))

        created_at = d.pop("createdAt")

        elapsed_ms = d.pop("elapsedMs")

        last_update = d.pop("lastUpdate")

        def _parse_source_ip(data: object) -> str | None:
            if data is None:
                return data
            return cast(None | str, data)

        source_ip = _parse_source_ip(d.pop("sourceIp"))

        token = d.pop("token")

        user = d.pop("user")

        def _parse_user_agent(data: object) -> str | None:
            if data is None:
                return data
            return cast(None | str, data)

        user_agent = _parse_user_agent(d.pop("userAgent"))

        issuer = d.pop("issuer", UNSET)

        session_list_result_item = cls(
            city=city,
            country=country,
            created_at=created_at,
            elapsed_ms=elapsed_ms,
            last_update=last_update,
            source_ip=source_ip,
            token=token,
            user=user,
            user_agent=user_agent,
            issuer=issuer,
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
