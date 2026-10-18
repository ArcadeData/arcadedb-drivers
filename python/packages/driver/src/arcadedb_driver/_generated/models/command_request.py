from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.command_request_params import CommandRequestParams


T = TypeVar("T", bound="CommandRequest")


@_attrs_define
class CommandRequest:
    """Command request object

    Attributes:
        command (str): Command to execute
        language (str): Command language Example: sql.
        limit (int | Unset): Maximum number of rows to serialize into the response. When omitted, a LIMIT stated by the
            query is honored as written and only a query stating none is capped by the server default
            ('arcadedb.server.httpQueryDefaultLimit'). Use -1 for no cap. The response always reports the cap that was
            applied ('limit'), how many rows it carries ('returned') and whether rows were left behind ('truncated'). No
            value here can widen a single response past the server's hard ceiling
            ('arcadedb.server.httpQueryMaxResultRows'): a result that would exceed it is refused with 413 instead of being
            truncated. Example: 100.
        params (CommandRequestParams | Unset): Command parameters. Values may be JSON primitives, arrays, or typed-
            marker objects: {"$bytes": "<base64>"} for byte[] (standard or URL-safe base64), {"$int8": [v0, v1, ...]} for
            byte[] from integers in [-128, 127] (used to send INT8-encoded vectors to LSM_VECTOR indexes without a float32
            round-trip).
        wait (int | Unset): Server commands only (POST /api/v1/server): how long 'terminate query', 'terminate queries
            tag' and 'terminate transaction' wait for the work to end before answering, in milliseconds. 5000 when absent,
            at most 10000. Work still running when it is over is answered 'terminating'. Example: 1000.
    """

    command: str
    language: str
    limit: int | Unset = UNSET
    params: CommandRequestParams | Unset = UNSET
    wait: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        command = self.command

        language = self.language

        limit = self.limit

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        wait = self.wait

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "command": command,
                "language": language,
            }
        )
        if limit is not UNSET:
            field_dict["limit"] = limit
        if params is not UNSET:
            field_dict["params"] = params
        if wait is not UNSET:
            field_dict["wait"] = wait

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.command_request_params import CommandRequestParams

        d = dict(src_dict)
        command = d.pop("command")

        language = d.pop("language")

        limit = d.pop("limit", UNSET)

        _params = d.pop("params", UNSET)
        params: CommandRequestParams | Unset
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = CommandRequestParams.from_dict(_params)

        wait = d.pop("wait", UNSET)

        command_request = cls(
            command=command,
            language=language,
            limit=limit,
            params=params,
            wait=wait,
        )

        command_request.additional_properties = d
        return command_request

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
