# Tanseek AI v2 — Evaluation & Release Gate Evidence

This file satisfies the AI release gate: dataset split, baseline
comparison, metric, known limitations, model/version log, and a working
non-AI fallback. Nothing here changes the solver or the API.

## 1. Dataset split (documented)

This service is deterministic constraint optimization (OR-Tools CP-SAT),
not machine learning: there are **no learned parameters**, so there is
nothing to train. The evaluation protocol is therefore:

| Split | Content | Used for |
|---|---|---|
| Fixture | `Tanseek_CSV_Data/` (27 tables, Fall 2027 term, 12 sections, 32 students, 128 ACTIVE enrollments) | Solving (`POST /solve`) |
| Held-out validation | `constraint_test_cases.csv` (12 proposals, never used to build the schedule) | `POST /validate-proposal` checks |
| Readiness suite | `tests/test_readiness.py` (synthetic corruptions of a data copy) | `GET /terms/{id}/readiness` checks |

The 12 constraint cases are independent of the scheduled result: each is
evaluated with the proposed section's own rows ignored (re-scheduling
semantics), so a case cannot leak the solution.

Run: `python -m pytest tests -q` (31 tests).

## 2. Baseline comparison

Reference method: first-feasible greedy assignment
(`scripts/eval_baseline.py`) — same hard checker
(`check_candidate_strict`), same candidate-level scoring scale,
fixed order, no lookahead, no compactness/room optimization.

| Metric | Greedy baseline | CP-SAT (`POST /solve`) |
|---|---|---|
| Sessions | 12 | 12 |
| Scheduled | 12 | 12 |
| Unscheduled | 0 | 0 |
| Candidate-level score | 292 | 300 |
| Compactness bonus | 0 (not optimized) | 60 (4 adjacent pairs × 15) |
| Room penalty | not optimized | 40 (4 active rooms × 10) |
| Final objective | — | 320 |
| Runtime | ~3.4 s | ~7 s |

Reproduce: `python scripts/eval_baseline.py`, then `POST /solve`
with `{"term_id": 1}`.

Reading: on this fixture both methods place everything (the fixture is
deliberately feasible), but CP-SAT wins on quality (+8 candidate points
plus compactness/room terms it alone optimizes). The gap is expected to
widen on tighter data (full rooms, sparse availability).

## 3. Metric

Primary: `scheduled` (maximize), `unscheduled` (must be 0 on valid data).
Quality: `final_objective_value = candidate_score + compactness_bonus
- room_penalty - unscheduled_penalty` (320 on the fixture).
Returned by every `/solve` call in `summary` + `objective_breakdown`.

## 4. Known limitations

- `/solve` takes ~7 s (CP-SAT, 2 workers); the free Render tier sleeps
  after 15 min idle, so the first request can take ~1 min.
- Room assignment may vary between runs at equal objective values.
- `GROUP_CONFLICT` is only a fallback when a section has no enrollment
  data; incomplete terms should be rejected by readiness instead.
- The fixture is synthetic Fall-2027 data, not real operations data.
- No authentication/RBAC in this service (belongs to the Node backend).

## 5. Model/version log

| Component | Version |
|---|---|
| Service | 2.0.0 (`app/main.py`) |
| Solver | Google OR-Tools CP-SAT 9.15.6755 (pip) |
| Python | 3.13.5 (also works on 3.11) |
| pandas | 2.3.2 |
| FastAPI | 0.115.0 |
| Data model | v2 (`Tanseek_PostgreSQL_Schema_v2.sql`) |
| Fixture result | OPTIMAL, 12/12 scheduled, objective 320 |

## 6. Working non-AI fallback

If the solver cannot place sessions (or is unavailable), the backend can
still operate without AI:

1. **Manual placement**: `POST /validate-proposal` checks any
   (section, instructor, room, slot, date) against all hard constraints
   without running the optimizer.
2. **Published baseline**: the PUBLISHED schedule version is immutable;
   `POST /validate-change` gates single edits against it.
3. **Explicit diagnostics**: anything unscheduled comes back with
   `reason_codes` + `diagnostic_counts` (e.g. `CAPACITY_SHORTAGE`),
   so operators know exactly what to fix (add room, split section…).

Covered by `tests/test_constraints.py`, `tests/test_solver.py`
(`test_published_schedule_is_immutable`) and the notebook (59 cells).
