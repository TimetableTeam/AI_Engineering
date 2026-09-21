# Tanseek AI Scheduling Service

This is the Python/FastAPI scheduling component for Tanseek.

## What is live
- Deterministic hard-constraint validation.
- CP-SAT timetable optimization.
- Staff preference scoring.
- Capacity-fit scoring.
- Equipment-match scoring.
- Compactness bonus.
- Active-room utilization penalty.
- Explicit UNSCHEDULED output.
- Published-change validation logic.

## Data source in this handoff
The current service loads the existing synthetic CSV fixture from `Tanseek_CSV_Data` when the process starts. Put that folder beside `app/`.

Expected layout:
```text
Tanseek_Menna_Model_Starter/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── engine.py
│   └── solver.py
├── Tanseek_CSV_Data/
├── requirements.txt
└── run_server.ps1
```

## Install
```powershell
& "C:\Users\engme\anaconda3\Scripts\conda.exe" run --no-capture-output -n tanseek python -m pip install -r requirements.txt
```

## Run
```powershell
& "C:\Users\engme\anaconda3\Scripts\conda.exe" run --no-capture-output -n tanseek python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Swagger: `http://127.0.0.1:8001/docs`

## Smoke test order
1. `GET /health`
2. `GET /ready`
3. `POST /solve` with `{"term_id":1}`
4. `POST /validate-allocation`
5. `POST /validate-change`

Expected current fixture solve: 24 solver sessions, 4191 feasible candidates, 23 scheduled, 1 unscheduled (solver status can be FEASIBLE or OPTIMAL).

## Switch to the backend PostgreSQL database
Copy `.env.example` to `.env` and set:
```env
TANSEEK_DATA_SOURCE=postgres
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
TANSEEK_DB_SCHEMA=public
```
Restart Uvicorn after changing the data source. The public API contract stays the same; only the loader changes from CSV fixtures to PostgreSQL.
