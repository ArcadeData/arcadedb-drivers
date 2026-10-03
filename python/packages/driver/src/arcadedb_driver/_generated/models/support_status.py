from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.support_status_log_time_zone import SupportStatusLogTimeZone
    from ..models.support_status_plan import SupportStatusPlan
    from ..models.support_status_portal_error import SupportStatusPortalError
    from ..models.support_status_sla import SupportStatusSla


T = TypeVar("T", bound="SupportStatus")


@_attrs_define
class SupportStatus:
    """The registration of this server with the support portal

    Attributes:
        can_write_config (bool): Whether the configuration directory accepts the registration file
        portal_url (str): The portal URL in use
        registered (bool): Whether a Client ID and key are configured
        client_id (str | Unset): The Client ID (workspace id)
        from_settings (bool | Unset): The registration comes from the settings, not from support.json
        instance_id (str | Unset): The instance id of this server
        key_hint (str | Unset): The last four characters of the key, prefixed by an ellipsis: all that is ever shown
        log_time_zone (SupportStatusLogTimeZone | Unset): The time zone the log timestamps are written in: {id, name,
            offset, note}
        plan (SupportStatusPlan | Unset): {entitled, label, units, endsOn} as the portal reports it
        portal_error (SupportStatusPortalError | Unset): Present when the portal did not answer: {error, message}
        sla (SupportStatusSla | Unset): First-response times {S1, S2, S3, S4, coverage}, or null
        workspace_name (str | Unset): Name of the workspace, from the portal
    """

    can_write_config: bool
    portal_url: str
    registered: bool
    client_id: str | Unset = UNSET
    from_settings: bool | Unset = UNSET
    instance_id: str | Unset = UNSET
    key_hint: str | Unset = UNSET
    log_time_zone: SupportStatusLogTimeZone | Unset = UNSET
    plan: SupportStatusPlan | Unset = UNSET
    portal_error: SupportStatusPortalError | Unset = UNSET
    sla: SupportStatusSla | Unset = UNSET
    workspace_name: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        can_write_config = self.can_write_config

        portal_url = self.portal_url

        registered = self.registered

        client_id = self.client_id

        from_settings = self.from_settings

        instance_id = self.instance_id

        key_hint = self.key_hint

        log_time_zone: dict[str, Any] | Unset = UNSET
        if not isinstance(self.log_time_zone, Unset):
            log_time_zone = self.log_time_zone.to_dict()

        plan: dict[str, Any] | Unset = UNSET
        if not isinstance(self.plan, Unset):
            plan = self.plan.to_dict()

        portal_error: dict[str, Any] | Unset = UNSET
        if not isinstance(self.portal_error, Unset):
            portal_error = self.portal_error.to_dict()

        sla: dict[str, Any] | Unset = UNSET
        if not isinstance(self.sla, Unset):
            sla = self.sla.to_dict()

        workspace_name = self.workspace_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "canWriteConfig": can_write_config,
                "portalUrl": portal_url,
                "registered": registered,
            }
        )
        if client_id is not UNSET:
            field_dict["clientId"] = client_id
        if from_settings is not UNSET:
            field_dict["fromSettings"] = from_settings
        if instance_id is not UNSET:
            field_dict["instanceId"] = instance_id
        if key_hint is not UNSET:
            field_dict["keyHint"] = key_hint
        if log_time_zone is not UNSET:
            field_dict["logTimeZone"] = log_time_zone
        if plan is not UNSET:
            field_dict["plan"] = plan
        if portal_error is not UNSET:
            field_dict["portalError"] = portal_error
        if sla is not UNSET:
            field_dict["sla"] = sla
        if workspace_name is not UNSET:
            field_dict["workspaceName"] = workspace_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.support_status_log_time_zone import SupportStatusLogTimeZone
        from ..models.support_status_plan import SupportStatusPlan
        from ..models.support_status_portal_error import SupportStatusPortalError
        from ..models.support_status_sla import SupportStatusSla

        d = dict(src_dict)
        can_write_config = d.pop("canWriteConfig")

        portal_url = d.pop("portalUrl")

        registered = d.pop("registered")

        client_id = d.pop("clientId", UNSET)

        from_settings = d.pop("fromSettings", UNSET)

        instance_id = d.pop("instanceId", UNSET)

        key_hint = d.pop("keyHint", UNSET)

        _log_time_zone = d.pop("logTimeZone", UNSET)
        log_time_zone: SupportStatusLogTimeZone | Unset
        if isinstance(_log_time_zone, Unset):
            log_time_zone = UNSET
        else:
            log_time_zone = SupportStatusLogTimeZone.from_dict(_log_time_zone)

        _plan = d.pop("plan", UNSET)
        plan: SupportStatusPlan | Unset
        if isinstance(_plan, Unset):
            plan = UNSET
        else:
            plan = SupportStatusPlan.from_dict(_plan)

        _portal_error = d.pop("portalError", UNSET)
        portal_error: SupportStatusPortalError | Unset
        if isinstance(_portal_error, Unset):
            portal_error = UNSET
        else:
            portal_error = SupportStatusPortalError.from_dict(_portal_error)

        _sla = d.pop("sla", UNSET)
        sla: SupportStatusSla | Unset
        if isinstance(_sla, Unset):
            sla = UNSET
        else:
            sla = SupportStatusSla.from_dict(_sla)

        workspace_name = d.pop("workspaceName", UNSET)

        support_status = cls(
            can_write_config=can_write_config,
            portal_url=portal_url,
            registered=registered,
            client_id=client_id,
            from_settings=from_settings,
            instance_id=instance_id,
            key_hint=key_hint,
            log_time_zone=log_time_zone,
            plan=plan,
            portal_error=portal_error,
            sla=sla,
            workspace_name=workspace_name,
        )

        support_status.additional_properties = d
        return support_status

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
