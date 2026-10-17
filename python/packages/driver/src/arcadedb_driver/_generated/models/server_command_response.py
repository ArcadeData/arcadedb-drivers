from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.running_query import RunningQuery
    from ..models.server_command_response_result_type_6 import ServerCommandResponseResultType6
    from ..models.termination_status import TerminationStatus
    from ..models.transaction_session import TransactionSession


T = TypeVar("T", bound="ServerCommandResponse")


@_attrs_define
class ServerCommandResponse:
    """Answer of a server command

    Attributes:
        result (list[RunningQuery] | list[str] | list[TerminationStatus] | list[TransactionSession] |
            ServerCommandResponseResultType6 | str | TerminationStatus): What the command answered. "ok" for the commands
            that only act; the names of the databases for 'list databases'; RunningQuery rows for 'list queries';
            TransactionSession rows for 'list transactions'; one TerminationStatus for 'terminate query' and 'terminate
            transaction'; an array of them for 'terminate queries tag'; an object for the commands that report one, such as
            'get server events'.
    """

    result: (
        list[RunningQuery]
        | list[str]
        | list[TerminationStatus]
        | list[TransactionSession]
        | ServerCommandResponseResultType6
        | str
        | TerminationStatus
    )
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.server_command_response_result_type_6 import ServerCommandResponseResultType6
        from ..models.termination_status import TerminationStatus

        result: dict[str, Any] | list[dict[str, Any]] | list[str] | str
        if isinstance(self.result, list):
            result = self.result

        elif isinstance(self.result, list):
            result = []
            for result_type_2_item_data in self.result:
                result_type_2_item = result_type_2_item_data.to_dict()
                result.append(result_type_2_item)

        elif isinstance(self.result, list):
            result = []
            for result_type_3_item_data in self.result:
                result_type_3_item = result_type_3_item_data.to_dict()
                result.append(result_type_3_item)

        elif isinstance(self.result, TerminationStatus):
            result = self.result.to_dict()
        elif isinstance(self.result, list):
            result = []
            for result_type_5_item_data in self.result:
                result_type_5_item = result_type_5_item_data.to_dict()
                result.append(result_type_5_item)

        elif isinstance(self.result, ServerCommandResponseResultType6):
            result = self.result.to_dict()
        else:
            result = self.result

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.running_query import RunningQuery
        from ..models.server_command_response_result_type_6 import ServerCommandResponseResultType6
        from ..models.termination_status import TerminationStatus
        from ..models.transaction_session import TransactionSession

        d = dict(src_dict)

        def _parse_result(
            data: object,
        ) -> (
            list[RunningQuery]
            | list[str]
            | list[TerminationStatus]
            | list[TransactionSession]
            | ServerCommandResponseResultType6
            | str
            | TerminationStatus
        ):
            try:
                if not isinstance(data, list):
                    raise TypeError()
                result_type_1 = cast(list[str], data)

                return result_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                result_type_2 = []
                _result_type_2 = data
                for result_type_2_item_data in _result_type_2:
                    result_type_2_item = RunningQuery.from_dict(result_type_2_item_data)

                    result_type_2.append(result_type_2_item)

                return result_type_2
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                result_type_3 = []
                _result_type_3 = data
                for result_type_3_item_data in _result_type_3:
                    result_type_3_item = TransactionSession.from_dict(result_type_3_item_data)

                    result_type_3.append(result_type_3_item)

                return result_type_3
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                result_type_4 = TerminationStatus.from_dict(data)

                return result_type_4
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                result_type_5 = []
                _result_type_5 = data
                for result_type_5_item_data in _result_type_5:
                    result_type_5_item = TerminationStatus.from_dict(result_type_5_item_data)

                    result_type_5.append(result_type_5_item)

                return result_type_5
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                result_type_6 = ServerCommandResponseResultType6.from_dict(data)

                return result_type_6
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[RunningQuery]
                | list[str]
                | list[TerminationStatus]
                | list[TransactionSession]
                | ServerCommandResponseResultType6
                | str
                | TerminationStatus,
                data,
            )

        result = _parse_result(d.pop("result"))

        server_command_response = cls(
            result=result,
        )

        server_command_response.additional_properties = d
        return server_command_response

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
