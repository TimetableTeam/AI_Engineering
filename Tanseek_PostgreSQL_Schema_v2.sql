-- ============================================================
-- TANSEEK v2 | Student-aware timetable and room allocation
-- PostgreSQL 15+
-- Run on an EMPTY database.
-- ============================================================

BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE account_role AS ENUM (
  'SUPER_ADMIN','ADMIN','SCHEDULER','REGISTRATION_OFFICER',
  'DEPARTMENT_COORDINATOR','LAB_MANAGER','LECTURER','TA','STUDENT'
);
CREATE TYPE account_state AS ENUM ('INVITED','ACTIVE','SUSPENDED','DISABLED');
CREATE TYPE term_state AS ENUM ('PLANNING','COLLECTING_AVAILABILITY','READY_TO_SCHEDULE','ACTIVE','ARCHIVED');
CREATE TYPE session_kind AS ENUM ('LECTURE','PRACTICAL');
CREATE TYPE room_kind AS ENUM (
  'LECTURE_HALL','COMPUTER_LAB','GPU_LAB','NETWORK_LAB'
);
CREATE TYPE availability_state AS ENUM ('DRAFT','CONFIRMED');
CREATE TYPE availability_kind AS ENUM ('AVAILABLE','UNAVAILABLE','PREFERRED');
CREATE TYPE registration_state AS ENUM ('REGISTERED','DROPPED','WITHDRAWN','COMPLETED');
CREATE TYPE enrollment_state AS ENUM ('ACTIVE','MOVED','REMOVED');
CREATE TYPE schedule_state AS ENUM ('DRAFT','PUBLISHED','ARCHIVED');

CREATE TABLE departments (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code varchar(30) NOT NULL UNIQUE,
  name varchar(180) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE accounts (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email varchar(254) NOT NULL UNIQUE,
  password_hash varchar(255),
  full_name varchar(180) NOT NULL,
  role account_role NOT NULL,
  state account_state NOT NULL DEFAULT 'INVITED',
  home_department_id bigint REFERENCES departments(id),
  created_by bigint REFERENCES accounts(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (state <> 'ACTIVE' OR password_hash IS NOT NULL)
);

CREATE TABLE account_department_grants (
  account_id bigint NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  department_id bigint NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
  granted_by bigint NOT NULL REFERENCES accounts(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, department_id)
);

CREATE TABLE audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_account_id bigint REFERENCES accounts(id) ON DELETE SET NULL,
  action varchar(120) NOT NULL,
  entity_type varchar(80) NOT NULL,
  entity_id varchar(120),
  department_id bigint REFERENCES departments(id) ON DELETE SET NULL,
  before_data jsonb,
  after_data jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE academic_terms (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name varchar(120) NOT NULL,
  starts_on date NOT NULL,
  ends_on date NOT NULL,
  state term_state NOT NULL DEFAULT 'PLANNING',
  availability_deadline timestamptz,
  created_by bigint REFERENCES accounts(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (starts_on <= ends_on)
);

-- ISO weekday: Monday=1 ... Sunday=7.
CREATE TABLE time_slots (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id bigint NOT NULL REFERENCES academic_terms(id) ON DELETE CASCADE,
  weekday smallint NOT NULL CHECK (weekday BETWEEN 1 AND 7),
  starts_at time NOT NULL,
  ends_at time NOT NULL,
  label varchar(80) NOT NULL,
  CHECK (starts_at < ends_at),
  UNIQUE (term_id, weekday, starts_at),
  UNIQUE (id, term_id)
);

CREATE TABLE term_holidays (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id bigint NOT NULL REFERENCES academic_terms(id) ON DELETE CASCADE,
  holiday_date date NOT NULL,
  reason varchar(180),
  UNIQUE (term_id, holiday_date)
);

CREATE TABLE courses (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  department_id bigint NOT NULL REFERENCES departments(id),
  code varchar(40) NOT NULL,
  title varchar(180) NOT NULL,
  created_by bigint REFERENCES accounts(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (department_id, code),
  UNIQUE (id, department_id)
);

-- Each course/term must have exactly one LECTURE row and one PRACTICAL row.
-- The UNIQUE constraint prevents duplicates; the service validates that both exist
-- before the term becomes READY_TO_SCHEDULE.
CREATE TABLE course_session_requirements (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  course_id bigint NOT NULL REFERENCES courses(id),
  term_id bigint NOT NULL REFERENCES academic_terms(id),
  kind session_kind NOT NULL,
  sessions_per_week integer NOT NULL DEFAULT 1 CHECK (sessions_per_week > 0),
  duration_minutes integer NOT NULL DEFAULT 120 CHECK (duration_minutes > 0),
  required_room_kind room_kind NOT NULL,
  preferred_window_note text,
  created_by bigint NOT NULL REFERENCES accounts(id),
  updated_by bigint REFERENCES accounts(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (course_id, term_id, kind),
  UNIQUE (id, term_id, course_id, kind)
);

CREATE TABLE equipment (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code varchar(60) NOT NULL UNIQUE,
  name varchar(120) NOT NULL UNIQUE
);

CREATE TABLE required_equipment (
  requirement_id bigint NOT NULL REFERENCES course_session_requirements(id) ON DELETE CASCADE,
  equipment_id bigint NOT NULL REFERENCES equipment(id),
  quantity integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
  PRIMARY KEY (requirement_id, equipment_id)
);

-- Students are domain records linked to read-only STUDENT accounts.
-- The scheduling model uses student.id; account_id is only for authentication.
CREATE TABLE students (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  university_id varchar(50) NOT NULL UNIQUE,
  full_name varchar(180) NOT NULL,
  email varchar(254) UNIQUE,
  department_id bigint NOT NULL REFERENCES departments(id),
  academic_level smallint,
  account_id bigint UNIQUE REFERENCES accounts(id) ON DELETE SET NULL,
  status varchar(20) NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE','SUSPENDED','GRADUATED','WITHDRAWN')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, department_id)
);

-- A Student Group is an organisational cohort used for bulk assignment.
CREATE TABLE student_groups (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id bigint NOT NULL REFERENCES academic_terms(id),
  department_id bigint NOT NULL REFERENCES departments(id),
  name varchar(100) NOT NULL,
  UNIQUE (term_id, department_id, name),
  UNIQUE (id, term_id)
);

CREATE TABLE student_group_members (
  group_id bigint NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE,
  student_id bigint NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  joined_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (group_id, student_id)
);

-- Registration Officer registers the student in the course.
CREATE TABLE student_course_registrations (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  student_id bigint NOT NULL REFERENCES students(id),
  course_id bigint NOT NULL REFERENCES courses(id),
  term_id bigint NOT NULL REFERENCES academic_terms(id),
  state registration_state NOT NULL DEFAULT 'REGISTERED',
  registered_by bigint NOT NULL REFERENCES accounts(id),
  registered_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (student_id, course_id, term_id),
  UNIQUE (id, term_id, course_id)
);

-- A Section is a teaching stream for one course component.
-- Examples: AI301-L1 (LECTURE), AI301-P1 (PRACTICAL).
CREATE TABLE sections (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id bigint NOT NULL REFERENCES academic_terms(id),
  course_id bigint NOT NULL REFERENCES courses(id),
  requirement_id bigint NOT NULL,
  kind session_kind NOT NULL,
  code varchar(50) NOT NULL,
  max_capacity integer CHECK (max_capacity IS NULL OR max_capacity > 0),
  status varchar(20) NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE','CANCELLED')),
  created_by bigint REFERENCES accounts(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (requirement_id, term_id, course_id, kind)
    REFERENCES course_session_requirements(id, term_id, course_id, kind),
  UNIQUE (term_id, course_id, code),
  UNIQUE (id, term_id, course_id, kind)
);

-- This is a bulk/default assignment record, not a second kind of group.
-- The service expands active group members into student_section_enrollments.
CREATE TABLE section_group_assignments (
  section_id bigint NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  group_id bigint NOT NULL REFERENCES student_groups(id) ON DELETE RESTRICT,
  assigned_by bigint NOT NULL REFERENCES accounts(id),
  assigned_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (section_id, group_id)
);

-- This table is authoritative for each student's personal timetable.
-- One active LECTURE and one active PRACTICAL enrollment per registration.
CREATE TABLE student_section_enrollments (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  registration_id bigint NOT NULL,
  term_id bigint NOT NULL,
  course_id bigint NOT NULL,
  section_kind session_kind NOT NULL,
  section_id bigint NOT NULL,
  state enrollment_state NOT NULL DEFAULT 'ACTIVE',
  assigned_by bigint NOT NULL REFERENCES accounts(id),
  assigned_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  FOREIGN KEY (registration_id, term_id, course_id)
    REFERENCES student_course_registrations(id, term_id, course_id) ON DELETE CASCADE,
  FOREIGN KEY (section_id, term_id, course_id, section_kind)
    REFERENCES sections(id, term_id, course_id, kind) ON DELETE RESTRICT,
  CHECK ((state = 'ACTIVE' AND ended_at IS NULL) OR state <> 'ACTIVE')
);
CREATE UNIQUE INDEX one_active_section_per_component
  ON student_section_enrollments(registration_id, section_kind)
  WHERE state = 'ACTIVE';
CREATE INDEX student_section_section_idx
  ON student_section_enrollments(section_id) WHERE state = 'ACTIVE';

CREATE TABLE section_instructors (
  section_id bigint NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  instructor_id bigint NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
  assignment_role varchar(20) NOT NULL DEFAULT 'PRIMARY'
    CHECK (assignment_role IN ('PRIMARY','ASSISTANT')),
  PRIMARY KEY (section_id, instructor_id)
);

CREATE TABLE availability_submissions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id bigint NOT NULL REFERENCES academic_terms(id),
  instructor_id bigint NOT NULL REFERENCES accounts(id),
  state availability_state NOT NULL DEFAULT 'DRAFT',
  confirmed_at timestamptz,
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  UNIQUE (term_id, instructor_id),
  UNIQUE (id, term_id),
  CHECK ((state = 'CONFIRMED') = (confirmed_at IS NOT NULL))
);

CREATE TABLE availability_slots (
  submission_id bigint NOT NULL,
  term_id bigint NOT NULL,
  slot_id bigint NOT NULL,
  kind availability_kind NOT NULL,
  PRIMARY KEY (submission_id, slot_id),
  FOREIGN KEY (submission_id, term_id)
    REFERENCES availability_submissions(id, term_id) ON DELETE CASCADE,
  FOREIGN KEY (slot_id, term_id)
    REFERENCES time_slots(id, term_id) ON DELETE CASCADE
);

CREATE TABLE rooms (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  building varchar(120) NOT NULL,
  code varchar(50) NOT NULL,
  kind room_kind NOT NULL,
  capacity integer NOT NULL CHECK (capacity > 0),
  accessible boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  managed_by bigint REFERENCES accounts(id),
  UNIQUE (building, code)
);

CREATE TABLE room_equipment (
  room_id bigint NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  equipment_id bigint NOT NULL REFERENCES equipment(id),
  quantity integer NOT NULL CHECK (quantity > 0),
  PRIMARY KEY (room_id, equipment_id)
);

CREATE TABLE room_closures (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  room_id bigint NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  reason text NOT NULL,
  created_by bigint NOT NULL REFERENCES accounts(id),
  CHECK (starts_at < ends_at)
);

CREATE TABLE schedule_versions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id bigint NOT NULL REFERENCES academic_terms(id),
  version_number integer NOT NULL CHECK (version_number > 0),
  name varchar(120) NOT NULL,
  state schedule_state NOT NULL DEFAULT 'DRAFT',
  created_by bigint NOT NULL REFERENCES accounts(id),
  published_by bigint REFERENCES accounts(id),
  published_at timestamptz,
  UNIQUE (term_id, version_number),
  UNIQUE (id, term_id),
  CHECK ((state = 'PUBLISHED') = (published_at IS NOT NULL))
);
CREATE UNIQUE INDEX one_published_version_per_term
  ON schedule_versions(term_id) WHERE state = 'PUBLISHED';

CREATE TABLE allocations (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id bigint NOT NULL,
  version_id bigint NOT NULL,
  section_id bigint NOT NULL,
  instructor_id bigint NOT NULL REFERENCES accounts(id),
  room_id bigint NOT NULL REFERENCES rooms(id),
  start_slot_id bigint NOT NULL,
  ends_at time NOT NULL,
  created_by bigint NOT NULL REFERENCES accounts(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (version_id, term_id)
    REFERENCES schedule_versions(id, term_id) ON DELETE CASCADE,
  FOREIGN KEY (section_id)
    REFERENCES sections(id),
  FOREIGN KEY (start_slot_id, term_id)
    REFERENCES time_slots(id, term_id),
  FOREIGN KEY (section_id, instructor_id)
    REFERENCES section_instructors(section_id, instructor_id),
  UNIQUE (version_id, section_id, start_slot_id)
);
CREATE INDEX allocations_room_time_idx
  ON allocations(version_id, room_id, start_slot_id);
CREATE INDEX allocations_staff_time_idx
  ON allocations(version_id, instructor_id, start_slot_id);

-- Required service-level checks that span multiple rows:
-- 1) Both LECTURE and PRACTICAL requirements exist for every offered course.
-- 2) Every REGISTERED student has one active LECTURE and one active PRACTICAL section.
-- 3) Active enrollment count <= section.max_capacity and allocated room.capacity.
-- 4) No overlap for room, instructor, or any student enrolled in two sections.
-- 5) Only REGISTRATION_OFFICER registers courses; DEPARTMENT_COORDINATOR assigns sections;
--    SCHEDULER assigns time and room.
-- 6) students.account_id must point to an account whose role is STUDENT;
--    STUDENT endpoints are read-only and filtered by the authenticated student id.

COMMIT;
