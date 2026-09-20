from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AddPeerRequest")


@_attrs_define
class AddPeerRequest:
    """Peer to add

    Attributes:
        address (str): Peer address
        peer_id (str): Peer identifier
        name (str | Unset): Optional display name
        priority (int | None | Unset): Raft leader-election priority, a non-negative integer. Defaults to 0, which is
            Ratis's own default and leaves the peer as electable as every other peer on a cluster where nobody names a
            priority. Once ANY peer carries a positive priority the priority-0 ones become witnesses that are never elected
            and are skipped as step-down targets, so 0 is how a witness is declared and a higher value how a preferred
            leader is. A fractional value or one that does not fit in a 32-bit integer is refused rather than rounded,
            because the value it would round to declares a witness. The same field the 'priority' of an
            arcadedb.ha.serverList entry sets. Default: 0.
    """

    address: str
    peer_id: str
    name: str | Unset = UNSET
    priority: int | Unset | None = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        address = self.address

        peer_id = self.peer_id

        name = self.name

        priority: int | Unset | None
        if isinstance(self.priority, Unset):
            priority = UNSET
        else:
            priority = self.priority

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "address": address,
                "peerId": peer_id,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if priority is not UNSET:
            field_dict["priority"] = priority

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        address = d.pop("address")

        peer_id = d.pop("peerId")

        name = d.pop("name", UNSET)

        def _parse_priority(data: object) -> int | Unset | None:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        priority = _parse_priority(d.pop("priority", UNSET))

        add_peer_request = cls(
            address=address,
            peer_id=peer_id,
            name=name,
            priority=priority,
        )

        add_peer_request.additional_properties = d
        return add_peer_request

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
