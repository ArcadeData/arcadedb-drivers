from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.mcp_config_profile import McpConfigProfile
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mcp_config_databases import McpConfigDatabases
    from ..models.mcp_config_principal_profiles import McpConfigPrincipalProfiles


T = TypeVar("T", bound="McpConfig")


@_attrs_define
class McpConfig:
    """MCP server configuration, as GET and POST both answer with it

    Attributes:
        allow_admin (bool): Permit administrative operations
        allow_delete (bool): Permit deletes
        allow_insert (bool): Permit inserts
        allow_reads (bool): Permit read operations
        allow_schema_change (bool): Permit schema changes
        allow_update (bool): Permit updates
        allowed_origins (list[str]): Extra browser origins permitted for the HTTP transport, beyond loopback addresses
            which are always allowed. The value '*' permits any origin, disabling the anti-DNS-rebinding check.
        allowed_users (list[str]): Users permitted to reach the MCP server. The value '*' permits any authenticated
            user.
        enabled (bool): Whether the MCP server answers requests
        profile (McpConfigProfile): Default tool profile, applied to a principal that 'principalProfiles' does not name
        databases (McpConfigDatabases | Unset): Per-database permission overrides, keyed by database name. Present only
            when at least one override is configured.
        principal_profiles (McpConfigPrincipalProfiles | Unset): Tool profile assigned per principal (user or API token)
            name. Present only when at least one is configured.
    """

    allow_admin: bool
    allow_delete: bool
    allow_insert: bool
    allow_reads: bool
    allow_schema_change: bool
    allow_update: bool
    allowed_origins: list[str]
    allowed_users: list[str]
    enabled: bool
    profile: McpConfigProfile
    databases: McpConfigDatabases | Unset = UNSET
    principal_profiles: McpConfigPrincipalProfiles | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        allow_admin = self.allow_admin

        allow_delete = self.allow_delete

        allow_insert = self.allow_insert

        allow_reads = self.allow_reads

        allow_schema_change = self.allow_schema_change

        allow_update = self.allow_update

        allowed_origins = self.allowed_origins

        allowed_users = self.allowed_users

        enabled = self.enabled

        profile = self.profile.value

        databases: dict[str, Any] | Unset = UNSET
        if not isinstance(self.databases, Unset):
            databases = self.databases.to_dict()

        principal_profiles: dict[str, Any] | Unset = UNSET
        if not isinstance(self.principal_profiles, Unset):
            principal_profiles = self.principal_profiles.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "allowAdmin": allow_admin,
                "allowDelete": allow_delete,
                "allowInsert": allow_insert,
                "allowReads": allow_reads,
                "allowSchemaChange": allow_schema_change,
                "allowUpdate": allow_update,
                "allowedOrigins": allowed_origins,
                "allowedUsers": allowed_users,
                "enabled": enabled,
                "profile": profile,
            }
        )
        if databases is not UNSET:
            field_dict["databases"] = databases
        if principal_profiles is not UNSET:
            field_dict["principalProfiles"] = principal_profiles

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mcp_config_databases import McpConfigDatabases
        from ..models.mcp_config_principal_profiles import McpConfigPrincipalProfiles

        d = dict(src_dict)
        allow_admin = d.pop("allowAdmin")

        allow_delete = d.pop("allowDelete")

        allow_insert = d.pop("allowInsert")

        allow_reads = d.pop("allowReads")

        allow_schema_change = d.pop("allowSchemaChange")

        allow_update = d.pop("allowUpdate")

        allowed_origins = cast(list[str], d.pop("allowedOrigins"))

        allowed_users = cast(list[str], d.pop("allowedUsers"))

        enabled = d.pop("enabled")

        profile = McpConfigProfile(d.pop("profile"))

        _databases = d.pop("databases", UNSET)
        databases: McpConfigDatabases | Unset
        if isinstance(_databases, Unset):
            databases = UNSET
        else:
            databases = McpConfigDatabases.from_dict(_databases)

        _principal_profiles = d.pop("principalProfiles", UNSET)
        principal_profiles: McpConfigPrincipalProfiles | Unset
        if isinstance(_principal_profiles, Unset):
            principal_profiles = UNSET
        else:
            principal_profiles = McpConfigPrincipalProfiles.from_dict(_principal_profiles)

        mcp_config = cls(
            allow_admin=allow_admin,
            allow_delete=allow_delete,
            allow_insert=allow_insert,
            allow_reads=allow_reads,
            allow_schema_change=allow_schema_change,
            allow_update=allow_update,
            allowed_origins=allowed_origins,
            allowed_users=allowed_users,
            enabled=enabled,
            profile=profile,
            databases=databases,
            principal_profiles=principal_profiles,
        )

        mcp_config.additional_properties = d
        return mcp_config

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
