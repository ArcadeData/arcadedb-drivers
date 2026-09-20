from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.server_info_ha import ServerInfoHa
    from ..models.server_info_metrics import ServerInfoMetrics
    from ..models.server_info_settings_item import ServerInfoSettingsItem


T = TypeVar("T", bound="ServerInfo")


@_attrs_define
class ServerInfo:
    """Server information. The first four members are on every answer; which of the rest appear is decided by the 'mode'
    query parameter.

        Attributes:
            languages (list[str]): Query languages this build can run, e.g. sql, sqlscript, cypher, gremlin
            server_name (str): This server's configured name
            user (None | str): The authenticated caller. Null on a request that carried no principal
            version (str): Server version
            ha (ServerInfoHa | Unset): Cluster topology and per-database replication state. Present with mode=cluster only,
                and only when this server runs an HA implementation. The per-database rows are scoped to the caller's authorized
                databases; the topology members are not.

                Its 'securityRefresh' member says whether the replicated group changes THIS node received have been enforced
                here, not merely received: entriesApplied, refreshesRequested, refreshesCoalesced, sweepsCompleted,
                sweepsFailed, databasesRefreshed, databaseRefreshFailures, and the epoch-millisecond lastEntryAppliedAt /
                lastSweepAt. entriesApplied rising while sweepsCompleted does not is a node enforcing permissions it has already
                been told to replace; the same numbers are scrapable as the arcadedb.ha.security.* meters.
            metrics (ServerInfoMetrics | Unset): Profiler counters, request meters, executor pools and sparse-vector index
                statistics. Present with mode=default only. An open map: the counter set follows the build and the plugins
                loaded.
            settings (list[ServerInfoSettingsItem] | Unset): Every server setting with its current and default value.
                Present with mode=default only. A setting marked hidden reports '*****' for both, and so does any setting whose
                key contains 'password'.
    """

    languages: list[str]
    server_name: str
    user: str | None
    version: str
    ha: ServerInfoHa | Unset = UNSET
    metrics: ServerInfoMetrics | Unset = UNSET
    settings: list[ServerInfoSettingsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        languages = self.languages

        server_name = self.server_name

        user: str | None
        user = self.user

        version = self.version

        ha: dict[str, Any] | Unset = UNSET
        if not isinstance(self.ha, Unset):
            ha = self.ha.to_dict()

        metrics: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metrics, Unset):
            metrics = self.metrics.to_dict()

        settings: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.settings, Unset):
            settings = []
            for settings_item_data in self.settings:
                settings_item = settings_item_data.to_dict()
                settings.append(settings_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "languages": languages,
                "serverName": server_name,
                "user": user,
                "version": version,
            }
        )
        if ha is not UNSET:
            field_dict["ha"] = ha
        if metrics is not UNSET:
            field_dict["metrics"] = metrics
        if settings is not UNSET:
            field_dict["settings"] = settings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.server_info_ha import ServerInfoHa
        from ..models.server_info_metrics import ServerInfoMetrics
        from ..models.server_info_settings_item import ServerInfoSettingsItem

        d = dict(src_dict)
        languages = cast(list[str], d.pop("languages"))

        server_name = d.pop("serverName")

        def _parse_user(data: object) -> str | None:
            if data is None:
                return data
            return cast(None | str, data)

        user = _parse_user(d.pop("user"))

        version = d.pop("version")

        _ha = d.pop("ha", UNSET)
        ha: ServerInfoHa | Unset
        if isinstance(_ha, Unset):
            ha = UNSET
        else:
            ha = ServerInfoHa.from_dict(_ha)

        _metrics = d.pop("metrics", UNSET)
        metrics: ServerInfoMetrics | Unset
        if isinstance(_metrics, Unset):
            metrics = UNSET
        else:
            metrics = ServerInfoMetrics.from_dict(_metrics)

        _settings = d.pop("settings", UNSET)
        settings: list[ServerInfoSettingsItem] | Unset = UNSET
        if _settings is not UNSET:
            settings = []
            for settings_item_data in _settings:
                settings_item = ServerInfoSettingsItem.from_dict(settings_item_data)

                settings.append(settings_item)

        server_info = cls(
            languages=languages,
            server_name=server_name,
            user=user,
            version=version,
            ha=ha,
            metrics=metrics,
            settings=settings,
        )

        server_info.additional_properties = d
        return server_info

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
