from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.ai_chat import AiChat


T = TypeVar("T", bound="AiChatList")


@_attrs_define
class AiChatList:
    """Stored chats

    Attributes:
        chats (list[AiChat]): Stored chat transcripts, metadata only (no 'messages'). Empty when this user has stored
            none
    """

    chats: list[AiChat]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        chats = []
        for chats_item_data in self.chats:
            chats_item = chats_item_data.to_dict()
            chats.append(chats_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "chats": chats,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ai_chat import AiChat

        d = dict(src_dict)
        chats = []
        _chats = d.pop("chats")
        for chats_item_data in _chats:
            chats_item = AiChat.from_dict(chats_item_data)

            chats.append(chats_item)

        ai_chat_list = cls(
            chats=chats,
        )

        ai_chat_list.additional_properties = d
        return ai_chat_list

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
