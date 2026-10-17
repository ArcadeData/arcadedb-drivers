from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.termination_status_status import TerminationStatusStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="TerminationStatus")


@_attrs_define
class TerminationStatus:
    """How a terminate ended

    Attributes:
        id (str): Statement id, or session id for 'terminate transaction'
        status (TerminationStatusStatus): 'terminated': it stopped and what it wrote was rolled back. 'completed': it
            ended on its own before it noticed, and what it did stands (statements only). 'terminating': not stopped within
            'wait'. 'not found': no such work, or not the caller's to see.
        session_id (str | Unset): Statements only: the transaction session the statement ran in. Absent outside one
        session_open (bool | Unset): Statements only, with 'sessionId': whether the session is still open. A terminated
            command ends its session, a terminated read leaves it to its client. For 'terminating', only the state when the
            answer was built
    """

    id: str
    status: TerminationStatusStatus
    session_id: str | Unset = UNSET
    session_open: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        status = self.status.value

        session_id = self.session_id

        session_open = self.session_open

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "status": status,
            }
        )
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id
        if session_open is not UNSET:
            field_dict["sessionOpen"] = session_open

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        status = TerminationStatusStatus(d.pop("status"))

        session_id = d.pop("sessionId", UNSET)

        session_open = d.pop("sessionOpen", UNSET)

        termination_status = cls(
            id=id,
            status=status,
            session_id=session_id,
            session_open=session_open,
        )

        termination_status.additional_properties = d
        return termination_status

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
