# Tanseek AI Service — Backend Contract

Base URL (local development): `http://127.0.0.1:8001`

## Health
`GET /health`

## Ready
`GET /ready`

Returns loaded fixture counts and confirms the solver module can see the data.

## Solve timetable
`POST /solve`

Request:
```json
{"term_id": 1}
```

Response shape:
```json
{
  "term_id": 1,
  "solver_status": "FEASIBLE",
  "summary": {
    "solver_sessions": 24,
    "candidate_count": 4191,
    "scheduled": 23,
    "unscheduled": 1
  },
  "objective_breakdown": {},
  "soft_score_definitions": {},
  "scheduled_sessions": [],
  "unscheduled_sessions": []
}
```

`FEASIBLE` and `OPTIMAL` are both valid solver outcomes.

## Validate allocation
`POST /validate-allocation`

Request:
```json
{
  "term_id": 1,
  "section_id": 4,
  "requirement_id": 1,
  "instructor_id": 7,
  "room_id": 3,
  "weekday": 1,
  "starts_at": "11:00:00",
  "ends_at": "13:00:00",
  "session_date": null
}
```

Feasible response:
```json
{"primary_result":"FEASIBLE","reasons":[],"slot_id":10}
```

## Validate a change to a published schedule
`POST /validate-change`

Request:
```json
{
  "allocation_id": 1,
  "session_date": "2027-10-04",
  "proposed_room_id": null,
  "proposed_instructor_id": null,
  "proposed_start_slot_id": null
}
```

Current synthetic data has no PUBLISHED schedule version, so the expected current fixture response is `NO_PUBLISHED_VERSION`.

## Important integration note
The solver/constraint logic is live. This packaged version still loads the current synthetic `Tanseek_CSV_Data` fixture at service startup. The API contract can be integrated now. Replacing the fixture loader with Node/PostgreSQL data is the next data-source integration step and should not require changing the response contract.

## Live PostgreSQL handoff
The service supports two data sources without changing the API contract:
- `TANSEEK_DATA_SOURCE=csv` for the current fixture.
- `TANSEEK_DATA_SOURCE=postgres` with `DATABASE_URL` for the shared backend database.

For backend integration, use PostgreSQL mode and restart the FastAPI process after changing the database configuration.
