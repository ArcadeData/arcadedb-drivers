from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.ai_chat_stream_event_type import AiChatStreamEventType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ai_chat_stream_event_args import AiChatStreamEventArgs
    from ..models.ai_command import AiCommand


T = TypeVar("T", bound="AiChatStreamEvent")


@_attrs_define
class AiChatStreamEvent:
    """One event of the chat stream. 'type' says which one; the other members below belong to the kinds their descriptions
    name, and an event carries only its own.

        Attributes:
            type_ (AiChatStreamEventType): Which event this is. 'tool_start' and 'tool_end' bracket one tool the server ran
                locally, and 'done' terminates a complete stream. The gateway's own 'session' and 'tool_call' events never
                appear: the server consumes both and synthesizes the pair above in their place. Any OTHER value is an event the
                gateway added and this server relays unchanged - ignore what you do not recognise rather than failing on it.
            args (AiChatStreamEventArgs | Unset): Arguments the assistant passed to the tool, echoed identically on
                'tool_start' and 'tool_end'. An open map: the keys are the tool's own parameters.
            chat_id (str | Unset): Chat this exchange belongs to, on 'done'. Added by this server, not by the gateway, and
                the chat is persisted before this event is written - so a client that has seen it can read the chat back
                immediately.
            commands (list[AiCommand] | Unset): SQL commands the assistant proposes, on 'done'. Absent or empty when it
                proposes none
            error (str | Unset): Why the tool failed, on 'tool_end' only, and only when it did. Its absence is what says the
                run succeeded - the stream does not carry the tool's result, which goes back to the gateway rather than to the
                caller.
            response (str | Unset): The assistant's reply, on 'done'. The same value POST /api/v1/ai/chat returns under this
                name
            tool (str | Unset): Name of the tool being run, on 'tool_start' and 'tool_end'. The same name appears on both,
                which is how a consumer pairs them
    """

    type_: AiChatStreamEventType
    args: AiChatStreamEventArgs | Unset = UNSET
    chat_id: str | Unset = UNSET
    commands: list[AiCommand] | Unset = UNSET
    error: str | Unset = UNSET
    response: str | Unset = UNSET
    tool: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_.value

        args: dict[str, Any] | Unset = UNSET
        if not isinstance(self.args, Unset):
            args = self.args.to_dict()

        chat_id = self.chat_id

        commands: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.commands, Unset):
            commands = []
            for commands_item_data in self.commands:
                commands_item = commands_item_data.to_dict()
                commands.append(commands_item)

        error = self.error

        response = self.response

        tool = self.tool

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
            }
        )
        if args is not UNSET:
            field_dict["args"] = args
        if chat_id is not UNSET:
            field_dict["chatId"] = chat_id
        if commands is not UNSET:
            field_dict["commands"] = commands
        if error is not UNSET:
            field_dict["error"] = error
        if response is not UNSET:
            field_dict["response"] = response
        if tool is not UNSET:
            field_dict["tool"] = tool

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ai_chat_stream_event_args import AiChatStreamEventArgs
        from ..models.ai_command import AiCommand

        d = dict(src_dict)
        type_ = AiChatStreamEventType(d.pop("type"))

        _args = d.pop("args", UNSET)
        args: AiChatStreamEventArgs | Unset
        if isinstance(_args, Unset):
            args = UNSET
        else:
            args = AiChatStreamEventArgs.from_dict(_args)

        chat_id = d.pop("chatId", UNSET)

        _commands = d.pop("commands", UNSET)
        commands: list[AiCommand] | Unset = UNSET
        if _commands is not UNSET:
            commands = []
            for commands_item_data in _commands:
                commands_item = AiCommand.from_dict(commands_item_data)

                commands.append(commands_item)

        error = d.pop("error", UNSET)

        response = d.pop("response", UNSET)

        tool = d.pop("tool", UNSET)

        ai_chat_stream_event = cls(
            type_=type_,
            args=args,
            chat_id=chat_id,
            commands=commands,
            error=error,
            response=response,
            tool=tool,
        )

        ai_chat_stream_event.additional_properties = d
        return ai_chat_stream_event

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
