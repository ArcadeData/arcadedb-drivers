from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ProgressResponseResultItem")


@_attrs_define
class ProgressResponseResultItem:
    """One in-progress operation

    Attributes:
        database (str): Database the operation runs on
        done (int): Units completed in the current step
        elapsed_ms (int): Elapsed time in milliseconds
        id (int): Operation identifier
        operation (str): Operation name, for example CHECK DATABASE
        percentage (int): Completion percentage of the current step, -1 when the total is unknown
        started_on (int): Start time as epoch milliseconds
        step_index (int): Current step, 0-based
        step_name (str): Current step name
        total (int): Units in the current step, -1 when unknown
        total_steps (int): Total number of steps
    """

    database: str
    done: int
    elapsed_ms: int
    id: int
    operation: str
    percentage: int
    started_on: int
    step_index: int
    step_name: str
    total: int
    total_steps: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database = self.database

        done = self.done

        elapsed_ms = self.elapsed_ms

        id = self.id

        operation = self.operation

        percentage = self.percentage

        started_on = self.started_on

        step_index = self.step_index

        step_name = self.step_name

        total = self.total

        total_steps = self.total_steps

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "database": database,
                "done": done,
                "elapsedMs": elapsed_ms,
                "id": id,
                "operation": operation,
                "percentage": percentage,
                "startedOn": started_on,
                "stepIndex": step_index,
                "stepName": step_name,
                "total": total,
                "totalSteps": total_steps,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        database = d.pop("database")

        done = d.pop("done")

        elapsed_ms = d.pop("elapsedMs")

        id = d.pop("id")

        operation = d.pop("operation")

        percentage = d.pop("percentage")

        started_on = d.pop("startedOn")

        step_index = d.pop("stepIndex")

        step_name = d.pop("stepName")

        total = d.pop("total")

        total_steps = d.pop("totalSteps")

        progress_response_result_item = cls(
            database=database,
            done=done,
            elapsed_ms=elapsed_ms,
            id=id,
            operation=operation,
            percentage=percentage,
            started_on=started_on,
            step_index=step_index,
            step_name=step_name,
            total=total,
            total_steps=total_steps,
        )

        progress_response_result_item.additional_properties = d
        return progress_response_result_item

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
