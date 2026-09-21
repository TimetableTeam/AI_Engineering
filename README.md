# Tanseek AI Scheduling Service (v2)

Student-aware Python/FastAPI scheduling component for Tanseek v2.

## What is live

- Term readiness validation (every course has LECTURE + PRACTICAL
  requirements; every REGISTERED student has one ACTIVE LECTURE and one
  ACTIVE PRACTICAL enrollment; sections are bound, instructed and sized).
- Deterministic hard-constraint validation (v2 codes).
- CP-SAT timetable optimization using Google OR-Tools.
- Individual student conflict detection via `student_section_enrollments`
  (authoritative; groups are only a bulk-assignment fallback when a
  section has no enrollment data).
- Capacity-fit scoring from unique ACTIVE enrollment counts.
- Staff preference, equipment-match, compactness and room-utilization scoring.
- Explicit UNSCHEDULED output with diagnostic reasons.
- Ranked feasible alternatives for scheduled sessions.
- Published-schedule change validation against the immutable PUBLISHED snapshot.

## Current Data Source

The v2 service uses the sample data in:

`Tanseek_CSV_Data/` (27 tables)

Plus at the folder root:

- `constraint_test_cases.csv` — 12 proposals with expected outcomes
- `Tanseek_Data_v2.xlsx` — all sample tables in one workbook
- `Tanseek_ERD_v2.md` — data model
- `Tanseek_PostgreSQL_Schema_v2.sql` — PostgreSQL baseline

Local testing loads CSVs through `CsvSchedulingDataRepository`
(`app/engine.py`). The solver only depends on the
`SchedulingDataRepository` interface, so the backend can later plug in a
`PostgresSchedulingDataRepository` without touching solver logic.
No authentication, RBAC or student-login logic lives in this service;
those belong to the Node/PostgreSQL backend.

The folder must be placed beside the `app/` directory.

## Run the service

```
python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

- Swagger: `http://127.0.0.1:8003/docs`
- Health: `http://127.0.0.1:8003/health`
- Ready: `http://127.0.0.1:8003/ready`
- Term readiness: `http://127.0.0.1:8003/terms/1/readiness`

## Run the tests

```
python -m pytest tests -q
```

Covers term readiness, all hard constraints, all 12
`constraint_test_cases.csv` cases, full-schedule solving and published
immutability.

## Solver mode

FRESH: the v2 fixture ships only a PUBLISHED version, so the solver
schedules every section from scratch. The published baseline stays
immutable for `POST /validate-change`.

`POST /solve` first runs term readiness validation. If the term is not
ready it returns HTTP 422 with structured errors and CP-SAT never runs.

## Current project layout

```text
Tanseek_Menna_Model_v2_Starter/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── engine.py
│   └── solver.py
│
├── tests/
│   ├── conftest.py
│   ├── test_readiness.py
│   ├── test_constraints.py
│   └── test_solver.py
│
├── Tanseek_CSV_Data/   (27 CSV files)
├── constraint_test_cases.csv
├── Tanseek_Data_v2.xlsx
├── Tanseek_ERD_v2.md
├── Tanseek_PostgreSQL_Schema_v2.sql
├── Tanseek_Menna_Model_v2_Starter.ipynb
├── tanseek_solver_output.json   (optional example output only)
├── API_CONTRACT.md
├── requirements.txt
└── README.md
```
