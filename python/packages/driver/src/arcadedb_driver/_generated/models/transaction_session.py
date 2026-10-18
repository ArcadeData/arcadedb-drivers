from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TransactionSession")


@_attrs_define
class TransactionSession:
    """An open transaction session

    Attributes:
        busy (bool): True while a request runs in it
        database (str): Database of its transaction
        id (str): Session id, to pass to 'terminate transaction'
        idle_ms (int): Milliseconds since it was last used
        running_queries (list[str]): Ids of the statements running in it
        server (str): Name of the server holding it
        user (str): User that opened it
        tag (str | Unset): Label it was opened with. Absent without one
    """

    busy: bool
    database: str
    id: str
    idle_ms: int
    running_queries: list[str]
    server: str
    user: str
    tag: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        busy = self.busy

        database = self.database

        id = self.id

        idle_ms = self.idle_ms

        running_queries = self.running_queries

        server = self.server

        user = self.user

        tag = self.tag

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "busy": busy,
                "database": database,
                "id": id,
                "idleMs": idle_ms,
                "runningQueries": running_queries,
                "server": server,
                "user": user,
            }
        )
        if tag is not UNSET:
            field_dict["tag"] = tag

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        busy = d.pop("busy")

        database = d.pop("database")

        id = d.pop("id")

        idle_ms = d.pop("idleMs")

        running_queries = cast(list[str], d.pop("runningQueries"))

        server = d.pop("server")

        user = d.pop("user")

        tag = d.pop("tag", UNSET)

        transaction_session = cls(
            busy=busy,
            database=database,
            id=id,
            idle_ms=idle_ms,
            running_queries=running_queries,
            server=server,
            user=user,
            tag=tag,
        )

        transaction_session.additional_properties = d
        return transaction_session

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
