from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.verify_database_cluster_result import VerifyDatabaseClusterResult


T = TypeVar("T", bound="VerifyDatabaseClusterResponse")


@_attrs_define
class VerifyDatabaseClusterResponse:
    """A leader's cluster-wide comparison, fanned out to every peer

    Attributes:
        result (VerifyDatabaseClusterResult): Leader-only cluster-wide comparison, fanned out to every peer
    """

    result: VerifyDatabaseClusterResult
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = self.result.to_dict()

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
        from ..models.verify_database_cluster_result import VerifyDatabaseClusterResult

        d = dict(src_dict)
        result = VerifyDatabaseClusterResult.from_dict(d.pop("result"))

        verify_database_cluster_response = cls(
            result=result,
        )

        verify_database_cluster_response.additional_properties = d
        return verify_database_cluster_response

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
