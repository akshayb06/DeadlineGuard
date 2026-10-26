> Supplied background document. For the combined build, INTEGRATION_NOTES.md and VALIDATION.md supersede conflicting API, limit, or test details below.

# Backend Explained

This document explains the backend implementation of DeadlineGuard as it exists.

## Architecture

The backend follows a layered structure:
- `main.py` - Routes only, no business logic
- `models.py` - SQLAlchemy models and database schema
- `database.py` - Database connection setup
- `auth.py` - Authentication and authorization
- `deadline_service.py` - Deadline and time logic
- `rate_limiter.py` - Rate limiting
- `upload_service.py` - Upload business logic
- `errors.py` - Error handling
- `seed.py` - Test data seeding

## Module Details

### database.py
- Uses SQLite with `check_same_thread=False` for FastAPI compatibility
- `get_db()` dependency provides per-request sessions with automatic cleanup

### models.py
All timestamps use `utcnow()` which returns naive UTC (tzinfo removed) for consistent SQLite storage.

**Tables:**
- `users`: id, username (unique), password_hash, role (student/faculty), created_at
- `assignments`: id, title, description, faculty_id, deadline_at, recovery_minutes, max_file_size, created_at
- `upload_sessions`: id, student_id, assignment_id, original_filename, expected_file_size, expected_file_hash, chunk_size, total_chunks, status, created_at, expires_at
- `upload_chunks`: id, upload_session_id, chunk_index, chunk_hash, stored_path, received_at. UNIQUE(upload_session_id, chunk_index)
- `submissions`: id, student_id, assignment_id, upload_session_id, stored_file_path, final_file_hash, submitted_at, submission_status. UNIQUE(student_id, assignment_id)
- `audit_log`: id, upload_session_id, event, detail, created_at

**Session states:** CREATED, UPLOADING, FINALIZING, COMPLETED, EXPIRED, CANCELLED, FAILED

### auth.py
- Passwords hashed with PBKDF2-SHA256 (200000 iterations), random salt per password, stored as `salt$hash`
- Password verification uses `secrets.compare_digest` for constant-time comparison
- Login tokens are 256-bit random hex strings stored in in-memory `SESSIONS` dict (token -> user_id)
- Cookies are HTTP-only with samesite=lax
- `get_current_user` never trusts client-sent user IDs
- `require_faculty` enforces role check

### deadline_service.py
All times are compared in naive UTC using server clock.

- `check_new_session()`: Returns True only if `now < deadline_at` (strictly before)
- `check_existing_session()`: Returns True if before deadline OR in recovery window (`now < expires_at`)
- `classify_submission()`: "SUBMITTED_ON_TIME" if finalized before deadline, else "RECOVERED_WITHIN_GRACE"
- `session_expiry()`: `deadline_at + recovery_minutes`

### rate_limiter.py
Sliding window rate limiter using `collections.deque` and monotonic time.

- **Session-aware mode (default)**: Only `kind="new_session"` counted against 3 req/min limit. All other requests allowed.
- **Naive mode**: All requests counted against limit.

### upload_service.py
Core upload logic with security checks at every step.

**Key behaviors:**
- Ownership checked via `get_owned_session()` returning 404 for non-owners (prevents enumeration)
- Same-file unfinished sessions are reused (resume shortcut)
- Max 2 active sessions per student
- Chunks validated for index range and exact size
- Idempotent chunk re-uploads with same content; different content rejected with 409
- UNIQUE constraint on (session_id, chunk_index) prevents race conditions
- Assembly in strict index order
- Final validation: file size, SHA-256 hash, PDF magic bytes (%PDF)
- Idempotent finalize returns existing receipt if already completed
- Submission and session status committed atomically
- All events logged to audit_log

### main.py
Routes only - all business logic delegated to service modules. Uses Pydantic for request validation. AppError exceptions converted to JSON responses with appropriate status codes.
