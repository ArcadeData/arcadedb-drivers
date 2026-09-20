from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ai_command import AiCommand
    from ..models.ai_tool_call import AiToolCall


T = TypeVar("T", bound="AiChatResponse")


@_attrs_define
class AiChatResponse:
    """Assistant reply

    Attributes:
        chat_id (str): Chat this exchange belongs to, for continuing the conversation
        response (str): Assistant message
        commands (list[AiCommand] | Unset): SQL commands the assistant proposes. Absent when it proposes none.
        tool_calls (list[AiToolCall] | Unset): Tools the assistant invoked while answering. Absent when it invoked none.
    """

    chat_id: str
    response: str
    commands: list[AiCommand] | Unset = UNSET
    tool_calls: list[AiToolCall] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        chat_id = self.chat_id

        response = self.response

        commands: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.commands, Unset):
            commands = []
            for commands_item_data in self.commands:
                commands_item = commands_item_data.to_dict()
                commands.append(commands_item)

        tool_calls: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.tool_calls, Unset):
            tool_calls = []
            for tool_calls_item_data in self.tool_calls:
                tool_calls_item = tool_calls_item_data.to_dict()
                tool_calls.append(tool_calls_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "chatId": chat_id,
                "response": response,
            }
        )
        if commands is not UNSET:
            field_dict["commands"] = commands
        if tool_calls is not UNSET:
            field_dict["toolCalls"] = tool_calls

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ai_command import AiCommand
        from ..models.ai_tool_call import AiToolCall

        d = dict(src_dict)
        chat_id = d.pop("chatId")

        response = d.pop("response")

        _commands = d.pop("commands", UNSET)
        commands: list[AiCommand] | Unset = UNSET
        if _commands is not UNSET:
            commands = []
            for commands_item_data in _commands:
                commands_item = AiCommand.from_dict(commands_item_data)

                commands.append(commands_item)

        _tool_calls = d.pop("toolCalls", UNSET)
        tool_calls: list[AiToolCall] | Unset = UNSET
        if _tool_calls is not UNSET:
            tool_calls = []
            for tool_calls_item_data in _tool_calls:
                tool_calls_item = AiToolCall.from_dict(tool_calls_item_data)

                tool_calls.append(tool_calls_item)

        ai_chat_response = cls(
            chat_id=chat_id,
            response=response,
            commands=commands,
            tool_calls=tool_calls,
        )

        ai_chat_response.additional_properties = d
        return ai_chat_response

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
