from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Tanseek_CSV_Data"


# =================================================
# Load Data
# =================================================

tables = {
    p.stem: pd.read_csv(
        p,
        encoding="utf-8-sig"
    )
    for p in DATA.glob("*.csv")
}


def by_id(name):
    return (
        tables[name]
        .set_index("id")
        .to_dict("index")
    )


sections = by_id("sections")
requirements = by_id("session_requirements")
rooms = by_id("rooms")
slots = by_id("time_slots")
accounts = by_id("accounts")


# =================================================
# Section Groups + Student Counts
# =================================================

group_links = tables[
    "section_groups"
].merge(
    tables["student_groups"][
        [
            "id",
            "student_count",
            "name"
        ]
    ],
    left_on="group_id",
    right_on="id",
    validate="many_to_one"
)


group_summary = (
    group_links
    .groupby(
        "section_id",
        as_index=False
    )
    .agg(
        group_ids=("group_id", list),
        student_count=("student_count", "sum")
    )
)


groups_by_section = {
    int(row.section_id):
        set(
            map(
                int,
                row.group_ids
            )
        )

    for row in group_summary.itertuples()
}


students_by_section = {
    int(row.section_id):
        int(row.student_count)

    for row in group_summary.itertuples()
}


# =================================================
# Equipment
# =================================================

required = {
    (
        int(row.requirement_id),
        int(row.equipment_id)
    ):
        int(row.quantity)

    for row
    in tables[
        "required_equipment"
    ].itertuples()
}


available = {
    (
        int(row.room_id),
        int(row.equipment_id)
    ):
        int(row.quantity)

    for row
    in tables[
        "room_equipment"
    ].itertuples()
}


# =================================================
# Eligible Instructors
# =================================================

eligible = {
    (
        int(row.section_id),
        int(row.requirement_id),
        int(row.instructor_id)
    )

    for row
    in tables[
        "section_instructors"
    ].itertuples()
}


# =================================================
# Instructor Availability
# =================================================

submissions = (
    tables[
        "availability_submissions"
    ]
    .sort_values(
        [
            "revision",
            "id"
        ]
    )
    .drop_duplicates(
        [
            "term_id",
            "instructor_id"
        ],
        keep="last"
    )
)


submission_by_staff = {
    (
        int(row.term_id),
        int(row.instructor_id)
    ):
        row

    for row
    in submissions.itertuples(
        index=False
    )
}


availability = {
    (
        int(row.submission_id),
        int(row.slot_id)
    ):
        row.kind

    for row
    in tables[
        "availability_slots"
    ].itertuples(
        index=False
    )
}


# =================================================
# Existing Allocations
# =================================================

allocations = (
    tables["allocations"]
    .merge(
        tables["time_slots"][
            [
                "id",
                "weekday",
                "starts_at",
                "ends_at"
            ]
        ],
        left_on="start_slot_id",
        right_on="id",
        validate="many_to_one",
        suffixes=(
            "",
            "_slot"
        )
    )
)


# =================================================
# Holidays
# =================================================

term_holidays = tables.get(
    "term_holidays",
    pd.DataFrame(
        columns=[
            "id",
            "term_id",
            "holiday_date",
            "reason"
        ]
    )
).copy()


if not term_holidays.empty:

    term_holidays[
        "holiday_date"
    ] = pd.to_datetime(
        term_holidays[
            "holiday_date"
        ]
    ).dt.date


# =================================================
# Room Closures
# =================================================

room_closures = tables.get(
    "room_closures",
    pd.DataFrame(
        columns=[
            "id",
            "room_id",
            "starts_at",
            "ends_at",
            "reason"
        ]
    )
).copy()


if not room_closures.empty:

    room_closures[
        "starts_at_ts"
    ] = (
        pd.to_datetime(
            room_closures[
                "starts_at"
            ],
            utc=True
        )
        .dt
        .tz_convert(
            "Africa/Cairo"
        )
    )

    room_closures[
        "ends_at_ts"
    ] = (
        pd.to_datetime(
            room_closures[
                "ends_at"
            ],
            utc=True
        )
        .dt
        .tz_convert(
            "Africa/Cairo"
        )
    )

# =================================================
# Schedule Version Context
# =================================================

TERM_ID = int(
    tables["sections"]["term_id"]
    .mode()
    .iloc[0]
)


schedule_versions_df = (
    tables["schedule_versions"]
    .copy()
)


def get_latest_version_by_state(
    term_id,
    state
):

    matches = schedule_versions_df[
        (
            schedule_versions_df[
                "term_id"
            ].astype(int)
            == int(term_id)
        )
        &
        (
            schedule_versions_df[
                "state"
            ]
            == state
        )
    ]

    if matches.empty:
        return None

    return (
        matches
        .sort_values(
            [
                "version_number",
                "id"
            ]
        )
        .iloc[-1]
    )


published_version = (
    get_latest_version_by_state(
        TERM_ID,
        "PUBLISHED"
    )
)


working_version = (
    get_latest_version_by_state(
        TERM_ID,
        "DRAFT"
    )
)


def get_version_allocations(
    version_id
):

    if version_id is None:
        return (
            allocations
            .iloc[0:0]
            .copy()
        )

    return (
        allocations[
            allocations[
                "version_id"
            ].astype(int)
            == int(version_id)
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )


published_allocations = (
    get_version_allocations(
        None
        if published_version is None
        else int(
            published_version["id"]
        )
    )
)


working_allocations = (
    get_version_allocations(
        None
        if working_version is None
        else int(
            working_version["id"]
        )
    )
)


if working_version is not None:

    solver_existing_allocations = (
        working_allocations.copy()
    )

elif published_version is not None:

    solver_existing_allocations = (
        published_allocations.copy()
    )

else:

    solver_existing_allocations = (
        allocations
        .iloc[0:0]
        .copy()
    )


published_snapshot = (
    published_allocations
    .copy(
        deep=True
    )
)

# =================================================
# Helpers
# =================================================

def minutes(value):

    hh, mm = str(
        value
    ).split(":")[:2]

    return (
        int(hh) * 60
        + int(mm)
    )


def overlaps(
    start1,
    end1,
    start2,
    end2
):

    return (
        max(
            start1,
            start2
        )
        <
        min(
            end1,
            end2
        )
    )


def is_term_holiday(
    term_id,
    session_date
):

    if session_date is None:
        return False

    if term_holidays.empty:
        return False

    session_date = (
        pd.Timestamp(
            session_date
        ).date()
    )

    rows = term_holidays[
        (
            term_holidays[
                "term_id"
            ].astype(int)
            == int(term_id)
        )
        &
        (
            term_holidays[
                "holiday_date"
            ]
            == session_date
        )
    ]

    return not rows.empty


def is_room_closed(
    room_id,
    session_date,
    starts_at,
    ends_at
):

    if session_date is None:
        return False

    if room_closures.empty:
        return False

    candidate_start = pd.Timestamp(
        f"{session_date} {starts_at}",
        tz="Africa/Cairo"
    )

    candidate_end = pd.Timestamp(
        f"{session_date} {ends_at}",
        tz="Africa/Cairo"
    )

    room_rows = room_closures[
        room_closures[
            "room_id"
        ].astype(int)
        == int(room_id)
    ]

    for closure in room_rows.itertuples(
        index=False
    ):

        if (
            candidate_start
            < closure.ends_at_ts
            and
            candidate_end
            > closure.starts_at_ts
        ):
            return True

    return False


# =================================================
# Hard Constraint Priority
# =================================================

PRIORITY = [
    "NO_WORKING_SLOT",
    "TERM_HOLIDAY",
    "ROOM_CLOSED",
    "INVALID_DURATION",
    "AVAILABILITY_NOT_CONFIRMED",
    "STAFF_UNAVAILABLE",
    "ROOM_CONFLICT",
    "STAFF_CONFLICT",
    "GROUP_CONFLICT",
    "ROOM_TYPE_MISMATCH",
    "CAPACITY_SHORTAGE",
    "EQUIPMENT_SHORTAGE",
    "INELIGIBLE_INSTRUCTOR",
    "INVALID_REFERENCE"
]


# =================================================
# Allocation Validator
# =================================================

def check_allocation(
    term_id,
    section_id,
    requirement_id,
    instructor_id,
    room_id,
    weekday,
    starts_at,
    ends_at,
    session_date=None,
    existing=None
):

    if existing is None:
        existing = solver_existing_allocations

    term_id = int(term_id)
    section_id = int(section_id)
    requirement_id = int(
        requirement_id
    )
    instructor_id = int(
        instructor_id
    )
    room_id = int(room_id)
    weekday = int(weekday)

    reasons = set()


    # -------------------------
    # References
    # -------------------------

    if any(
        key not in mapping

        for key, mapping in [
            (
                section_id,
                sections
            ),
            (
                requirement_id,
                requirements
            ),
            (
                room_id,
                rooms
            ),
            (
                instructor_id,
                accounts
            )
        ]
    ):

        return {
            "primary_result":
                "INVALID_REFERENCE",

            "reasons": [
                "INVALID_REFERENCE"
            ],

            "slot_id":
                None
        }


    section = sections[
        section_id
    ]

    requirement = requirements[
        requirement_id
    ]

    room = rooms[
        room_id
    ]


    if (
        int(
            section[
                "term_id"
            ]
        )
        != term_id

        or

        int(
            requirement[
                "term_id"
            ]
        )
        != term_id

        or

        int(
            section[
                "course_id"
            ]
        )
        != int(
            requirement[
                "course_id"
            ]
        )
    ):

        reasons.add(
            "INVALID_REFERENCE"
        )


    # -------------------------
    # Instructor Eligibility
    # -------------------------

    if (
        section_id,
        requirement_id,
        instructor_id
    ) not in eligible:

        reasons.add(
            "INELIGIBLE_INSTRUCTOR"
        )


    start = minutes(
        starts_at
    )

    end = minutes(
        ends_at
    )


    # -------------------------
    # Date Constraints
    # -------------------------

    if session_date is not None:

        if is_term_holiday(
            term_id,
            session_date
        ):

            reasons.add(
                "TERM_HOLIDAY"
            )

        if is_room_closed(
            room_id,
            session_date,
            starts_at,
            ends_at
        ):

            reasons.add(
                "ROOM_CLOSED"
            )


    # -------------------------
    # Working Slot
    # -------------------------

    matching = [
        (
            slot_id,
            slot
        )

        for slot_id, slot
        in slots.items()

        if (
            int(
                slot[
                    "term_id"
                ]
            )
            == term_id

            and

            int(
                slot[
                    "weekday"
                ]
            )
            == weekday

            and

            minutes(
                slot[
                    "starts_at"
                ]
            )
            == start
        )
    ]


    slot_id = (
        matching[0][0]
        if matching
        else None
    )


    if (
        not matching
        or start < 9 * 60
    ):

        reasons.add(
            "NO_WORKING_SLOT"
        )


    if (
        end - start
        != int(
            requirement[
                "duration_minutes"
            ]
        )

        or

        (
            matching
            and
            end
            != minutes(
                matching[0][1][
                    "ends_at"
                ]
            )
        )
    ):

        reasons.add(
            "INVALID_DURATION"
        )


    # -------------------------
    # Staff Availability
    # -------------------------

    submission = (
        submission_by_staff.get(
            (
                term_id,
                instructor_id
            )
        )
    )


    if (
        submission is None
        or submission.state
        != "CONFIRMED"
    ):

        reasons.add(
            "AVAILABILITY_NOT_CONFIRMED"
        )

    elif (
        slot_id is not None
        and
        availability.get(
            (
                int(
                    submission.id
                ),
                int(slot_id)
            )
        )
        not in (
            "AVAILABLE",
            "PREFERRED"
        )
    ):

        reasons.add(
            "STAFF_UNAVAILABLE"
        )


    # -------------------------
    # Room Type
    # -------------------------

    if (
        room[
            "kind"
        ]
        != requirement[
            "required_room_kind"
        ]

        or

        not bool(
            room[
                "active"
            ]
        )
    ):

        reasons.add(
            "ROOM_TYPE_MISMATCH"
        )


    # -------------------------
    # Capacity
    # -------------------------

    if (
        students_by_section.get(
            section_id,
            0
        )
        >
        int(
            room[
                "capacity"
            ]
        )
    ):

        reasons.add(
            "CAPACITY_SHORTAGE"
        )


    # -------------------------
    # Equipment
    # -------------------------

    for (
        req_id,
        equipment_id
    ), quantity in required.items():

        if (
            req_id
            == requirement_id

            and

            available.get(
                (
                    room_id,
                    equipment_id
                ),
                0
            )
            < quantity
        ):

            reasons.add(
                "EQUIPMENT_SHORTAGE"
            )


    # -------------------------
    # Existing Conflicts
    # -------------------------

    candidate_groups = (
        groups_by_section.get(
            section_id,
            set()
        )
    )


    for old in existing.itertuples(
        index=False
    ):

        if (
            int(old.term_id)
            != term_id
        ):
            continue

        if (
            int(old.weekday)
            != weekday
        ):
            continue

        # Same-section conflicts are
        # handled in check_candidate_strict()
        if (
            int(old.section_id)
            == section_id
        ):
            continue

        if (
            not overlaps(
                start,
                end,
                minutes(
                    old.starts_at
                ),
                minutes(
                    old.ends_at
                )
            )
        ):
            continue


        if (
            int(old.room_id)
            == room_id
        ):

            reasons.add(
                "ROOM_CONFLICT"
            )


        if (
            int(old.instructor_id)
            == instructor_id
        ):

            reasons.add(
                "STAFF_CONFLICT"
            )


        old_groups = (
            groups_by_section.get(
                int(
                    old.section_id
                ),
                set()
            )
        )


        if (
            candidate_groups
            & old_groups
        ):

            reasons.add(
                "GROUP_CONFLICT"
            )


    # -------------------------
    # Result
    # -------------------------

    ordered = [
        reason

        for reason in PRIORITY

        if reason in reasons
    ]


    return {
        "primary_result":
            (
                ordered[0]
                if ordered
                else "FEASIBLE"
            ),

        "reasons":
            ordered,

        "slot_id":
            (
                int(slot_id)
                if slot_id is not None
                else None
            )
    }
    # =================================================
# Strict Candidate Checker
# =================================================

def check_candidate_strict(
    term_id,
    section_id,
    requirement_id,
    instructor_id,
    room_id,
    weekday,
    starts_at,
    ends_at,
    existing,
    session_date=None
):

    result = check_allocation(
        term_id=term_id,
        section_id=section_id,
        requirement_id=requirement_id,
        instructor_id=instructor_id,
        room_id=room_id,
        weekday=weekday,
        starts_at=starts_at,
        ends_at=ends_at,
        existing=existing,
        session_date=session_date
    )


    reasons = set(
        result["reasons"]
    )


    start = minutes(
        starts_at
    )

    end = minutes(
        ends_at
    )


    # Explicit same-section conflict check
    for old in existing.itertuples(
        index=False
    ):

        if (
            int(old.term_id)
            != int(term_id)
        ):
            continue

        if (
            int(old.weekday)
            != int(weekday)
        ):
            continue

        if (
            int(old.section_id)
            != int(section_id)
        ):
            continue

        if not overlaps(
            start,
            end,
            minutes(
                old.starts_at
            ),
            minutes(
                old.ends_at
            )
        ):
            continue


        reasons.add(
            "GROUP_CONFLICT"
        )


        if (
            int(old.room_id)
            == int(room_id)
        ):

            reasons.add(
                "ROOM_CONFLICT"
            )


        if (
            int(old.instructor_id)
            == int(instructor_id)
        ):

            reasons.add(
                "STAFF_CONFLICT"
            )


    ordered = [
        reason
        for reason in PRIORITY
        if reason in reasons
    ]


    return {
        "primary_result":
            (
                ordered[0]
                if ordered
                else "FEASIBLE"
            ),

        "reasons":
            ordered,

        "slot_id":
            result["slot_id"]
    }


# =================================================
# Published Change Request Validator
# =================================================

def evaluate_published_change_request(
    allocation_id,
    session_date,
    proposed_room_id=None,
    proposed_instructor_id=None,
    proposed_start_slot_id=None
):

    # -------------------------
    # Published version required
    # -------------------------

    if published_version is None:

        return {
            "status":
                "NO_PUBLISHED_VERSION",

            "primary_result":
                None,

            "reasons": [
                "NO_PUBLISHED_VERSION"
            ]
        }


    # -------------------------
    # Find allocation
    # only inside immutable published snapshot
    # -------------------------

    target_rows = published_snapshot[
        published_snapshot[
            "id"
        ].astype(int)
        == int(allocation_id)
    ]


    if target_rows.empty:

        return {
            "status":
                "ALLOCATION_NOT_FOUND",

            "primary_result":
                "INVALID_REFERENCE",

            "reasons": [
                "INVALID_REFERENCE"
            ]
        }


    target = target_rows.iloc[0]


    term_id = int(
        target["term_id"]
    )

    section_id = int(
        target["section_id"]
    )

    requirement_id = int(
        target["requirement_id"]
    )


    # -------------------------
    # Proposed instructor
    # -------------------------

    instructor_id = (
        int(
            target[
                "instructor_id"
            ]
        )
        if proposed_instructor_id is None
        else int(
            proposed_instructor_id
        )
    )


    # -------------------------
    # Proposed room
    # -------------------------

    room_id = (
        int(
            target[
                "room_id"
            ]
        )
        if proposed_room_id is None
        else int(
            proposed_room_id
        )
    )


    # -------------------------
    # Proposed slot
    # -------------------------

    start_slot_id = (
        int(
            target[
                "start_slot_id"
            ]
        )
        if proposed_start_slot_id is None
        else int(
            proposed_start_slot_id
        )
    )


    if start_slot_id not in slots:

        return {
            "status":
                "BLOCKED",

            "primary_result":
                "INVALID_REFERENCE",

            "reasons": [
                "INVALID_REFERENCE"
            ]
        }


    slot = slots[
        start_slot_id
    ]


    # -------------------------
    # Real date weekday
    # -------------------------

    session_date_ts = pd.Timestamp(
        session_date
    )


    weekday = int(
        session_date_ts.isoweekday()
    )


    # Proposed slot must belong to same weekday
    if (
        int(
            slot["weekday"]
        )
        != weekday
    ):

        return {
            "status":
                "BLOCKED",

            "primary_result":
                "NO_WORKING_SLOT",

            "reasons": [
                "NO_WORKING_SLOT"
            ]
        }


    # -------------------------
    # Keep rest of published
    # schedule immutable
    # -------------------------

    immutable_existing = (
        published_snapshot[
            published_snapshot[
                "id"
            ].astype(int)
            != int(allocation_id)
        ]
        .copy()
    )


    # -------------------------
    # Validate proposal
    # -------------------------

    result = check_candidate_strict(
        term_id=term_id,
        section_id=section_id,
        requirement_id=requirement_id,
        instructor_id=instructor_id,
        room_id=room_id,
        weekday=weekday,
        starts_at=slot[
            "starts_at"
        ],
        ends_at=slot[
            "ends_at"
        ],
        existing=immutable_existing,
        session_date=session_date
    )


    status = (
        "FEASIBLE"
        if result[
            "primary_result"
        ]
        == "FEASIBLE"
        else "BLOCKED"
    )


    return {
        "status":
            status,

        "primary_result":
            result[
                "primary_result"
            ],

        "reasons":
            result[
                "reasons"
            ],

        "source_published_version_id":
            int(
                published_version[
                    "id"
                ]
            ),

        "source_allocation_id":
            int(
                allocation_id
            ),

        "proposal": {

            "session_date":
                str(
                    session_date
                ),

            "weekday":
                weekday,

            "start_slot_id":
                start_slot_id,

            "room_id":
                room_id,

            "instructor_id":
                instructor_id
        }
    }