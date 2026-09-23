"""Greedy baseline for EVAL comparison (non-optimal reference).

Assigns each weekly session the first feasible candidate in a fixed
order (eligible instructor, slot, room). Uses the same hard-constraint
checker as the service (app.engine.check_candidate_strict) and mirrors
the candidate-level soft-score formula from app.solver so the quality
gap with CP-SAT is measured on the same scale.

Read-only: never modifies data or the published schedule.
"""

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import (
    TERM_ID,
    availability,
    available,
    check_candidate_strict,
    eligible,
    required,
    rooms,
    slots,
    solver_existing_allocations,
    students_by_section,
    submission_by_staff,
)
from app.solver import build_weekly_sessions


def candidate_total_score(
    requirement_id, section_id, room_id, availability_kind
):
    staff = 30 if availability_kind == "PREFERRED" else 0

    students = int(students_by_section.get(section_id, 0))
    capacity = int(rooms[room_id]["capacity"])
    pct = round(students / capacity * 100) if capacity else 0
    pct = max(0, min(pct, 100))
    cap_score = round(25 * pct / 100)

    items = [
        (eid, qty)
        for (rid, eid), qty in required.items()
        if int(rid) == int(requirement_id)
    ]
    if not items:
        eq_pct = 100
    else:
        ratios = []
        for eid, need in items:
            have = int(available.get((int(room_id), int(eid)), 0))
            ratios.append(0 if have <= 0 else min(need / have, 1.0))
        eq_pct = round(sum(ratios) / len(ratios) * 100)
    eq_score = round(20 * eq_pct / 100)

    return staff + cap_score + eq_score


def run_baseline(term_id=None):
    term_id = TERM_ID if term_id is None else int(term_id)
    sessions = build_weekly_sessions()
    sessions = sessions[sessions["term_id"].astype(int) == term_id]
    placed = solver_existing_allocations.iloc[0:0].copy()
    chosen, unscheduled = [], []
    total = 0
    started = time.perf_counter()

    for session in sessions.itertuples(index=False):
        section_id = int(session.section_id)
        requirement_id = int(session.requirement_id)
        instructors = sorted(
            i
            for (s, r, i) in eligible
            if s == section_id and r == requirement_id
        )
        done = False
        for instructor_id in instructors:
            submission = submission_by_staff.get(
                (term_id, instructor_id)
            )
            for slot_id in sorted(slots):
                slot = slots[slot_id]
                if int(slot["term_id"]) != term_id:
                    continue
                for room_id in sorted(rooms):
                    result = check_candidate_strict(
                        term_id=term_id,
                        section_id=section_id,
                        requirement_id=requirement_id,
                        instructor_id=instructor_id,
                        room_id=room_id,
                        weekday=int(slot["weekday"]),
                        starts_at=slot["starts_at"],
                        ends_at=slot["ends_at"],
                        existing=placed,
                    )
                    if result["primary_result"] != "FEASIBLE":
                        continue
                    kind = (
                        availability.get(
                            (int(submission.id), int(slot_id)),
                            "UNKNOWN",
                        )
                        if submission is not None
                        else "UNKNOWN"
                    )
                    score = candidate_total_score(
                        requirement_id, section_id, room_id, kind
                    )
                    total += score
                    chosen.append(
                        {
                            "session_key": session.session_key,
                            "section_id": section_id,
                            "instructor_id": instructor_id,
                            "room_id": int(room_id),
                            "slot_id": int(slot_id),
                            "score": score,
                        }
                    )
                    placed = pd.concat(
                        [
                            placed,
                            pd.DataFrame(
                                [
                                    {
                                        "term_id": term_id,
                                        "section_id": section_id,
                                        "requirement_id": requirement_id,
                                        "instructor_id": instructor_id,
                                        "room_id": int(room_id),
                                        "weekday": int(slot["weekday"]),
                                        "starts_at": slot["starts_at"],
                                        "ends_at": slot["ends_at"],
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )
                    done = True
                    break
                if done:
                    break
            if done:
                break
        if not done:
            unscheduled.append(session.session_key)

    elapsed = time.perf_counter() - started
    return {
        "sessions": len(sessions),
        "scheduled": len(chosen),
        "unscheduled": len(unscheduled),
        "unscheduled_keys": unscheduled,
        "candidate_total_score": total,
        "seconds": round(elapsed, 2),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_baseline(), indent=2))
