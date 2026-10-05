from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ai_config_portal import AiConfigPortal


T = TypeVar("T", bound="AiConfig")


@_attrs_define
class AiConfig:
    """AI assistant configuration

    Attributes:
        configured (bool): True when the assistant can answer: a connected portal whose plan includes it, or an
            activated gateway key
        current_protocol_version (int): Protocol version this server prefers
        gateway_url (str): AI gateway endpoint
        supported_protocol_versions (list[int]): Every version this server accepts
        portal (AiConfigPortal | Unset): The state of the customer portal connection: connected, enabled, tier, turns,
            spent, budget (billed dollars this month), percent, resetsOn, portalUrl, upgradeUrl and, when the plan could not
            be read, code and message. Never carries the key
        source (str | Unset): Where the answers come from: 'portal' (this server is connected to the customer portal and
            the plan includes the assistant), 'gateway' (a legacy subscription key) or 'none'. Absent on a server without
            the portal client
    """

    configured: bool
    current_protocol_version: int
    gateway_url: str
    supported_protocol_versions: list[int]
    portal: AiConfigPortal | Unset = UNSET
    source: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        configured = self.configured

        current_protocol_version = self.current_protocol_version

        gateway_url = self.gateway_url

        supported_protocol_versions = self.supported_protocol_versions

        portal: dict[str, Any] | Unset = UNSET
        if not isinstance(self.portal, Unset):
            portal = self.portal.to_dict()

        source = self.source

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "configured": configured,
                "currentProtocolVersion": current_protocol_version,
                "gatewayUrl": gateway_url,
                "supportedProtocolVersions": supported_protocol_versions,
            }
        )
        if portal is not UNSET:
            field_dict["portal"] = portal
        if source is not UNSET:
            field_dict["source"] = source

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ai_config_portal import AiConfigPortal

        d = dict(src_dict)
        configured = d.pop("configured")

        current_protocol_version = d.pop("currentProtocolVersion")

        gateway_url = d.pop("gatewayUrl")

        supported_protocol_versions = cast(list[int], d.pop("supportedProtocolVersions"))

        _portal = d.pop("portal", UNSET)
        portal: AiConfigPortal | Unset
        if isinstance(_portal, Unset):
            portal = UNSET
        else:
            portal = AiConfigPortal.from_dict(_portal)

        source = d.pop("source", UNSET)

        ai_config = cls(
            configured=configured,
            current_protocol_version=current_protocol_version,
            gateway_url=gateway_url,
            supported_protocol_versions=supported_protocol_versions,
            portal=portal,
            source=source,
        )

        ai_config.additional_properties = d
        return ai_config

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
