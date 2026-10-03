from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ClusterStatusSecurityConvergence")


@_attrs_define
class ClusterStatusSecurityConvergence:
    """What the security-convergence readiness gate sees on this node. Present on every answer. The three security
    documents (users, groups, API tokens) do not travel in the Raft snapshot and reach a new peer only through the
    admission seed, so a member that is caught up can still hold none of the cluster's copies. While 'held',
    '/api/v1/ready' answers 503 until the leader confirms them. The wait is bounded by
    arcadedb.ha.securityConvergenceReadinessTimeout: past it the node reports READY while enforcing its own copies
    ('gaveUp'). Not a resync, so 'localResync' does not reflect it; the 'security-documents-unconverged' alert does.
    Reading this document counts as observing the node: it evaluates the same shared window as the readiness probe, so
    the first read that finds the node otherwise ready opens the window, exactly as a probe would.

        Attributes:
            armed (bool): True for a runtime joiner (a node added to a running cluster), false for a statically configured
                member held after a snapshot install
            gave_up (bool): True once the window expired unconverged: the node is READY and serving traffic while enforcing
                its own copies of the documents, which may hold a user dropped, a group narrowed or a token revoked while it was
                away
            held (bool): True while '/api/v1/ready' is answering 503 because of this gate
            since_index (int): The Raft log index of the join or of the snapshot install the window is keyed by, 0 when
                there is none
            skipped_because_leading (bool): True while this node leads: nobody can confirm a leader's documents, so it is
                not held for them. It is held again with a full window if it steps down while still unconfirmed
            unconverged_documents (list[str]): The documents the cluster has not confirmed on this node, in the order users,
                groups, API tokens. Empty when converged or when the gate does not apply (no HA layer, or readiness that does
                not require HA)
            window_opened_at (int): When the current window opened, as epoch milliseconds, 0 while none is open
    """

    armed: bool
    gave_up: bool
    held: bool
    since_index: int
    skipped_because_leading: bool
    unconverged_documents: list[str]
    window_opened_at: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        armed = self.armed

        gave_up = self.gave_up

        held = self.held

        since_index = self.since_index

        skipped_because_leading = self.skipped_because_leading

        unconverged_documents = self.unconverged_documents

        window_opened_at = self.window_opened_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "armed": armed,
                "gaveUp": gave_up,
                "held": held,
                "sinceIndex": since_index,
                "skippedBecauseLeading": skipped_because_leading,
                "unconvergedDocuments": unconverged_documents,
                "windowOpenedAt": window_opened_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        armed = d.pop("armed")

        gave_up = d.pop("gaveUp")

        held = d.pop("held")

        since_index = d.pop("sinceIndex")

        skipped_because_leading = d.pop("skippedBecauseLeading")

        unconverged_documents = cast(list[str], d.pop("unconvergedDocuments"))

        window_opened_at = d.pop("windowOpenedAt")

        cluster_status_security_convergence = cls(
            armed=armed,
            gave_up=gave_up,
            held=held,
            since_index=since_index,
            skipped_because_leading=skipped_because_leading,
            unconverged_documents=unconverged_documents,
            window_opened_at=window_opened_at,
        )

        cluster_status_security_convergence.additional_properties = d
        return cluster_status_security_convergence

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
