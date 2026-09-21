from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Tanseek_CSV_Data"


# =================================================
# Data Source Boundary
# The solver must not depend directly on CSV paths.
# Local testing uses CsvSchedulingDataRepository;
# the backend can later provide PostgresSchedulingDataRepository.
# =================================================

class SchedulingDataRepository(ABC):

    """Provides the datasets required by the solver."""

    @abstractmethod
    def load(self):
        """Return {table_name: DataFrame}."""


def apply_v1_compatibility_aliases(tables):
    """Single labelled place for v1 table-name compatibility.

    v1 named these tables `session_requirements` and `section_groups`;
    v2 names them `course_session_requirements` and
    `section_group_assignments`. New code must use the v2 names.
    """

    if (
        "session_requirements" not in tables
        and "course_session_requirements" in tables
    ):
        tables["session_requirements"] = (
            tables["course_session_requirements"].copy()
        )

    if (
        "section_groups" not in tables
        and "section_group_assignments" in tables
    ):
        tables["section_groups"] = (
            tables["section_group_assignments"][
                ["section_id", "group_id"]
            ].copy()
        )

    return tables


class CsvSchedulingDataRepository(SchedulingDataRepository):

    """Loads the file-based v2 fixture for local testing."""

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else DATA

    def load(self):

        tables = {
            p.stem: pd.read_csv(
                p,
                encoding="utf-8-sig"
            )
            for p in self.data_dir.glob("*.csv")
        }

        return apply_v1_compatibility_aliases(tables)


# =================================================
# Load Data (local CSV fixture)
# =================================================

tables = CsvSchedulingDataRepository(DATA).load()


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
# Section -> Requirement map (v2 sections carry requirement_id)
# =================================================

section_requirement = {}
for _sid, _srow in sections.items():
    try:
        if "requirement_id" in _srow and pd.notna(_srow["requirement_id"]):
            section_requirement[int(_sid)] = int(_srow["requirement_id"])
    except (ValueError, TypeError):
        pass


# =================================================
# Section Groups
# =================================================

group_links = None
group_summary = None
groups_by_section = {}

if "section_groups" in tables and "student_groups" in tables:
    try:
        _sg = tables["section_groups"][["section_id", "group_id"]].copy()
        group_links = _sg.merge(
            tables["student_groups"][["id"]],
            left_on="group_id",
            right_on="id",
            validate="many_to_one",
            suffixes=("", "_group"),
        )
        for _row in _sg.itertuples():
            groups_by_section.setdefault(int(_row.section_id), set()).add(
                int(_row.group_id)
            )
    except Exception:
        groups_by_section = {}


# =================================================
# Students (authoritative enrollments)
# section_id -> set(student_id) and counts.
# =================================================

students_by_section_ids = {}
students_by_section = {}

try:
    _enr = tables.get("student_section_enrollments")
    _reg = tables.get("student_course_registrations")
    if _enr is not None and _reg is not None:
        _enr_active = _enr[_enr["state"] == "ACTIVE"].copy()
        _reg_map = {
            int(r.id): int(r.student_id) for r in _reg.itertuples()
        }
        for _row in _enr_active.itertuples():
            _sid = int(_row.section_id)
            _student_id = _reg_map.get(int(_row.registration_id))
            if _student_id is None:
                continue
            students_by_section_ids.setdefault(_sid, set()).add(_student_id)
        students_by_section = {
            _sid: len(_s) for _sid, _s in students_by_section_ids.items()
        }
except Exception:
    students_by_section_ids = {}
    students_by_section = {}


# Fallback for v1 fixtures where student_groups carries student_count
if not students_by_section and "student_groups" in tables:
    try:
        if "student_count" in tables["student_groups"].columns:
            _gl = tables["section_groups"].merge(
                tables["student_groups"][["id", "student_count", "name"]],
                left_on="group_id",
                right_on="id",
                validate="many_to_one",
            )
            _gs = (
                _gl.groupby("section_id", as_index=False)
                .agg(group_ids=("group_id", list), student_count=("student_count", "sum"))
            )
            group_summary = _gs
            groups_by_section = {
                int(r.section_id): set(map(int, r.group_ids))
                for r in _gs.itertuples()
            }
            students_by_section = {
                int(r.section_id): int(r.student_count) for r in _gs.itertuples()
            }
    except Exception:
        pass


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
# v1: section_instructors has (section_id, instructor_id, requirement_id)
# v2: section_instructors has (section_id, instructor_id) and the
#     requirement is taken from sections.requirement_id.
# =================================================

eligible = set()
section_instructors_map = {}

_si = tables["section_instructors"]
_has_req = "requirement_id" in _si.columns

for _row in _si.itertuples():
    _sec = int(_row.section_id)
    _ins = int(_row.instructor_id)
    section_instructors_map.setdefault(_sec, set()).add(_ins)
    if _has_req:
        try:
            eligible.add((_sec, int(_row.requirement_id), _ins))
        except (ValueError, TypeError):
            pass
    else:
        _req = section_requirement.get(_sec)
        if _req is not None:
            eligible.add((_sec, int(_req), _ins))


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
# v2 allocations have no requirement_id column;
# it is derived from sections.requirement_id.
# =================================================

allocations = tables["allocations"].copy()

if "requirement_id" not in allocations.columns:
    allocations["requirement_id"] = allocations["section_id"].map(
        section_requirement
    )

allocations = (
    allocations
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
    ] = pd.to_datetime(
        room_closures[
            "starts_at"
        ],
        utc=True
    )

    room_closures[
        "ends_at_ts"
    ] = pd.to_datetime(
        room_closures[
            "ends_at"
        ],
        utc=True
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


# FRESH solver mode for v2: the published baseline stays immutable for
# change validation, but the solver schedules from the DRAFT working
# set only. With no DRAFT version this is empty, so POST /solve
# schedules every section from scratch.
if working_version is not None:

    solver_existing_allocations = (
        working_allocations.copy()
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
        tz="UTC"
    )

    candidate_end = pd.Timestamp(
        f"{session_date} {ends_at}",
        tz="UTC"
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
# Term Readiness Validation
# Runs before solve_schedule(). Incomplete term data is rejected
# here instead of relying on fallbacks during production solving.
# =================================================

class TermNotReadyError(Exception):

    """Raised when a term fails readiness validation."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(
            f"Term is not ready: {len(self.errors)} error(s)"
        )


# Single source of truth for readiness error codes.
READINESS_ERROR_CODES = (
    "MISSING_LECTURE_REQUIREMENT",
    "MISSING_PRACTICAL_REQUIREMENT",
    "DUPLICATE_LECTURE_REQUIREMENT",
    "DUPLICATE_PRACTICAL_REQUIREMENT",
    "MISSING_LECTURE_ENROLLMENT",
    "MISSING_PRACTICAL_ENROLLMENT",
    "DUPLICATE_ACTIVE_COMPONENT_ENROLLMENT",
    "ENROLLMENT_SECTION_MISMATCH",
    "SECTION_REQUIREMENT_MISMATCH",
    "SECTION_WITHOUT_INSTRUCTOR",
    "INVALID_SECTION_CAPACITY",
)


def validate_term_readiness(term_id, tables_override=None):

    source = (
        tables_override
        if tables_override is not None
        else tables
    )

    term_id = int(term_id)
    errors = []

    if "course_session_requirements" in source:
        requirements_df = source["course_session_requirements"]
    else:
        requirements_df = source["session_requirements"]

    sections_df = source["sections"]
    instructors_df = source["section_instructors"]
    registrations_df = source["student_course_registrations"]
    enrollments_df = source["student_section_enrollments"]

    term_reqs = requirements_df[
        requirements_df["term_id"].astype(int) == term_id
    ]

    # -------------------------
    # 1) Every offered course: one LECTURE + one PRACTICAL
    # -------------------------

    for course_id in sorted(term_reqs["course_id"].astype(int).unique()):

        course_reqs = term_reqs[
            term_reqs["course_id"].astype(int) == int(course_id)
        ]

        lectures = course_reqs[course_reqs["kind"] == "LECTURE"]
        practicals = course_reqs[course_reqs["kind"] == "PRACTICAL"]

        if len(lectures) == 0:
            errors.append({
                "code": "MISSING_LECTURE_REQUIREMENT",
                "course_id": int(course_id),
            })
        elif len(lectures) > 1:
            errors.append({
                "code": "DUPLICATE_LECTURE_REQUIREMENT",
                "course_id": int(course_id),
            })

        if len(practicals) == 0:
            errors.append({
                "code": "MISSING_PRACTICAL_REQUIREMENT",
                "course_id": int(course_id),
            })
        elif len(practicals) > 1:
            errors.append({
                "code": "DUPLICATE_PRACTICAL_REQUIREMENT",
                "course_id": int(course_id),
            })

    # -------------------------
    # 2-4) REGISTERED registrations: exactly one ACTIVE
    # LECTURE + one ACTIVE PRACTICAL enrollment
    # -------------------------

    term_regs = registrations_df[
        (
            registrations_df["term_id"].astype(int)
            == term_id
        )
        &
        (
            registrations_df["state"]
            == "REGISTERED"
        )
    ]

    reg_by_id = {
        int(row.id): row
        for row in term_regs.itertuples()
    }

    term_active_enrollments = enrollments_df[
        (
            enrollments_df["term_id"].astype(int)
            == term_id
        )
        &
        (
            enrollments_df["state"]
            == "ACTIVE"
        )
    ]

    enrollments_by_registration = {}
    for row in term_active_enrollments.itertuples():
        enrollments_by_registration.setdefault(
            int(row.registration_id), []
        ).append(row)

    sections_by_id = {
        int(row.id): row
        for row in sections_df.itertuples()
    }

    for registration_id, reg in sorted(reg_by_id.items()):

        student_id = int(reg.student_id)
        course_id = int(reg.course_id)

        active = enrollments_by_registration.get(
            registration_id, []
        )

        for kind, missing_code in (
            ("LECTURE", "MISSING_LECTURE_ENROLLMENT"),
            ("PRACTICAL", "MISSING_PRACTICAL_ENROLLMENT"),
        ):

            component = [
                row for row in active
                if str(row.section_kind) == kind
            ]

            if len(component) == 0:
                errors.append({
                    "code": missing_code,
                    "registration_id": int(registration_id),
                    "student_id": student_id,
                    "course_id": course_id,
                })
            elif len(component) > 1:
                errors.append({
                    "code": (
                        "DUPLICATE_ACTIVE_COMPONENT_ENROLLMENT"
                    ),
                    "registration_id": int(registration_id),
                    "student_id": student_id,
                    "course_id": course_id,
                    "section_kind": kind,
                })

        # -------------------------
        # 3) Each ACTIVE enrollment must point at a Section
        # with matching kind, course and term
        # -------------------------

        for row in active:

            section_id = int(row.section_id)
            section = sections_by_id.get(section_id)

            if (
                section is None
                or str(section.kind)
                != str(row.section_kind)
                or int(section.course_id) != course_id
                or int(section.term_id) != term_id
            ):
                errors.append({
                    "code": "ENROLLMENT_SECTION_MISMATCH",
                    "enrollment_id": int(row.id),
                    "registration_id": int(registration_id),
                    "student_id": student_id,
                    "course_id": course_id,
                    "section_id": section_id,
                })

    # -------------------------
    # 5) Every ACTIVE Section: valid requirement, matching
    # kind, at least one instructor, positive max_capacity
    # -------------------------

    requirements_by_id = {
        int(row.id): row
        for row in term_reqs.itertuples()
    }

    instructor_sections = set(
        instructors_df["section_id"].astype(int).unique()
    )

    has_capacity_column = "max_capacity" in sections_df.columns

    term_sections = sections_df[
        sections_df["term_id"].astype(int) == term_id
    ]

    for row in term_sections.itertuples():

        if str(row.status) != "ACTIVE":
            continue

        section_id = int(row.id)

        try:
            requirement_id = int(row.requirement_id)
        except (ValueError, TypeError):
            requirement_id = None

        requirement = (
            requirements_by_id.get(requirement_id)
            if requirement_id is not None
            else None
        )

        if (
            requirement is None
            or int(requirement.term_id) != term_id
            or int(requirement.course_id) != int(row.course_id)
            or str(requirement.kind) != str(row.kind)
        ):
            errors.append({
                "code": "SECTION_REQUIREMENT_MISMATCH",
                "section_id": section_id,
                "requirement_id": requirement_id,
            })

        if section_id not in instructor_sections:
            errors.append({
                "code": "SECTION_WITHOUT_INSTRUCTOR",
                "section_id": section_id,
            })

        if has_capacity_column:
            try:
                capacity = float(row.max_capacity)
            except (ValueError, TypeError):
                capacity = float("nan")

            if not (capacity == capacity and capacity > 0):
                errors.append({
                    "code": "INVALID_SECTION_CAPACITY",
                    "section_id": section_id,
                })

    return {
        "ready": len(errors) == 0,
        "errors": errors,
    }


def verify_published_immutable():

    if published_version is None:
        return False

    current_published = get_version_allocations(
        int(published_version["id"])
    )

    pd.testing.assert_frame_equal(
        published_snapshot.reset_index(drop=True),
        current_published.reset_index(drop=True),
    )

    return True


# =================================================
# Post-Solve Conflict Scan
# Individual ACTIVE enrollments are authoritative;
# groups are only a fallback when a Section has no
# enrollment data.
# =================================================

def find_schedule_conflicts(schedule_df):

    problems = []

    rows = list(
        schedule_df.itertuples(index=False)
    )

    for i in range(len(rows)):

        first = rows[i]

        for j in range(i + 1, len(rows)):

            second = rows[j]

            if int(first.term_id) != int(second.term_id):
                continue

            if int(first.weekday) != int(second.weekday):
                continue

            if not overlaps(
                minutes(first.starts_at),
                minutes(first.ends_at),
                minutes(second.starts_at),
                minutes(second.ends_at),
            ):
                continue

            reasons = []

            if int(first.room_id) == int(second.room_id):
                reasons.append("ROOM_CONFLICT")

            if int(first.instructor_id) == int(second.instructor_id):
                reasons.append("INSTRUCTOR_CONFLICT")

            if int(first.section_id) == int(second.section_id):
                reasons.append("SECTION_CONFLICT")

            first_students = students_by_section_ids.get(
                int(first.section_id), set()
            )
            second_students = students_by_section_ids.get(
                int(second.section_id), set()
            )

            if first_students and second_students:
                if first_students & second_students:
                    reasons.append("STUDENT_CONFLICT")
            else:
                first_groups = groups_by_section.get(
                    int(first.section_id), set()
                )
                second_groups = groups_by_section.get(
                    int(second.section_id), set()
                )
                if first_groups & second_groups:
                    reasons.append("GROUP_CONFLICT")

            if reasons:
                problems.append({
                    "session_a": first.session_key,
                    "session_b": second.session_key,
                    "reasons": reasons,
                })

    return problems


# =================================================
# Hard Constraint Priority (v2 codes)
# Single source of truth for reason codes + priority.
# =================================================

PRIORITY = [
    "INVALID_SLOT",
    "HOLIDAY",
    "ROOM_CLOSED",
    "INVALID_DURATION",
    "AVAILABILITY_NOT_CONFIRMED",
    "INSTRUCTOR_UNAVAILABLE",
    "ROOM_CONFLICT",
    "INSTRUCTOR_CONFLICT",
    "STUDENT_CONFLICT",
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


    # Section must use its own requirement (v2 sections are bound).
    _section_req = section_requirement.get(section_id)
    if (
        _section_req is not None
        and int(_section_req) != int(requirement_id)
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
                "HOLIDAY"
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
            "INVALID_SLOT"
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


    # Event date must fall on the slot weekday.
    if session_date is not None and matching:
        try:
            _dow = int(pd.Timestamp(session_date).isoweekday())
            if _dow != int(weekday):
                reasons.add("INVALID_SLOT")
        except Exception:
            pass


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
            "INSTRUCTOR_UNAVAILABLE"
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
    # Capacity (authoritative enrollment count)
    # -------------------------

    _enrolled = int(
        students_by_section.get(
            section_id,
            0
        )
    )

    if (
        _enrolled
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

    candidate_students = (
        students_by_section_ids.get(
            section_id,
            set()
        )
    )

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
                "INSTRUCTOR_CONFLICT"
            )


        old_students = (
            students_by_section_ids.get(
                int(
                    old.section_id
                ),
                set()
            )
        )


        # Individual enrollments are authoritative. Only when
        # one or both Sections have no enrollment data may
        # groups be used as a fallback.
        if (
            candidate_students
            and old_students
        ):

            if (
                candidate_students
                & old_students
            ):

                reasons.add(
                    "STUDENT_CONFLICT"
                )

        else:

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
            "STUDENT_CONFLICT"
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
                "INSTRUCTOR_CONFLICT"
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
# Proposal Validator (v2 test-case shape)
# section_id + instructor_id + room_id + slot_id + event_date
# =================================================

def validate_proposal(
    section_id,
    instructor_id,
    room_id,
    slot_id,
    event_date,
    existing=None,
):

    if existing is None:
        existing = allocations

    try:
        slot_id = int(slot_id)
    except (ValueError, TypeError):
        return {
            "feasible": False,
            "primary_result": "INVALID_SLOT",
            "reasons": ["INVALID_SLOT"],
            "slot_id": None,
        }

    if slot_id not in slots:
        return {
            "feasible": False,
            "primary_result": "INVALID_SLOT",
            "reasons": ["INVALID_SLOT"],
            "slot_id": None,
        }

    slot = slots[slot_id]
    term_id = int(slot["term_id"])
    weekday = int(slot["weekday"])

    if int(section_id) not in sections:
        return {
            "feasible": False,
            "primary_result": "INVALID_REFERENCE",
            "reasons": ["INVALID_REFERENCE"],
            "slot_id": int(slot_id),
        }

    requirement_id = section_requirement.get(int(section_id))
    if requirement_id is None:
        return {
            "feasible": False,
            "primary_result": "INVALID_REFERENCE",
            "reasons": ["INVALID_REFERENCE"],
            "slot_id": int(slot_id),
        }

    # Re-scheduling semantics: ignore the section's own existing rows,
    # otherwise every same-slot proposal would self-conflict.
    try:
        _base = existing[
            existing["section_id"].astype(int) != int(section_id)
        ].copy()
    except (KeyError, TypeError):
        _base = existing

    result = check_candidate_strict(
        term_id=term_id,
        section_id=int(section_id),
        requirement_id=int(requirement_id),
        instructor_id=int(instructor_id),
        room_id=int(room_id),
        weekday=weekday,
        starts_at=slot["starts_at"],
        ends_at=slot["ends_at"],
        existing=_base,
        session_date=event_date,
    )

    return {
        "feasible": result["primary_result"] == "FEASIBLE",
        "primary_result": result["primary_result"],
        "reasons": result["reasons"],
        "slot_id": int(slot_id),
        "term_id": term_id,
        "weekday": weekday,
        "requirement_id": int(requirement_id),
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

    requirement_id = section_requirement.get(section_id)
    if requirement_id is None:
        try:
            requirement_id = int(target["requirement_id"])
        except (KeyError, ValueError, TypeError):
            return {
                "status": "BLOCKED",
                "primary_result": "INVALID_REFERENCE",
                "reasons": ["INVALID_REFERENCE"],
            }


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
                "INVALID_SLOT",

            "reasons": [
                "INVALID_SLOT"
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
                "INVALID_SLOT",

            "reasons": [
                "INVALID_SLOT"
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
        requirement_id=int(requirement_id),
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
