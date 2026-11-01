CREATE TABLE programs (
    id VARCHAR(16) PRIMARY KEY,
    program_code VARCHAR(16) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    department VARCHAR(80) NOT NULL,
    degree_level VARCHAR(20) NOT NULL CHECK (degree_level IN ('undergraduate', 'graduate')),
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE courses (
    id VARCHAR(16) PRIMARY KEY,
    program_id VARCHAR(16) NOT NULL,
    course_code VARCHAR(24) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    credits INT NOT NULL CHECK (credits BETWEEN 1 AND 6),
    category VARCHAR(20) NOT NULL CHECK (category IN ('required', 'elective')),
    is_elective BOOLEAN NOT NULL,
    max_section_size INT NOT NULL CHECK (max_section_size BETWEEN 1 AND 500),
    popularity_score FLOAT NOT NULL CHECK (popularity_score BETWEEN 0 AND 1),
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_courses_program FOREIGN KEY (program_id) REFERENCES programs(id)
);

CREATE TABLE prerequisites (
    id VARCHAR(16) PRIMARY KEY,
    course_id VARCHAR(16) NOT NULL,
    required_course_id VARCHAR(16) NOT NULL,
    minimum_grade VARCHAR(2) NOT NULL DEFAULT 'D',
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_prerequisites_course_pair UNIQUE (course_id, required_course_id),
    CONSTRAINT ck_prerequisites_no_self CHECK (course_id <> required_course_id),
    CONSTRAINT fk_prerequisites_course FOREIGN KEY (course_id) REFERENCES courses(id),
    CONSTRAINT fk_prerequisites_required FOREIGN KEY (required_course_id) REFERENCES courses(id)
);

CREATE TABLE student_plans (
    id VARCHAR(16) PRIMARY KEY,
    program_id VARCHAR(16) NOT NULL,
    cohort_year INT NOT NULL CHECK (cohort_year BETWEEN 2000 AND 2100),
    entry_term VARCHAR(12) NOT NULL,
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_student_plans_program FOREIGN KEY (program_id) REFERENCES programs(id)
);

CREATE TABLE registration_interests (
    id VARCHAR(24) PRIMARY KEY,
    student_plan_id VARCHAR(16) NOT NULL,
    course_id VARCHAR(16) NOT NULL,
    term_code VARCHAR(12) NOT NULL,
    interest_status VARCHAR(16) NOT NULL
        CHECK (interest_status IN ('interested', 'registered', 'completed', 'waitlisted', 'withdrawn')),
    requested_at DATETIME NOT NULL,
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_registration_student_course_term UNIQUE (student_plan_id, course_id, term_code),
    CONSTRAINT fk_registration_plan FOREIGN KEY (student_plan_id) REFERENCES student_plans(id),
    CONSTRAINT fk_registration_course FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE faculty (
    id VARCHAR(16) PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    department VARCHAR(80) NOT NULL,
    years_experience INT NOT NULL CHECK (years_experience BETWEEN 0 AND 60),
    max_weekly_workload INT NOT NULL CHECK (max_weekly_workload BETWEEN 1 AND 60),
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE faculty_skills (
    id VARCHAR(16) PRIMARY KEY,
    faculty_id VARCHAR(16) NOT NULL,
    course_id VARCHAR(16) NOT NULL,
    proficiency VARCHAR(20) NOT NULL
        CHECK (proficiency IN ('beginner', 'intermediate', 'advanced', 'expert')),
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_faculty_course_skill UNIQUE (faculty_id, course_id),
    CONSTRAINT fk_faculty_skills_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id),
    CONSTRAINT fk_faculty_skills_course FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE availabilities (
    id VARCHAR(24) PRIMARY KEY,
    faculty_id VARCHAR(16) NOT NULL,
    weekday INT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    availability_type VARCHAR(12) NOT NULL CHECK (availability_type IN ('available', 'leave')),
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_availability_faculty_slot UNIQUE (faculty_id, weekday, start_time, effective_from),
    CONSTRAINT ck_availability_time_order CHECK (start_time < end_time),
    CONSTRAINT fk_availabilities_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id)
);

CREATE TABLE rooms (
    id VARCHAR(16) PRIMARY KEY,
    room_code VARCHAR(16) NOT NULL UNIQUE,
    building VARCHAR(80) NOT NULL,
    capacity INT NOT NULL CHECK (capacity BETWEEN 1 AND 1000),
    room_type VARCHAR(20) NOT NULL,
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE sections (
    id VARCHAR(24) PRIMARY KEY,
    course_id VARCHAR(16) NOT NULL,
    room_id VARCHAR(16) NOT NULL,
    term_code VARCHAR(12) NOT NULL,
    section_number INT NOT NULL,
    capacity INT NOT NULL CHECK (capacity BETWEEN 1 AND 1000),
    expected_enrollment INT NOT NULL DEFAULT 0,
    weekday INT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_section_course_term_number UNIQUE (course_id, term_code, section_number),
    CONSTRAINT ck_section_expected_enrollment CHECK (expected_enrollment BETWEEN 0 AND capacity),
    CONSTRAINT ck_section_time_order CHECK (start_time < end_time),
    CONSTRAINT fk_sections_course FOREIGN KEY (course_id) REFERENCES courses(id),
    CONSTRAINT fk_sections_room FOREIGN KEY (room_id) REFERENCES rooms(id)
);

CREATE TABLE workload_assignments (
    id VARCHAR(24) PRIMARY KEY,
    faculty_id VARCHAR(16) NOT NULL,
    section_id VARCHAR(24) NOT NULL,
    weekly_hours FLOAT NOT NULL CHECK (weekly_hours BETWEEN 0 AND 60),
    assignment_status VARCHAR(16) NOT NULL CHECK (assignment_status IN ('assigned', 'unassigned')),
    score FLOAT NULL,
    explanation VARCHAR(500) NULL,
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_workload_faculty_section UNIQUE (faculty_id, section_id),
    CONSTRAINT fk_workload_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id),
    CONSTRAINT fk_workload_section FOREIGN KEY (section_id) REFERENCES sections(id)
);

CREATE TABLE audit_events (
    id VARCHAR(24) PRIMARY KEY,
    entity_type VARCHAR(40) NOT NULL,
    entity_id VARCHAR(40) NOT NULL,
    action VARCHAR(40) NOT NULL,
    details JSON NOT NULL,
    occurred_at DATETIME NOT NULL
);

CREATE TABLE forecast_runs (
    id VARCHAR(24) PRIMARY KEY,
    term_code VARCHAR(12) NOT NULL,
    algorithm VARCHAR(40) NOT NULL,
    metrics JSON NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX ix_forecast_runs_term_code (term_code)
);

CREATE TABLE forecast_results (
    id VARCHAR(32) PRIMARY KEY,
    run_id VARCHAR(24) NOT NULL,
    course_id VARCHAR(16) NOT NULL,
    historical_enrollment INT NOT NULL,
    current_interest INT NOT NULL,
    predicted_enrollment INT NOT NULL,
    uncertainty FLOAT NOT NULL,
    recommended_sections INT NOT NULL,
    expected_unmet_demand INT NOT NULL DEFAULT 0,
    demand_category VARCHAR(12) NOT NULL
        CHECK (demand_category IN ('High', 'Medium', 'Low')),
    explanation JSON NOT NULL,
    CONSTRAINT uq_forecast_run_course UNIQUE (run_id, course_id),
    CONSTRAINT ck_forecast_non_negative CHECK (
        historical_enrollment >= 0 AND current_interest >= 0
        AND predicted_enrollment >= 0 AND uncertainty >= 0
        AND recommended_sections >= 0
    ),
    CONSTRAINT fk_forecast_results_run FOREIGN KEY (run_id) REFERENCES forecast_runs(id),
    CONSTRAINT fk_forecast_results_course FOREIGN KEY (course_id) REFERENCES courses(id),
    INDEX ix_forecast_results_run_id (run_id),
    INDEX ix_forecast_results_course_id (course_id)
);

CREATE TABLE exceptions (
    id VARCHAR(24) PRIMARY KEY,
    entity_id VARCHAR(40) NOT NULL,
    issue_type VARCHAR(48) NOT NULL,
    description VARCHAR(1000) NOT NULL,
    severity VARCHAR(12) NOT NULL
        CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    detected_at DATETIME NOT NULL,
    ground_truth_label BOOLEAN NOT NULL,
    resolution_status VARCHAR(16) NOT NULL DEFAULT 'open'
        CHECK (resolution_status IN ('open', 'in_progress', 'resolved', 'dismissed')),
    source VARCHAR(24) NOT NULL DEFAULT 'validation',
    created_at DATETIME NOT NULL,
    INDEX ix_exceptions_entity_id (entity_id),
    INDEX ix_exceptions_issue_type (issue_type)
);

CREATE TABLE validation_runs (
    id VARCHAR(24) PRIMARY KEY,
    total_checks INT NOT NULL,
    passed_checks INT NOT NULL,
    failed_checks INT NOT NULL,
    warning_count INT NOT NULL,
    validation_status VARCHAR(16) NOT NULL,
    details JSON NOT NULL,
    created_at DATETIME NOT NULL
);
