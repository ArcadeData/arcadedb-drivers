from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RunningQuery")


@_attrs_define
class RunningQuery:
    """A statement this server is running

    Attributes:
        database (str): Database the statement runs against
        elapsed_ms (int): How long it has been running, in milliseconds
        id (str): Id to pass to 'terminate query'
        language (str): Query language
        protocol (str): Protocol it arrived on, such as 'http'
        server (str): Name of the server running it
        started_at (int): When it started, in milliseconds since the epoch
        terminating (bool): True once a terminate asked it to stop
        text (str): Statement text
        user (str): User that sent it
        client_address (str | Unset): Address of the client, where known
        connection_id (str | Unset): Connection it arrived on, where the protocol has one
        forwarded_from (str | Unset): Id it has on the server that forwarded it here
        forwarded_to (str | Unset): Server this one forwarded it to
        session_id (str | Unset): Transaction session it runs in. Absent outside one
        tag (str | Unset): Label from the X-ArcadeDB-Query-Tag request header. Absent without one
        terminated_by (str | Unset): User that asked it to stop. Absent until one did
    """

    database: str
    elapsed_ms: int
    id: str
    language: str
    protocol: str
    server: str
    started_at: int
    terminating: bool
    text: str
    user: str
    client_address: str | Unset = UNSET
    connection_id: str | Unset = UNSET
    forwarded_from: str | Unset = UNSET
    forwarded_to: str | Unset = UNSET
    session_id: str | Unset = UNSET
    tag: str | Unset = UNSET
    terminated_by: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database = self.database

        elapsed_ms = self.elapsed_ms

        id = self.id

        language = self.language

        protocol = self.protocol

        server = self.server

        started_at = self.started_at

        terminating = self.terminating

        text = self.text

        user = self.user

        client_address = self.client_address

        connection_id = self.connection_id

        forwarded_from = self.forwarded_from

        forwarded_to = self.forwarded_to

        session_id = self.session_id

        tag = self.tag

        terminated_by = self.terminated_by

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "database": database,
                "elapsedMs": elapsed_ms,
                "id": id,
                "language": language,
                "protocol": protocol,
                "server": server,
                "startedAt": started_at,
                "terminating": terminating,
                "text": text,
                "user": user,
            }
        )
        if client_address is not UNSET:
            field_dict["clientAddress"] = client_address
        if connection_id is not UNSET:
            field_dict["connectionId"] = connection_id
        if forwarded_from is not UNSET:
            field_dict["forwardedFrom"] = forwarded_from
        if forwarded_to is not UNSET:
            field_dict["forwardedTo"] = forwarded_to
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id
        if tag is not UNSET:
            field_dict["tag"] = tag
        if terminated_by is not UNSET:
            field_dict["terminatedBy"] = terminated_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        database = d.pop("database")

        elapsed_ms = d.pop("elapsedMs")

        id = d.pop("id")

        language = d.pop("language")

        protocol = d.pop("protocol")

        server = d.pop("server")

        started_at = d.pop("startedAt")

        terminating = d.pop("terminating")

        text = d.pop("text")

        user = d.pop("user")

        client_address = d.pop("clientAddress", UNSET)

        connection_id = d.pop("connectionId", UNSET)

        forwarded_from = d.pop("forwardedFrom", UNSET)

        forwarded_to = d.pop("forwardedTo", UNSET)

        session_id = d.pop("sessionId", UNSET)

        tag = d.pop("tag", UNSET)

        terminated_by = d.pop("terminatedBy", UNSET)

        running_query = cls(
            database=database,
            elapsed_ms=elapsed_ms,
            id=id,
            language=language,
            protocol=protocol,
            server=server,
            started_at=started_at,
            terminating=terminating,
            text=text,
            user=user,
            client_address=client_address,
            connection_id=connection_id,
            forwarded_from=forwarded_from,
            forwarded_to=forwarded_to,
            session_id=session_id,
            tag=tag,
            terminated_by=terminated_by,
        )

        running_query.additional_properties = d
        return running_query

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
