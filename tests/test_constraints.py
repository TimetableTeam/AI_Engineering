"""Hard-constraint tests through POST /validate-proposal logic."""

import csv
from pathlib import Path

import pandas as pd
import pytest

from app.engine import check_allocation, validate_proposal

ROOT = Path(__file__).resolve().parent.parent


def propose(section_id, instructor_id, room_id, slot_id, event_date):
    return validate_proposal(
        section_id, instructor_id, room_id, slot_id, event_date
    )


def test_valid_proposal():
    result = propose(2, 12, 3, 3, "2027-09-25")
    assert result["feasible"] is True
    assert result["primary_result"] == "FEASIBLE"
    assert result["reasons"] == []


def _section5_proposal_existing():
    # Published allocations without section 5, plus a synthetic
    # overlapping row for section 2 with a neutral instructor/room
    # so only the student dimension can fire.
    from app.engine import allocations

    existing = allocations[
        allocations["section_id"].astype(int) != 5
    ].copy()
    extra = pd.DataFrame(
        [
            {
                "term_id": 1,
                "section_id": 2,
                "requirement_id": 2,
                "instructor_id": 99,
                "room_id": 99,
                "weekday": 7,
                "starts_at": "11:00",
                "ends_at": "13:00",
            }
        ]
    )
    return pd.concat([existing, extra], ignore_index=True)


def _section5_sunday_proposal(existing):
    return check_allocation(
        term_id=1,
        section_id=5,
        requirement_id=4,
        instructor_id=12,
        room_id=5,
        weekday=7,
        starts_at="11:00",
        ends_at="13:00",
        existing=existing,
    )


def test_student_conflict():
    result = propose(4, 9, 2, 1, "2027-09-25")
    assert result["feasible"] is False
    assert result["primary_result"] == "STUDENT_CONFLICT"


def test_student_conflict_authoritative():
    # Sections 2 and 5 share group 1 AND students 1..8:
    # the conflict must come from enrollments.
    result = _section5_sunday_proposal(_section5_proposal_existing())
    assert result["primary_result"] == "STUDENT_CONFLICT"
    assert "GROUP_CONFLICT" not in result["reasons"]


def test_no_false_group_conflict(monkeypatch):
    # Same setup, but section 5 holds disjoint students while still
    # sharing group 1 with section 2: neither STUDENT_CONFLICT nor
    # the GROUP_CONFLICT fallback may fire.
    import app.engine as engine_module

    patched = {
        section: set(students)
        for section, students in engine_module.students_by_section_ids.items()
    }
    patched[5] = {101, 102, 103, 104, 105, 106, 107, 108}
    monkeypatch.setattr(
        engine_module, "students_by_section_ids", patched
    )
    result = _section5_sunday_proposal(_section5_proposal_existing())
    assert "STUDENT_CONFLICT" not in result["reasons"]
    assert "GROUP_CONFLICT" not in result["reasons"]
    assert result["primary_result"] == "FEASIBLE"


def test_room_conflict():
    result = propose(4, 9, 1, 1, "2027-09-25")
    assert result["primary_result"] == "ROOM_CONFLICT"


def test_instructor_conflict():
    result = propose(5, 8, 5, 1, "2027-09-25")
    assert result["primary_result"] == "INSTRUCTOR_CONFLICT"


def test_room_type_mismatch():
    result = propose(5, 12, 1, 6, "2027-09-26")
    assert result["primary_result"] == "ROOM_TYPE_MISMATCH"


def test_capacity_shortage():
    result = propose(1, 8, 7, 1, "2027-09-25")
    assert result["primary_result"] == "CAPACITY_SHORTAGE"


def test_equipment_shortage():
    result = propose(11, 14, 8, 14, "2027-09-28")
    assert result["feasible"] is False
    assert result["primary_result"] == "EQUIPMENT_SHORTAGE"
    assert result["reasons"] == ["EQUIPMENT_SHORTAGE"]


def test_instructor_unavailable():
    result = propose(1, 8, 1, 9, "2027-09-27")
    assert result["primary_result"] == "INSTRUCTOR_UNAVAILABLE"


def test_room_closed():
    result = propose(8, 14, 3, 10, "2027-11-15")
    assert result["primary_result"] == "ROOM_CLOSED"


def test_holiday():
    result = propose(7, 10, 1, 17, "2027-10-06")
    assert result["primary_result"] == "HOLIDAY"


def test_invalid_slot():
    result = propose(2, 12, 3, 999, "2027-09-25")
    assert result["primary_result"] == "INVALID_SLOT"


def test_all_csv_constraint_cases():
    cases_path = ROOT / "constraint_test_cases.csv"
    failures = []
    with open(cases_path, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            result = propose(
                int(row["section_id"]),
                int(row["instructor_id"]),
                int(row["room_id"]),
                int(row["slot_id"]),
                row["event_date"],
            )
            expected = row["expected_violation"]
            ok = (expected == "NONE" and result["feasible"]) or (
                expected in result["reasons"]
            )
            if not ok:
                failures.append((row["test_case_id"], expected, result))
    assert not failures, failures
    assert sum(1 for _ in open(cases_path, encoding="utf-8-sig")) - 1 == 12
