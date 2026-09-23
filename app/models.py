from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class SolveRequest(BaseModel):
    term_id: Optional[int] = None


class ProposalInput(BaseModel):
    section_id: int
    instructor_id: int
    room_id: int
    slot_id: int
    event_date: str


class ProposalResponse(BaseModel):
    feasible: bool
    primary_result: str
    reasons: List[str]
    slot_id: Optional[int] = None
    term_id: Optional[int] = None
    weekday: Optional[int] = None
    requirement_id: Optional[int] = None


class ChangeRequest(BaseModel):
    allocation_id: int
    session_date: str

    proposed_room_id: Optional[int] = None
    proposed_instructor_id: Optional[int] = None
    proposed_start_slot_id: Optional[int] = None


class ChangeValidationResponse(BaseModel):
    status: str
    primary_result: Optional[str] = None
    reasons: List[str]

    source_published_version_id: Optional[int] = None
    source_allocation_id: Optional[int] = None
    proposal: Optional[Dict[str, Any]] = None


class ReadinessErrorItem(BaseModel):
    code: str

    registration_id: Optional[int] = None
    student_id: Optional[int] = None
    course_id: Optional[int] = None
    section_id: Optional[int] = None
    requirement_id: Optional[int] = None
    enrollment_id: Optional[int] = None
    section_kind: Optional[str] = None


class TermReadinessResponse(BaseModel):
    term_id: int
    ready: bool
    errors: List[ReadinessErrorItem]
