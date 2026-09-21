# Tanseek AI Service v2 — Backend Contract

Base URL (local development): `http://127.0.0.1:8003`

v2 runs on port **8003** so it can run beside the v1 fixture (port 8002).

## Health
`GET /health`

## Ready
`GET /ready`

Returns loaded fixture counts and confirms the solver module can see the data.

## Term readiness
`GET /terms/{term_id}/readiness`

Validates the term before solving:

- every offered course has exactly one LECTURE and one PRACTICAL requirement
- every REGISTERED student has exactly one ACTIVE LECTURE and one ACTIVE
  PRACTICAL enrollment, pointing at a matching section of the same
  course and term
- every ACTIVE section has a valid requirement, a matching kind, at least
  one instructor and a positive `max_capacity`

Response:

```json
{
  "term_id": 1,
  "ready": true,
  "errors": []
}
```

Error items use codes such as `MISSING_LECTURE_REQUIREMENT`,
`MISSING_PRACTICAL_ENROLLMENT`,
`DUPLICATE_ACTIVE_COMPONENT_ENROLLMENT`,
`ENROLLMENT_SECTION_MISMATCH`, `SECTION_REQUIREMENT_MISMATCH`,
`SECTION_WITHOUT_INSTRUCTOR`, `INVALID_SECTION_CAPACITY`.

## Solve timetable
`POST /solve`

Request:
```json
{"term_id": 1}
```

Runs readiness validation first. If the term is not ready, returns
**HTTP 422** with the structured readiness errors and CP-SAT never runs:

```json
{
  "detail": {
    "term_id": 1,
    "ready": false,
    "errors": [{"code": "MISSING_PRACTICAL_ENROLLMENT", "...": "..."}]
  }
}
```

On success (`FEASIBLE` or `OPTIMAL`):

```json
{
  "term_id": 1,
  "solver_status": "OPTIMAL",
  "summary": {
    "solver_sessions": 12,
    "candidate_count": 82,
    "scheduled": 12,
    "unscheduled": 0
  },
  "objective_breakdown": {},
  "soft_score_definitions": {},
  "scheduled_sessions": [],
  "unscheduled_sessions": []
}
```

Solver mode is FRESH: the published v2 baseline stays immutable for change
validation, but the solver schedules every section from scratch (the v2
fixture ships only a PUBLISHED version, no DRAFT).

## Validate proposal (main endpoint)
`POST /validate-proposal`

The section already carries its `requirement_id`, so the client sends no
`requirement_id`. The service derives term, course, requirement, kind,
weekday and times from the Section and Time Slot.

Request:
```json
{
  "section_id": 2,
  "instructor_id": 12,
  "room_id": 3,
  "slot_id": 3,
  "event_date": "2027-09-25"
}
```

Feasible response:
```json
{"feasible": true, "primary_result": "FEASIBLE", "reasons": [], "slot_id": 3}
```

Blocked response example:
```json
{"feasible": false, "primary_result": "ROOM_CONFLICT", "reasons": ["ROOM_CONFLICT"], "slot_id": 1}
```

## Validate allocation (DEPRECATED)
`POST /validate-allocation` — **deprecated**, kept only for compatibility.
Use `POST /validate-proposal` instead. A mismatched legacy
`requirement_id` is rejected with `INVALID_REFERENCE`.

## Validate a change to a published schedule
`POST /validate-change`

Request:
```json
{
  "allocation_id": 1,
  "session_date": "2027-09-25",
  "proposed_room_id": null,
  "proposed_instructor_id": null,
  "proposed_start_slot_id": null
}
```

Unlike v1, the v2 fixture ships a PUBLISHED version, so change validation
runs against the immutable published snapshot instead of returning
`NO_PUBLISHED_VERSION`.

## v2 hard-constraint codes

`INVALID_SLOT`, `HOLIDAY`, `ROOM_CLOSED`, `INVALID_DURATION`,
`AVAILABILITY_NOT_CONFIRMED`, `INSTRUCTOR_UNAVAILABLE`, `ROOM_CONFLICT`,
`INSTRUCTOR_CONFLICT`, `STUDENT_CONFLICT`, `GROUP_CONFLICT`,
`ROOM_TYPE_MISMATCH`, `CAPACITY_SHORTAGE`, `EQUIPMENT_SHORTAGE`,
`INELIGIBLE_INSTRUCTOR`, `INVALID_REFERENCE`

Student conflicts come from individual ACTIVE
`student_section_enrollments`. Groups are only a bulk-assignment fallback
when a section has no enrollment data, so no false `GROUP_CONFLICT`
occurs for sections whose students do not overlap. Capacity uses unique
ACTIVE enrollment counts.

## How the backend should call the service

1. `GET /terms/{term_id}/readiness` — proceed only when `ready` is true.
2. `POST /solve` with `{"term_id": N}` — persist `scheduled_sessions`;
   surface `unscheduled_sessions` with their diagnostic reasons.
3. `POST /validate-proposal` for single-placement checks from the UI.
4. `POST /validate-change` for edits against a published version.

## Data Source Integration

The solver/constraint logic is live on the v2 `Tanseek_CSV_Data` fixture
(27 tables including `students`, `student_section_enrollments`,
`term_holidays`, `room_closures`).

The code reads data through the `SchedulingDataRepository` interface
(`CsvSchedulingDataRepository` for local testing). Replacing it with a
Postgres-backed repository is the next data-source integration step and
should not require changing the response contract.
