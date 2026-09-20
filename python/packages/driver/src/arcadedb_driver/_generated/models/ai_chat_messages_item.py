from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.ai_chat_messages_item_role import AiChatMessagesItemRole
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ai_command import AiCommand


T = TypeVar("T", bound="AiChatMessagesItem")


@_attrs_define
class AiChatMessagesItem:
    """One chat message

    Attributes:
        content (str): Message text
        role (AiChatMessagesItemRole): Who wrote the message
        timestamp (str): ISO-8601 instant
        commands (list[AiCommand] | Unset): SQL commands the assistant proposed with this reply. Present only on an
            assistant message that proposed at least one.
    """

    content: str
    role: AiChatMessagesItemRole
    timestamp: str
    commands: list[AiCommand] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        content = self.content

        role = self.role.value

        timestamp = self.timestamp

        commands: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.commands, Unset):
            commands = []
            for commands_item_data in self.commands:
                commands_item = commands_item_data.to_dict()
                commands.append(commands_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "content": content,
                "role": role,
                "timestamp": timestamp,
            }
        )
        if commands is not UNSET:
            field_dict["commands"] = commands

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ai_command import AiCommand

        d = dict(src_dict)
        content = d.pop("content")

        role = AiChatMessagesItemRole(d.pop("role"))

        timestamp = d.pop("timestamp")

        _commands = d.pop("commands", UNSET)
        commands: list[AiCommand] | Unset = UNSET
        if _commands is not UNSET:
            commands = []
            for commands_item_data in _commands:
                commands_item = AiCommand.from_dict(commands_item_data)

                commands.append(commands_item)

        ai_chat_messages_item = cls(
            content=content,
            role=role,
            timestamp=timestamp,
            commands=commands,
        )

        ai_chat_messages_item.additional_properties = d
        return ai_chat_messages_item

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
