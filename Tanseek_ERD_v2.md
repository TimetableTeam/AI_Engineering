# Tanseek v2 — Unified ERD

```mermaid
erDiagram
    DEPARTMENTS ||--o{ ACCOUNTS : employs
    DEPARTMENTS ||--o{ COURSES : owns
    DEPARTMENTS ||--o{ STUDENTS : contains
    ACCOUNTS ||--o| STUDENTS : "student login"
    ACADEMIC_TERMS ||--o{ TIME_SLOTS : defines
    ACADEMIC_TERMS ||--o{ STUDENT_GROUPS : contains
    ACADEMIC_TERMS ||--o{ COURSE_SESSION_REQUIREMENTS : offers

    COURSES ||--o{ COURSE_SESSION_REQUIREMENTS : "has lecture and practical"
    COURSE_SESSION_REQUIREMENTS ||--o{ REQUIRED_EQUIPMENT : requires
    EQUIPMENT ||--o{ REQUIRED_EQUIPMENT : requested
    COURSE_SESSION_REQUIREMENTS ||--o{ SECTIONS : creates
    COURSES ||--o{ SECTIONS : contains

    STUDENTS ||--o{ STUDENT_GROUP_MEMBERS : joins
    STUDENT_GROUPS ||--o{ STUDENT_GROUP_MEMBERS : contains
    STUDENTS ||--o{ STUDENT_COURSE_REGISTRATIONS : registers
    COURSES ||--o{ STUDENT_COURSE_REGISTRATIONS : selected

    STUDENT_GROUPS ||--o{ SECTION_GROUP_ASSIGNMENTS : bulk_assigned
    SECTIONS ||--o{ SECTION_GROUP_ASSIGNMENTS : receives
    STUDENT_COURSE_REGISTRATIONS ||--o{ STUDENT_SECTION_ENROLLMENTS : split_into
    SECTIONS ||--o{ STUDENT_SECTION_ENROLLMENTS : "lecture or practical"

    SECTIONS ||--o{ SECTION_INSTRUCTORS : taught_by
    ACCOUNTS ||--o{ SECTION_INSTRUCTORS : teaches
    ACCOUNTS ||--o{ AVAILABILITY_SUBMISSIONS : submits
    AVAILABILITY_SUBMISSIONS ||--o{ AVAILABILITY_SLOTS : contains
    TIME_SLOTS ||--o{ AVAILABILITY_SLOTS : describes

    ROOMS ||--o{ ROOM_EQUIPMENT : provides
    EQUIPMENT ||--o{ ROOM_EQUIPMENT : installed
    ROOMS ||--o{ ROOM_CLOSURES : unavailable
    ACADEMIC_TERMS ||--o{ SCHEDULE_VERSIONS : versions
    SCHEDULE_VERSIONS ||--o{ ALLOCATIONS : contains
    SECTIONS ||--o{ ALLOCATIONS : scheduled
    ROOMS ||--o{ ALLOCATIONS : hosted_in
    TIME_SLOTS ||--o{ ALLOCATIONS : starts_at

    STUDENTS {
      bigint id PK
      varchar university_id UK
      bigint department_id FK
      bigint account_id FK,UK
      smallint academic_level
      varchar status
    }
    STUDENT_COURSE_REGISTRATIONS {
      bigint id PK
      bigint student_id FK
      bigint course_id FK
      bigint term_id FK
      registration_state state
      bigint registered_by FK
    }
    COURSE_SESSION_REQUIREMENTS {
      bigint id PK
      bigint course_id FK
      bigint term_id FK
      session_kind kind "LECTURE or PRACTICAL"
      int sessions_per_week
      int duration_minutes
      room_kind required_room_kind
    }
    SECTIONS {
      bigint id PK
      bigint course_id FK
      bigint requirement_id FK
      session_kind kind
      varchar code UK
      int max_capacity
    }
    STUDENT_SECTION_ENROLLMENTS {
      bigint id PK
      bigint registration_id FK
      bigint section_id FK
      session_kind section_kind
      enrollment_state state
    }
    STUDENT_GROUPS {
      bigint id PK
      bigint term_id FK
      bigint department_id FK
      varchar name
    }
    SECTION_GROUP_ASSIGNMENTS {
      bigint section_id PK,FK
      bigint group_id PK,FK
      bigint assigned_by FK
    }
    ALLOCATIONS {
      bigint id PK
      bigint version_id FK
      bigint section_id FK
      bigint instructor_id FK
      bigint room_id FK
      bigint start_slot_id FK
      time ends_at
    }
```

## Meaning of the similarly named entities

- `student_groups`: organisational cohorts such as `AI-L3-A`. They help the coordinator assign many students together.
- `sections`: actual teaching streams for one course component, such as `AI301-L1` or `AI301-P2`.
- `section_group_assignments`: a bulk/default mapping from a cohort to a section. The backend expands it into individual enrollments.
- `student_section_enrollments`: the authoritative personal assignment. Every registered student gets one active Lecture section and one active Practical section per course.

The student's timetable is built from `student_section_enrollments -> sections -> allocations`, not from the student's academic level.

Student authentication uses an `ACCOUNTS` row with role `STUDENT`, linked 1:1 through `STUDENTS.account_id`. This role is read-only and can only view its own profile, registrations, section enrollments, and published timetable.
