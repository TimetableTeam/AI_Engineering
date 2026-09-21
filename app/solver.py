from collections import defaultdict
import pandas as pd

from ortools.sat.python import cp_model

from .engine import (
    tables,
    sections,
    requirements,
    rooms,
    slots,
    accounts,
    eligible,
    submission_by_staff,
    availability,
    required,
    available,
    students_by_section,
    groups_by_section,
    solver_existing_allocations,
    check_candidate_strict,
)


# =================================================
# Solver Settings
# =================================================

UNSCHEDULED_PENALTY = 100000

COMPACTNESS_POINTS = 15

ROOM_ACTIVE_PENALTY = 10


# =================================================
# Soft Score Definitions
# =================================================

SOFT_SCORE_DEFINITIONS = {

    "STAFF_PREFERENCE": {
        "max_points": 30,
        "scope": "CANDIDATE"
    },

    "CAPACITY_FIT": {
        "max_points": 25,
        "scope": "CANDIDATE"
    },

    "EQUIPMENT_MATCH": {
        "max_points": 20,
        "scope": "CANDIDATE"
    },

    "COMPACTNESS": {
        "points_per_adjacent_pair": 15,
        "scope": "SCHEDULE"
    },

    "ROOM_UTILIZATION": {
        "penalty_per_active_room": 10,
        "scope": "SCHEDULE"
    }
}


# =================================================
# Solver Readiness Check
# =================================================

def solver_ready():

    return {
        "status": "ready",

        "rooms":
            len(rooms),

        "sections":
            len(sections),

        "requirements":
            len(requirements),

        "slots":
            len(slots),

        "existing_allocations":
            len(
                solver_existing_allocations
            )
    }


# =================================================
# Build Weekly Sessions
# =================================================

def build_weekly_sessions():

    rows = []

    section_instructors = (
        tables[
            "section_instructors"
        ].copy()
    )

    session_requirements = (
        tables[
            "session_requirements"
        ].copy()
    )

    sections_df = (
        tables[
            "sections"
        ].copy()
    )


    # ---------------------------------------------
    # Connect:
    # section
    # requirement
    # instructor eligibility
    # ---------------------------------------------

    merged = (
        section_instructors
        .merge(
            session_requirements,

            left_on=
                "requirement_id",

            right_on=
                "id",

            suffixes=(
                "_section_instructor",
                "_requirement"
            )
        )
        .merge(
            sections_df[
                [
                    "id",
                    "term_id",
                    "course_id",
                    "code"
                ]
            ],

            left_on=
                "section_id",

            right_on=
                "id",

            suffixes=(
                "",
                "_section"
            )
        )
    )


    # One row per:
    # section + requirement

    requirement_rows = (
        merged[
            [
                "section_id",
                "requirement_id",
                "term_id",
                "course_id",
                "code",
                "kind",
                "sessions_per_week",
                "duration_minutes",
                "required_room_kind"
            ]
        ]
        .drop_duplicates(
            [
                "section_id",
                "requirement_id"
            ]
        )
    )


    # ---------------------------------------------
    # Create remaining weekly session instances
    # ---------------------------------------------

    for row in requirement_rows.itertuples(
        index=False
    ):

        existing_count = len(

            solver_existing_allocations[

                (
                    solver_existing_allocations[
                        "term_id"
                    ].astype(int)
                    == int(
                        row.term_id
                    )
                )

                &

                (
                    solver_existing_allocations[
                        "section_id"
                    ].astype(int)
                    == int(
                        row.section_id
                    )
                )

                &

                (
                    solver_existing_allocations[
                        "requirement_id"
                    ].astype(int)
                    == int(
                        row.requirement_id
                    )
                )
            ]
        )


        remaining_count = max(

            int(
                row.sessions_per_week
            )
            -
            existing_count,

            0
        )


        for i in range(
            remaining_count
        ):

            instance_number = (
                existing_count
                + i
                + 1
            )


            rows.append({

                "session_key":
                    f"S{int(row.section_id)}"
                    f"_R{int(row.requirement_id)}"
                    f"_W{instance_number}",

                "term_id":
                    int(
                        row.term_id
                    ),

                "section_id":
                    int(
                        row.section_id
                    ),

                "section_code":
                    row.code,

                "requirement_id":
                    int(
                        row.requirement_id
                    ),

                "course_id":
                    int(
                        row.course_id
                    ),

                "kind":
                    row.kind,

                "instance_number":
                    int(
                        instance_number
                    ),

                "duration_minutes":
                    int(
                        row.duration_minutes
                    ),

                "required_room_kind":
                    row.required_room_kind
            })


    return pd.DataFrame(
        rows
    )


# =================================================
# Generate Feasible Candidates
# =================================================

def generate_all_candidates(
    weekly_sessions
):

    candidate_rows = []

    diagnostic_rows = []

    candidate_id = 1


    # ---------------------------------------------
    # Process every weekly session
    # ---------------------------------------------

    for session in weekly_sessions.itertuples(
        index=False
    ):

        term_id = int(
            session.term_id
        )

        section_id = int(
            session.section_id
        )

        requirement_id = int(
            session.requirement_id
        )


        # =========================================
        # Eligible Instructors
        # =========================================

        instructor_ids = sorted({

            instructor_id

            for (
                s,
                r,
                instructor_id
            )
            in eligible

            if (
                s == section_id
                and
                r == requirement_id
            )
        })


        feasible_count = 0

        rejection_reasons = defaultdict(
            int
        )


        # =========================================
        # Instructor Loop
        # =========================================

        for instructor_id in instructor_ids:

            submission = (
                submission_by_staff.get(
                    (
                        term_id,
                        instructor_id
                    )
                )
            )


            # =====================================
            # Slot Loop
            # =====================================

            for slot_id, slot in slots.items():

                if (
                    int(
                        slot[
                            "term_id"
                        ]
                    )
                    != term_id
                ):
                    continue


                # =================================
                # Room Loop
                # =================================

                for room_id, room in rooms.items():

                    # ---------------------------------
                    # Hard Constraint Validation
                    # ---------------------------------

                    result = (
                        check_candidate_strict(

                            term_id=
                                term_id,

                            section_id=
                                section_id,

                            requirement_id=
                                requirement_id,

                            instructor_id=
                                instructor_id,

                            room_id=
                                room_id,

                            weekday=
                                int(
                                    slot[
                                        "weekday"
                                    ]
                                ),

                            starts_at=
                                slot[
                                    "starts_at"
                                ],

                            ends_at=
                                slot[
                                    "ends_at"
                                ],

                            existing=
                                solver_existing_allocations
                        )
                    )


                    # ---------------------------------
                    # Reject infeasible candidate
                    # ---------------------------------

                    if (
                        result[
                            "primary_result"
                        ]
                        != "FEASIBLE"
                    ):

                        for reason in result[
                            "reasons"
                        ]:

                            rejection_reasons[
                                reason
                            ] += 1

                        continue


                    feasible_count += 1


                    # =================================
                    # Availability
                    # =================================

                    availability_kind = (

                        availability.get(
                            (
                                int(
                                    submission.id
                                ),

                                int(
                                    slot_id
                                )
                            ),

                            "UNKNOWN"
                        )

                        if submission
                        is not None

                        else "UNKNOWN"
                    )


                    # =================================
                    # 1) Staff Preference
                    # =================================

                    staff_preference_score = (

                        30

                        if (
                            availability_kind
                            == "PREFERRED"
                        )

                        else 0
                    )


                    # =================================
                    # 2) Capacity Fit
                    # =================================

                    student_count = int(

                        students_by_section.get(
                            section_id,
                            0
                        )
                    )


                    room_capacity = int(
                        room[
                            "capacity"
                        ]
                    )


                    if room_capacity > 0:

                        capacity_fit_pct = round(

                            (
                                student_count
                                /
                                room_capacity
                            )
                            * 100
                        )

                    else:

                        capacity_fit_pct = 0


                    capacity_fit_pct = max(

                        0,

                        min(
                            capacity_fit_pct,
                            100
                        )
                    )


                    capacity_fit_score = round(

                        25
                        *
                        (
                            capacity_fit_pct
                            /
                            100
                        )
                    )


                    # =================================
                    # 3) Equipment Match
                    # =================================

                    required_items = [

                        (
                            equipment_id,
                            required_quantity
                        )

                        for (
                            req_id,
                            equipment_id
                        ),
                        required_quantity
                        in required.items()

                        if (
                            int(
                                req_id
                            )
                            ==
                            requirement_id
                        )
                    ]


                    if not required_items:

                        equipment_fit_pct = 100

                    else:

                        equipment_fit_values = []


                        for (
                            equipment_id,
                            required_quantity
                        ) in required_items:

                            available_quantity = int(

                                available.get(
                                    (
                                        room_id,
                                        equipment_id
                                    ),
                                    0
                                )
                            )


                            if (
                                available_quantity
                                <= 0
                            ):

                                fit_ratio = 0

                            else:

                                fit_ratio = min(

                                    (
                                        required_quantity
                                        /
                                        available_quantity
                                    ),

                                    1
                                )


                            equipment_fit_values.append(
                                fit_ratio
                            )


                        equipment_fit_pct = round(

                            (
                                sum(
                                    equipment_fit_values
                                )
                                /
                                len(
                                    equipment_fit_values
                                )
                            )
                            * 100
                        )


                    equipment_match_score = round(

                        20
                        *
                        (
                            equipment_fit_pct
                            /
                            100
                        )
                    )


                    # =================================
                    # Candidate-Level Score
                    # =================================

                    total_score = (

                        staff_preference_score
                        +
                        capacity_fit_score
                        +
                        equipment_match_score
                    )


                    # =================================
                    # Soft Reason Codes
                    # =================================

                    soft_reason_codes = [
                        "CAPACITY_FIT",
                        "EQUIPMENT_MATCH"
                    ]


                    if (
                        availability_kind
                        == "PREFERRED"
                    ):

                        soft_reason_codes.insert(
                            0,
                            "STAFF_PREFERENCE"
                        )


                    # =================================
                    # Store Candidate
                    # =================================

                    candidate_rows.append({

                        "candidate_id":
                            int(
                                candidate_id
                            ),

                        "session_key":
                            session.session_key,

                        "term_id":
                            term_id,

                        "section_id":
                            section_id,

                        "section_code":
                            session.section_code,

                        "requirement_id":
                            requirement_id,

                        "instance_number":
                            int(
                                session.instance_number
                            ),

                        "instructor_id":
                            int(
                                instructor_id
                            ),

                        "room_id":
                            int(
                                room_id
                            ),

                        "room_capacity":
                            int(
                                room_capacity
                            ),

                        "slot_id":
                            int(
                                slot_id
                            ),

                        "weekday":
                            int(
                                slot[
                                    "weekday"
                                ]
                            ),

                        "starts_at":
                            slot[
                                "starts_at"
                            ],

                        "ends_at":
                            slot[
                                "ends_at"
                            ],

                        "availability":
                            availability_kind,

                        "student_count":
                            int(
                                student_count
                            ),

                        "staff_preference_score":
                            int(
                                staff_preference_score
                            ),

                        "capacity_fit_pct":
                            int(
                                capacity_fit_pct
                            ),

                        "capacity_fit_score":
                            int(
                                capacity_fit_score
                            ),

                        "equipment_fit_pct":
                            int(
                                equipment_fit_pct
                            ),

                        "equipment_match_score":
                            int(
                                equipment_match_score
                            ),

                        "total_score":
                            int(
                                total_score
                            ),

                        "soft_reason_codes":
                            soft_reason_codes
                    })


                    candidate_id += 1


        # =========================================
        # Diagnostics
        # =========================================

        diagnostic_rows.append({

            "session_key":
                session.session_key,

            "section_id":
                section_id,

            "requirement_id":
                requirement_id,

            "feasible_candidates":
                int(
                    feasible_count
                ),

            "rejection_reasons":
                dict(
                    rejection_reasons
                )
        })


    # =============================================
    # Final DataFrames
    # =============================================

    candidates = pd.DataFrame(
        candidate_rows
    )


    diagnostics = pd.DataFrame(
        diagnostic_rows
    )


    return (
        candidates,
        diagnostics
    )
    # =================================================
# Solve Full Timetable
# =================================================

def solve_schedule(
    term_id=None,
    max_time_seconds=30,
    num_workers=2
):

    # =================================================
    # 1) Prepare Sessions + Candidates
    # =================================================

    from .engine import TERM_ID as DEFAULT_TERM_ID

    if term_id is None:
        term_id = DEFAULT_TERM_ID
    else:
        term_id = int(term_id)

    weekly_sessions = (
        build_weekly_sessions()
    )
        # =================================================
    # Filter Requested Term
    # =================================================

    if term_id is not None:

        weekly_sessions = (
            weekly_sessions[
                weekly_sessions[
                    "term_id"
                ].astype(int)
                == int(term_id)
            ]
            .copy()
            .reset_index(
                drop=True
            )
        )

        if weekly_sessions.empty:

            raise ValueError(
                f"No sessions found for term_id={term_id}"
            )
    # Keep solver scoped to the requested term
    # (fixture currently has a single term).
    weekly_sessions = weekly_sessions[
        weekly_sessions["term_id"].astype(int) == int(term_id)
    ].reset_index(drop=True)

    if weekly_sessions.empty:
        raise ValueError(f"No sessions found for term_id={term_id}")

    candidates, diagnostics = (
        generate_all_candidates(
            weekly_sessions
        )
    )


    model = cp_model.CpModel()


    # =================================================
    # 2) Candidate Decision Variables
    # =================================================

    x = {}

    for row in candidates.itertuples(
        index=False
    ):

        candidate_id = int(
            row.candidate_id
        )

        x[candidate_id] = (
            model.NewBoolVar(
                f"candidate_{candidate_id}"
            )
        )


    # =================================================
    # 3) Unscheduled Variables
    # =================================================

    unscheduled = {}

    for session_key in weekly_sessions[
        "session_key"
    ]:

        unscheduled[
            session_key
        ] = model.NewBoolVar(
            f"unscheduled_{session_key}"
        )


    # =================================================
    # 4) Every Session:
    # exactly one candidate OR unscheduled
    # =================================================

    for session in weekly_sessions.itertuples(
        index=False
    ):

        session_key = (
            session.session_key
        )

        session_candidate_ids = (
            candidates.loc[
                candidates[
                    "session_key"
                ]
                == session_key,

                "candidate_id"
            ]
            .astype(int)
            .tolist()
        )


        model.Add(

            sum(
                x[candidate_id]

                for candidate_id
                in session_candidate_ids
            )

            +

            unscheduled[
                session_key
            ]

            == 1
        )


    # =================================================
    # 5) Room Conflicts
    # =================================================

    for _, group in candidates.groupby(
        [
            "term_id",
            "slot_id",
            "room_id"
        ]
    ):

        candidate_ids = (
            group[
                "candidate_id"
            ]
            .astype(int)
            .tolist()
        )

        if len(candidate_ids) > 1:

            model.Add(
                sum(
                    x[candidate_id]

                    for candidate_id
                    in candidate_ids
                )
                <= 1
            )


    # =================================================
    # 6) Instructor Conflicts
    # =================================================

    for _, group in candidates.groupby(
        [
            "term_id",
            "slot_id",
            "instructor_id"
        ]
    ):

        candidate_ids = (
            group[
                "candidate_id"
            ]
            .astype(int)
            .tolist()
        )

        if len(candidate_ids) > 1:

            model.Add(
                sum(
                    x[candidate_id]

                    for candidate_id
                    in candidate_ids
                )
                <= 1
            )


    # =================================================
    # 7) Section Conflicts
    # =================================================

    for _, group in candidates.groupby(
        [
            "term_id",
            "slot_id",
            "section_id"
        ]
    ):

        candidate_ids = (
            group[
                "candidate_id"
            ]
            .astype(int)
            .tolist()
        )

        if len(candidate_ids) > 1:

            model.Add(
                sum(
                    x[candidate_id]

                    for candidate_id
                    in candidate_ids
                )
                <= 1
            )


    # =================================================
    # 8) Student Group Conflicts
    # =================================================

    group_candidate_map = (
        defaultdict(list)
    )


    for row in candidates.itertuples(
        index=False
    ):

        section_groups = (
            groups_by_section.get(
                int(
                    row.section_id
                ),
                set()
            )
        )


        for group_id in section_groups:

            key = (
                int(
                    row.term_id
                ),

                int(
                    row.slot_id
                ),

                int(
                    group_id
                )
            )


            group_candidate_map[
                key
            ].append(
                int(
                    row.candidate_id
                )
            )


    for candidate_ids in (
        group_candidate_map.values()
    ):

        if len(candidate_ids) > 1:

            model.Add(
                sum(
                    x[candidate_id]

                    for candidate_id
                    in candidate_ids
                )
                <= 1
            )


    # =================================================
    # 9) Candidate-Level Score
    # =================================================

    candidate_score = sum(

        int(
            row.total_score
        )
        *
        x[
            int(
                row.candidate_id
            )
        ]

        for row in candidates.itertuples(
            index=False
        )
    )


    # =================================================
    # 10) Compactness
    # Memory-Efficient Version
    # =================================================

    slot_rows = []


    for slot_id, slot in slots.items():

        start_parts = str(
            slot["starts_at"]
        ).split(":")

        end_parts = str(
            slot["ends_at"]
        ).split(":")


        start_minute = (
            int(start_parts[0]) * 60
            + int(start_parts[1])
        )

        end_minute = (
            int(end_parts[0]) * 60
            + int(end_parts[1])
        )


        slot_rows.append({

            "slot_id":
                int(slot_id),

            "term_id":
                int(
                    slot[
                        "term_id"
                    ]
                ),

            "weekday":
                int(
                    slot[
                        "weekday"
                    ]
                ),

            "start_minute":
                start_minute,

            "end_minute":
                end_minute
        })


    slot_df = pd.DataFrame(
        slot_rows
    )


    adjacent_slots = []


    for (
        term_id,
        weekday
    ), day_slots in slot_df.groupby(
        [
            "term_id",
            "weekday"
        ]
    ):

        day_slots = (
            day_slots
            .sort_values(
                "start_minute"
            )
            .reset_index(
                drop=True
            )
        )


        for i in range(
            len(day_slots) - 1
        ):

            current_slot = (
                day_slots.iloc[i]
            )

            next_slot = (
                day_slots.iloc[
                    i + 1
                ]
            )


            if (
                int(
                    current_slot[
                        "end_minute"
                    ]
                )
                ==
                int(
                    next_slot[
                        "start_minute"
                    ]
                )
            ):

                adjacent_slots.append(
                    (
                        int(term_id),
                        int(weekday),

                        int(
                            current_slot[
                                "slot_id"
                            ]
                        ),

                        int(
                            next_slot[
                                "slot_id"
                            ]
                        )
                    )
                )


    # =================================================
    # Section Occupancy
    # =================================================

    section_occupancy = {}


    for keys, group in candidates.groupby(
        [
            "term_id",
            "weekday",
            "section_id",
            "slot_id"
        ]
    ):

        (
            term_id,
            weekday,
            section_id,
            slot_id
        ) = map(
            int,
            keys
        )


        candidate_ids = (
            group[
                "candidate_id"
            ]
            .astype(int)
            .tolist()
        )


        variable = (
            model.NewBoolVar(
                f"section_occ_"
                f"{term_id}_"
                f"{weekday}_"
                f"{section_id}_"
                f"{slot_id}"
            )
        )


        model.Add(
            variable
            ==
            sum(
                x[candidate_id]

                for candidate_id
                in candidate_ids
            )
        )


        section_occupancy[
            (
                term_id,
                weekday,
                section_id,
                slot_id
            )
        ] = variable


    # =================================================
    # Instructor Occupancy
    # =================================================

    instructor_occupancy = {}


    for keys, group in candidates.groupby(
        [
            "term_id",
            "weekday",
            "instructor_id",
            "slot_id"
        ]
    ):

        (
            term_id,
            weekday,
            instructor_id,
            slot_id
        ) = map(
            int,
            keys
        )


        candidate_ids = (
            group[
                "candidate_id"
            ]
            .astype(int)
            .tolist()
        )


        variable = (
            model.NewBoolVar(
                f"instructor_occ_"
                f"{term_id}_"
                f"{weekday}_"
                f"{instructor_id}_"
                f"{slot_id}"
            )
        )


        model.Add(
            variable
            ==
            sum(
                x[candidate_id]

                for candidate_id
                in candidate_ids
            )
        )


        instructor_occupancy[
            (
                term_id,
                weekday,
                instructor_id,
                slot_id
            )
        ] = variable


    # =================================================
    # Compactness Variables
    # =================================================

    compactness_vars = []


    section_ids = sorted(
        candidates[
            "section_id"
        ]
        .astype(int)
        .unique()
    )


    # Same Section
    for (
        term_id,
        weekday,
        slot_a,
        slot_b
    ) in adjacent_slots:

        for section_id in section_ids:

            key_a = (
                term_id,
                weekday,
                section_id,
                slot_a
            )

            key_b = (
                term_id,
                weekday,
                section_id,
                slot_b
            )


            if (
                key_a
                not in section_occupancy
                or
                key_b
                not in section_occupancy
            ):
                continue


            pair_var = (
                model.NewBoolVar(
                    f"section_compact_"
                    f"{term_id}_"
                    f"{weekday}_"
                    f"{section_id}_"
                    f"{slot_a}_"
                    f"{slot_b}"
                )
            )


            model.Add(
                pair_var
                <=
                section_occupancy[
                    key_a
                ]
            )

            model.Add(
                pair_var
                <=
                section_occupancy[
                    key_b
                ]
            )

            model.Add(
                pair_var
                >=
                section_occupancy[
                    key_a
                ]
                +
                section_occupancy[
                    key_b
                ]
                - 1
            )


            compactness_vars.append(
                pair_var
            )


    instructor_ids = sorted(
        candidates[
            "instructor_id"
        ]
        .astype(int)
        .unique()
    )


    # Same Instructor
    for (
        term_id,
        weekday,
        slot_a,
        slot_b
    ) in adjacent_slots:

        for instructor_id in instructor_ids:

            key_a = (
                term_id,
                weekday,
                instructor_id,
                slot_a
            )

            key_b = (
                term_id,
                weekday,
                instructor_id,
                slot_b
            )


            if (
                key_a
                not in instructor_occupancy
                or
                key_b
                not in instructor_occupancy
            ):
                continue


            pair_var = (
                model.NewBoolVar(
                    f"instructor_compact_"
                    f"{term_id}_"
                    f"{weekday}_"
                    f"{instructor_id}_"
                    f"{slot_a}_"
                    f"{slot_b}"
                )
            )


            model.Add(
                pair_var
                <=
                instructor_occupancy[
                    key_a
                ]
            )

            model.Add(
                pair_var
                <=
                instructor_occupancy[
                    key_b
                ]
            )

            model.Add(
                pair_var
                >=
                instructor_occupancy[
                    key_a
                ]
                +
                instructor_occupancy[
                    key_b
                ]
                - 1
            )


            compactness_vars.append(
                pair_var
            )


    compactness_bonus = (

        COMPACTNESS_POINTS

        *

        sum(
            compactness_vars
        )
    )


    # =================================================
    # 11) Room Utilization
    # =================================================

    room_used = {}


    for room_id, group in candidates.groupby(
        "room_id"
    ):

        room_id = int(
            room_id
        )


        candidate_ids = (
            group[
                "candidate_id"
            ]
            .astype(int)
            .tolist()
        )


        room_used[
            room_id
        ] = model.NewBoolVar(
            f"room_used_{room_id}"
        )


        for candidate_id in candidate_ids:

            model.Add(
                x[
                    candidate_id
                ]
                <=
                room_used[
                    room_id
                ]
            )


        model.Add(
            room_used[
                room_id
            ]
            <=
            sum(
                x[
                    candidate_id
                ]

                for candidate_id
                in candidate_ids
            )
        )


    room_utilization_penalty = (

        ROOM_ACTIVE_PENALTY

        *

        sum(
            room_used.values()
        )
    )


    # =================================================
    # 12) Unscheduled Penalty
    # =================================================

    unscheduled_cost = sum(

        UNSCHEDULED_PENALTY
        *
        unscheduled[
            session_key
        ]

        for session_key
        in unscheduled
    )


    # =================================================
    # 13) Final Objective
    # =================================================

    model.Maximize(

        candidate_score

        +

        compactness_bonus

        -

        room_utilization_penalty

        -

        unscheduled_cost
    )


    # =================================================
    # 14) Solve
    # =================================================

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = (
        float(
            max_time_seconds
        )
    )

    solver.parameters.num_search_workers = (
        int(
            num_workers
        )
    )


    status = solver.Solve(
        model
    )


    status_name = (
        solver.StatusName(
            status
        )
    )


    # =================================================
    # 15) Check Solver Result
    # =================================================

    if status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE
    ):

        return {
            "solver_status":
                status_name,

            "scheduled_count":
                0,

            "unscheduled_count":
                len(
                    weekly_sessions
                ),

            "scheduled_sessions":
                [],

            "unscheduled_sessions":
                weekly_sessions[
                    "session_key"
                ].tolist(),

            "candidate_count":
                len(
                    candidates
                )
        }


    # =================================================
    # 16) Selected Candidates
    # =================================================

    selected_candidate_ids = [

        candidate_id

        for (
            candidate_id,
            variable
        )
        in x.items()

        if (
            solver.Value(
                variable
            )
            == 1
        )
    ]


    selected_schedule = (

        candidates[
            candidates[
                "candidate_id"
            ].isin(
                selected_candidate_ids
            )
        ]

        .sort_values(
            [
                "weekday",
                "starts_at",
                "section_code"
            ]
        )

        .reset_index(
            drop=True
        )
    )


    # =================================================
    # 17) Unscheduled Sessions
    # =================================================

    unscheduled_sessions = [

        session_key

        for (
            session_key,
            variable
        )
        in unscheduled.items()

        if (
            solver.Value(
                variable
            )
            == 1
        )
    ]


    # =================================================
    # 18) Final Objective Metrics
    # =================================================

    candidate_score_value = (

        int(
            selected_schedule[
                "total_score"
            ].sum()
        )

        if not selected_schedule.empty

        else 0
    )


    selected_compact_pairs = int(

        sum(
            solver.Value(
                variable
            )

            for variable
            in compactness_vars
        )
    )


    compactness_bonus_value = (

        selected_compact_pairs
        *
        COMPACTNESS_POINTS
    )


    active_room_ids = [

        int(
            room_id
        )

        for (
            room_id,
            variable
        )
        in room_used.items()

        if (
            solver.Value(
                variable
            )
            == 1
        )
    ]


    active_room_count = len(
        active_room_ids
    )


    room_penalty_value = (

        active_room_count
        *
        ROOM_ACTIVE_PENALTY
    )


    unscheduled_penalty_value = (

        len(
            unscheduled_sessions
        )
        *
        UNSCHEDULED_PENALTY
    )


    calculated_objective = (

        candidate_score_value

        +

        compactness_bonus_value

        -

        room_penalty_value

        -

        unscheduled_penalty_value
    )


    solver_objective = int(
        round(
            solver.ObjectiveValue()
        )
    )


        # =================================================
    # 19) Build API Payload
    # =================================================
    # =================================================
    # Build Safe Alternatives
    # =================================================

    def candidate_conflicts_with_selected(
        alternative,
        selected_rows,
        current_session_key,
    ):

        alternative_section_groups = (
            groups_by_section.get(
                int(alternative.section_id),
                set(),
            )
        )

        for selected in selected_rows:

            if (
                str(selected.session_key)
                == str(current_session_key)
            ):
                continue

            # Different slots cannot conflict
            if (
                int(selected.slot_id)
                != int(alternative.slot_id)
            ):
                continue

            # Same room
            if (
                int(selected.room_id)
                == int(alternative.room_id)
            ):
                return True

            # Same instructor
            if (
                int(selected.instructor_id)
                == int(alternative.instructor_id)
            ):
                return True

            # Same section
            if (
                int(selected.section_id)
                == int(alternative.section_id)
            ):
                return True

            # Shared student group
            selected_groups = (
                groups_by_section.get(
                    int(selected.section_id),
                    set(),
                )
            )

            if (
                alternative_section_groups
                & selected_groups
            ):
                return True

        return False


    selected_rows_list = list(
        selected_schedule.itertuples(
            index=False
        )
    )
    scheduled_sessions = []

    for row in selected_schedule.itertuples(
        index=False
    ):

        instructor = accounts[
            int(row.instructor_id)
        ]

        room = rooms[
            int(row.room_id)
        ]
        session_alternatives = (
            candidates[
                (
                    candidates[
                        "session_key"
                    ]
                    == row.session_key
                )
                &
                (
                    candidates[
                        "candidate_id"
                    ].astype(int)
                    != int(row.candidate_id)
                )
            ]
            .sort_values(
                [
                    "total_score",
                    "staff_preference_score",
                    "capacity_fit_score",
                    "equipment_match_score",
                ],
                ascending=False,
            )
        )


        alternatives = []


        for alternative in (
            session_alternatives.itertuples(
                index=False
            )
        ):

            if candidate_conflicts_with_selected(
                alternative=
                    alternative,

                selected_rows=
                    selected_rows_list,

                current_session_key=
                    row.session_key,
            ):
                continue


            alternatives.append({

                "candidate_id":
                    int(
                        alternative.candidate_id
                    ),

                "instructor_id":
                    int(
                        alternative.instructor_id
                    ),

                "room_id":
                    int(
                        alternative.room_id
                    ),

                "slot_id":
                    int(
                        alternative.slot_id
                    ),

                "weekday":
                    int(
                        alternative.weekday
                    ),

                "starts_at":
                    str(
                        alternative.starts_at
                    ),

                "ends_at":
                    str(
                        alternative.ends_at
                    ),

                "availability":
                    str(
                        alternative.availability
                    ),

                "score":
                    int(
                        alternative.total_score
                    ),

                "score_breakdown": {

                    "staff_preference":
                        int(
                            alternative.staff_preference_score
                        ),

                    "capacity_fit":
                        int(
                            alternative.capacity_fit_score
                        ),

                    "capacity_fit_pct":
                        int(
                            alternative.capacity_fit_pct
                        ),

                    "equipment_match":
                        int(
                            alternative.equipment_match_score
                        ),

                    "equipment_fit_pct":
                        int(
                            alternative.equipment_fit_pct
                        ),
                },

                "soft_reason_codes":
                    list(
                        alternative.soft_reason_codes
                    ),
            })


            # Maximum 5 alternatives
            if len(alternatives) >= 5:
                break
            
        scheduled_sessions.append({

            "session_key":
                str(row.session_key),

            "section_id":
                int(row.section_id),

            "section_code":
                str(row.section_code),

            "requirement_id":
                int(row.requirement_id),

            "instance_number":
                int(row.instance_number),

            "status":
                "SCHEDULED",

            "instructor": {
                "id":
                    int(row.instructor_id),

                "name":
                    instructor.get(
                        "full_name"
                    )
            },

            "room": {
                "id":
                    int(row.room_id),

                "code":
                    room.get(
                        "code"
                    )
            },

            "slot": {
                "id":
                    int(row.slot_id),

                "weekday":
                    int(row.weekday),

                "starts_at":
                    str(row.starts_at),

                "ends_at":
                    str(row.ends_at)
            },

            "availability":
                str(row.availability),

            "score":
                int(row.total_score),

            "score_breakdown": {

                "staff_preference": {
                    "score":
                        int(
                            row.staff_preference_score
                        ),

                    "max_score":
                        30,

                    "availability":
                        str(
                            row.availability
                        )
                },

                "capacity_fit": {
                    "score":
                        int(
                            row.capacity_fit_score
                        ),

                    "max_score":
                        25,

                    "fit_percentage":
                        int(
                            row.capacity_fit_pct
                        ),

                    "student_count":
                        int(
                            row.student_count
                        ),

                    "room_capacity":
                        int(
                            row.room_capacity
                        )
                },

                "equipment_match": {
                    "score":
                        int(
                            row.equipment_match_score
                        ),

                    "max_score":
                        20,

                    "fit_percentage":
                        int(
                            row.equipment_fit_pct
                        )
                },

                "candidate_total": {
                    "score":
                        int(
                            row.total_score
                        ),

                    "max_score":
                        75
                }
            },

            "soft_reason_codes":
                list(
                    row.soft_reason_codes
                ),

            "alternatives":
                alternatives
            })

    # =================================================
    # 20) Build Unscheduled Payload
    # =================================================

    unscheduled_payload = []


    for session_key in unscheduled_sessions:

        session_row = weekly_sessions[
            weekly_sessions[
                "session_key"
            ]
            == session_key
        ].iloc[0]


        diagnostic_rows = diagnostics[
            diagnostics[
                "session_key"
            ]
            == session_key
        ]


        rejection_reasons = {}


        if not diagnostic_rows.empty:

            raw_reasons = diagnostic_rows.iloc[0][
                "rejection_reasons"
            ]

            if isinstance(
                raw_reasons,
                dict
            ):
                rejection_reasons = raw_reasons


        reason_codes = list(
            rejection_reasons.keys()
        )


        if not reason_codes:

            reason_codes = [
                "NO_FEASIBLE_CANDIDATE"
            ]


        unscheduled_payload.append({

            "session_key":
                str(session_key),

            "section_id":
                int(
                    session_row[
                        "section_id"
                    ]
                ),

            "section_code":
                str(
                    session_row[
                        "section_code"
                    ]
                ),

            "requirement_id":
                int(
                    session_row[
                        "requirement_id"
                    ]
                ),

            "kind":
                str(
                    session_row[
                        "kind"
                    ]
                ),

            "instance_number":
                int(
                    session_row[
                        "instance_number"
                    ]
                ),

            "status":
                "UNSCHEDULED",

            "reason_codes":
                reason_codes,

            "diagnostic_counts": {

                str(reason):
                    int(count)

                for (
                    reason,
                    count
                )
                in rejection_reasons.items()
            }
        })


    # =================================================
    # 21) Validate Objective Calculation
    # =================================================

    if (
        int(calculated_objective)
        != int(solver_objective)
    ):

        raise RuntimeError(
            "Solver objective mismatch: "
            f"calculated={calculated_objective}, "
            f"solver={solver_objective}"
        )


    # =================================================
    # 22) Final API Response
    # =================================================

    return {

        "solver_status":
            status_name,

        "summary": {

            "solver_sessions":
                int(
                    len(
                        weekly_sessions
                    )
                ),

            "candidate_count":
                int(
                    len(
                        candidates
                    )
                ),

            "scheduled":
                int(
                    len(
                        selected_schedule
                    )
                ),

            "unscheduled":
                int(
                    len(
                        unscheduled_sessions
                    )
                )
        },

        "objective_breakdown": {

            "candidate_level_score":
                int(
                    candidate_score_value
                ),

            "compactness": {

                "adjacent_pairs":
                    int(
                        selected_compact_pairs
                    ),

                "points_per_pair":
                    int(
                        COMPACTNESS_POINTS
                    ),

                "bonus":
                    int(
                        compactness_bonus_value
                    )
            },

            "room_utilization": {

                "active_room_count":
                    int(
                        active_room_count
                    ),

                "active_room_ids":
                    active_room_ids,

                "penalty_per_active_room":
                    int(
                        ROOM_ACTIVE_PENALTY
                    ),

                "penalty":
                    int(
                        room_penalty_value
                    )
            },

            "unscheduled": {

                "count":
                    int(
                        len(
                            unscheduled_sessions
                        )
                    ),

                "penalty_per_session":
                    int(
                        UNSCHEDULED_PENALTY
                    ),

                "total_penalty":
                    int(
                        unscheduled_penalty_value
                    )
            },

            "final_objective_value":
                int(
                    calculated_objective
                ),

            "solver_objective_value":
                int(
                    solver_objective
                )
        },

        "soft_score_definitions":
            SOFT_SCORE_DEFINITIONS,

        "scheduled_sessions":
            scheduled_sessions,

        "unscheduled_sessions":
            unscheduled_payload,
    }
