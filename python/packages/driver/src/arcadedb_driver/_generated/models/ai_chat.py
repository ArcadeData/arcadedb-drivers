from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ai_chat_messages_item import AiChatMessagesItem


T = TypeVar("T", bound="AiChat")


@_attrs_define
class AiChat:
    """One chat transcript. GET /api/v1/ai/chats returns this shape without 'messages'; GET /api/v1/ai/chats/{id} returns
    it in full.

        Attributes:
            created (str): ISO-8601 instant the chat was created
            database (str): Database this chat is about
            id (str): Chat identifier
            title (str): Chat title, generated from the first user message
            updated (str): ISO-8601 instant of the last change
            messages (list[AiChatMessagesItem] | Unset): Messages, oldest first. Omitted from the /chats list response.
    """

    created: str
    database: str
    id: str
    title: str
    updated: str
    messages: list[AiChatMessagesItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created = self.created

        database = self.database

        id = self.id

        title = self.title

        updated = self.updated

        messages: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.messages, Unset):
            messages = []
            for messages_item_data in self.messages:
                messages_item = messages_item_data.to_dict()
                messages.append(messages_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "created": created,
                "database": database,
                "id": id,
                "title": title,
                "updated": updated,
            }
        )
        if messages is not UNSET:
            field_dict["messages"] = messages

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ai_chat_messages_item import AiChatMessagesItem

        d = dict(src_dict)
        created = d.pop("created")

        database = d.pop("database")

        id = d.pop("id")

        title = d.pop("title")

        updated = d.pop("updated")

        _messages = d.pop("messages", UNSET)
        messages: list[AiChatMessagesItem] | Unset = UNSET
        if _messages is not UNSET:
            messages = []
            for messages_item_data in _messages:
                messages_item = AiChatMessagesItem.from_dict(messages_item_data)

                messages.append(messages_item)

        ai_chat = cls(
            created=created,
            database=database,
            id=id,
            title=title,
            updated=updated,
            messages=messages,
        )

        ai_chat.additional_properties = d
        return ai_chat

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
