"""Term readiness validation tests (uses validate_term_readiness)."""

from app.engine import validate_term_readiness


def codes(result):
    return [error["code"] for error in result["errors"]]


def test_term_readiness_valid(readiness_tables):
    result = validate_term_readiness(1, readiness_tables)
    assert result["ready"] is True
    assert result["errors"] == []


def test_missing_lecture_requirement(readiness_tables):
    reqs = readiness_tables["course_session_requirements"]
    readiness_tables["course_session_requirements"] = reqs[reqs["id"] != 1]
    result = validate_term_readiness(1, readiness_tables)
    assert result["ready"] is False
    assert "MISSING_LECTURE_REQUIREMENT" in codes(result)


def test_missing_practical_requirement(readiness_tables):
    reqs = readiness_tables["course_session_requirements"]
    readiness_tables["course_session_requirements"] = reqs[reqs["id"] != 2]
    result = validate_term_readiness(1, readiness_tables)
    assert result["ready"] is False
    assert "MISSING_PRACTICAL_REQUIREMENT" in codes(result)


def _drop_first_active_enrollment(readiness_tables, kind):
    enrollments = readiness_tables["student_section_enrollments"]
    mask = (enrollments["state"] == "ACTIVE") & (
        enrollments["section_kind"] == kind
    )
    drop_id = enrollments[mask].iloc[0]["id"]
    readiness_tables["student_section_enrollments"] = enrollments[
        enrollments["id"] != drop_id
    ]
    registration_id = int(enrollments[mask].iloc[0]["registration_id"])
    return registration_id


def test_missing_lecture_enrollment(readiness_tables):
    registration_id = _drop_first_active_enrollment(
        readiness_tables, "LECTURE"
    )
    result = validate_term_readiness(1, readiness_tables)
    assert result["ready"] is False
    matches = [
        error
        for error in result["errors"]
        if error["code"] == "MISSING_LECTURE_ENROLLMENT"
        and error["registration_id"] == registration_id
    ]
    assert matches


def test_missing_practical_enrollment(readiness_tables):
    registration_id = _drop_first_active_enrollment(
        readiness_tables, "PRACTICAL"
    )
    result = validate_term_readiness(1, readiness_tables)
    assert result["ready"] is False
    matches = [
        error
        for error in result["errors"]
        if error["code"] == "MISSING_PRACTICAL_ENROLLMENT"
        and error["registration_id"] == registration_id
    ]
    assert matches


def test_duplicate_active_component_enrollment(readiness_tables):
    import pandas as pd

    enrollments = readiness_tables["student_section_enrollments"]
    active = enrollments[enrollments["state"] == "ACTIVE"]
    duplicate = active[active["section_kind"] == "LECTURE"].iloc[[0]].copy()
    duplicate["id"] = int(enrollments["id"].max()) + 1
    readiness_tables["student_section_enrollments"] = pd.concat(
        [enrollments, duplicate], ignore_index=True
    )
    result = validate_term_readiness(1, readiness_tables)
    assert result["ready"] is False
    assert "DUPLICATE_ACTIVE_COMPONENT_ENROLLMENT" in codes(result)


def test_enrollment_section_mismatch(readiness_tables):
    enrollments = readiness_tables["student_section_enrollments"].copy()
    first = enrollments[
        (enrollments["state"] == "ACTIVE")
        & (enrollments["section_kind"] == "LECTURE")
    ].iloc[0]
    # Point a LECTURE enrollment at a PRACTICAL section of another course.
    enrollments.loc[enrollments["id"] == first["id"], "section_id"] = 2
    readiness_tables["student_section_enrollments"] = enrollments
    result = validate_term_readiness(1, readiness_tables)
    assert result["ready"] is False
    assert "ENROLLMENT_SECTION_MISMATCH" in codes(result)
