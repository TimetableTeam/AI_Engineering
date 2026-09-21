from fastapi import FastAPI, HTTPException

from .models import (
    SolveRequest,
    AllocationInput,
    ValidationResponse,
    ChangeRequest,
    ChangeValidationResponse,
)

from .engine import (
    check_allocation,
    evaluate_published_change_request,
)

from .solver import (
    solve_schedule,
    solver_ready,
)


# =================================================
# FastAPI App
# =================================================

app = FastAPI(
    title="Tanseek Scheduling AI Service",
    description=(
        "Constraint-based timetable, room and lab "
        "allocation service for Tanseek."
    ),
    version="1.1.0",
)


# =================================================
# Last Solver Result Cache
# =================================================

LAST_SOLVER_RESULT = None


# =================================================
# Root
# =================================================

@app.get("/")
def root():

    return {
        "service": "Tanseek Scheduling AI Service",
        "status": "running",
        "version": "1.1.0",
        "solver_mode": "LIVE_CP_SAT",
    }


# =================================================
# Health Check
# =================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "tanseek-ai",
        "solver": "live",
    }


# =================================================
# Readiness Check
# =================================================

@app.get("/ready")
def ready():

    try:

        result = solver_ready()

        return {
            "status": "ready",
            "solver": result,
        }

    except Exception as error:

        raise HTTPException(
            status_code=503,
            detail=str(error),
        )


# =================================================
# Run Live Solver
# =================================================

@app.post("/solve")
def solve(request: SolveRequest):

    global LAST_SOLVER_RESULT

    try:

        result = solve_schedule(
            term_id=request.term_id,
            max_time_seconds=30,
            num_workers=2,
        )

        # Put requested term in the API response
        result = {
            "term_id": request.term_id,
            **result,
        }

        LAST_SOLVER_RESULT = result

        return result

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# =================================================
# Helper: Get Last Solver Result
# =================================================

def get_last_solver_result():

    if LAST_SOLVER_RESULT is None:

        raise HTTPException(
            status_code=409,
            detail=(
                "No live solver result is available yet. "
                "Run POST /solve first."
            ),
        )

    return LAST_SOLVER_RESULT


# =================================================
# Solver Summary
# =================================================

@app.get("/solver/summary")
def solver_summary():

    result = get_last_solver_result()

    return {
        "term_id":
            result.get("term_id"),

        "solver_status":
            result.get("solver_status"),

        "summary":
            result.get("summary"),

        "objective_breakdown":
            result.get("objective_breakdown"),

        "soft_score_definitions":
            result.get("soft_score_definitions"),
    }


# =================================================
# Scheduled Sessions
# =================================================

@app.get("/solver/scheduled")
def scheduled_sessions():

    result = get_last_solver_result()

    sessions = result.get(
        "scheduled_sessions",
        [],
    )

    return {
        "term_id":
            result.get("term_id"),

        "count":
            len(sessions),

        "sessions":
            sessions,
    }


# =================================================
# Unscheduled Sessions
# =================================================

@app.get("/solver/unscheduled")
def unscheduled_sessions():

    result = get_last_solver_result()

    sessions = result.get(
        "unscheduled_sessions",
        [],
    )

    return {
        "term_id":
            result.get("term_id"),

        "count":
            len(sessions),

        "sessions":
            sessions,
    }


# =================================================
# Validate Allocation
# =================================================

@app.post(
    "/validate-allocation",
    response_model=ValidationResponse,
)
def validate_allocation(
    request: AllocationInput,
):

    try:

        result = check_allocation(
            term_id=
                request.term_id,

            section_id=
                request.section_id,

            requirement_id=
                request.requirement_id,

            instructor_id=
                request.instructor_id,

            room_id=
                request.room_id,

            weekday=
                request.weekday,

            starts_at=
                request.starts_at,

            ends_at=
                request.ends_at,

            session_date=
                request.session_date,
        )

        return result

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# =================================================
# Validate Published Change Request
# =================================================

@app.post(
    "/validate-change",
    response_model=ChangeValidationResponse,
)
def validate_change(
    request: ChangeRequest,
):

    try:

        result = (
            evaluate_published_change_request(
                allocation_id=
                    request.allocation_id,

                session_date=
                    request.session_date,

                proposed_room_id=
                    request.proposed_room_id,

                proposed_instructor_id=
                    request.proposed_instructor_id,

                proposed_start_slot_id=
                    request.proposed_start_slot_id,
            )
        )

        return result

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )