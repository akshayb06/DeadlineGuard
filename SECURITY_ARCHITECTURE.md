> Supplied background document. For the combined build, INTEGRATION_NOTES.md and VALIDATION.md supersede conflicting API, limit, or test details below.

# Security Architecture

## Authentication
- **Password hashing**: PBKDF2-SHA256 with 200000 iterations, random 16-byte salt per password
- **Password verification**: `secrets.compare_digest` for constant-time comparison
- **Session tokens**: 256-bit cryptographically random tokens (`secrets.token_hex(32)`)
- **Token storage**: In-memory server-side dict (token -> user_id). Tokens never stored in database.
- **Cookies**: HTTP-only, samesite=lax. No secure flag for local HTTP development.
- **User lookup**: Always fetched from database by ID from session, never trusted from client

## Authorization
- **Role-based access**: student and faculty roles
- **Route protection**: `get_current_user` for authenticated routes, `require_faculty` for faculty routes
- **Resource ownership**: `get_owned_session()` verifies session belongs to current student; returns 404 (not 403) to prevent resource enumeration
- **Submission access**: Students can only download own submissions, faculty can download any
- **Assignment creation**: Faculty only

## Input Validation
- **Request bodies**: Validated by Pydantic models
- **File hash**: Must be 64 hex characters (SHA-256)
- **File size**: Checked against limits (global and per-assignment)
- **Chunk validation**: Index in range, exact byte size (last chunk may be partial)
- **Chunk content**: SHA-256 computed and checked on re-upload
- **PDF validation**: Magic bytes check for `%PDF`

## Integrity & Trust
- **Server clock only**: All deadline/recovery checks use server time via `utcnow()`
- **Server-side assembly**: Chunks assembled server-side in order, never trusted from client
- **Hash verification**: Server recomputes SHA-256 after assembly and compares to hash sent at start
- **No client-trusted values**: Student ID, timestamps, file paths never trusted from client
- **No public static serving**: Uploads stored outside web root in `storage/` directory

## Race Condition Protection
- **UNIQUE constraint**: `upload_chunks` has UNIQUE(upload_session_id, chunk_index) - database enforces
- **IntegrityError handling**: Catches race conditions on chunk upload and treats as already_received
- **Submission uniqueness**: UNIQUE(student_id, assignment_id) prevents duplicate submissions
- **Atomic commits**: Submission creation and session status update committed together

## Rate Limiting
- **Session-aware**: Separates new session creation (limited) from continuation (unlimited by this limiter)
- **Sliding window**: Prevents burst attacks
- **Per-user limiting**: Keyed by user_id

## Known Security Limitations (by design)
- In-memory tokens lost on server restart
- No CSRF protection (deferred as per requirements)
- No token expiration/rotation
- Rate limiter not distributed (single process)
- No HTTPS enforcement (local development)
