"""Solver and published-schedule tests."""

from app.engine import (
    evaluate_published_change_request,
    published_snapshot,
    verify_published_immutable,
)
from app.solver import solve_schedule


def test_solver_schedules_all_valid_sections():
    result = solve_schedule(
        term_id=1, max_time_seconds=10, num_workers=2
    )
    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert result["summary"]["solver_sessions"] == 12
    assert result["summary"]["scheduled"] == 12
    assert result["summary"]["unscheduled"] == 0
    assert result["unscheduled_sessions"] == []


def test_published_schedule_is_immutable():
    before = published_snapshot.copy(deep=True).reset_index(drop=True)

    solve_schedule(term_id=1, max_time_seconds=10, num_workers=2)

    change = evaluate_published_change_request(
        allocation_id=1, session_date="2027-09-25"
    )
    assert change["status"] in ("FEASIBLE", "BLOCKED")

    assert verify_published_immutable() is True
    after = published_snapshot.copy(deep=True).reset_index(drop=True)
    assert before.equals(after)
