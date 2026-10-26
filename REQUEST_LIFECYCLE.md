> Supplied background document. For the combined build, INTEGRATION_NOTES.md and VALIDATION.md supersede conflicting API, limit, or test details below.

# Request Lifecycle

## Upload Start Flow
1. Client computes SHA-256 of file using Web Crypto, sends `POST /api/uploads/start` with assignment_id, filename, file_size, file_hash
2. `main.py` calls `enforce_limit(user, "new_session")` - checks session-aware rate limiter (3/min)
3. `upload_service.create_upload_session()` validates: role is student, assignment exists, `check_new_session()` allows (before deadline), file size/hash valid, no existing submission for assignment, reuses same-file unfinished session if exists, enforces max 2 active sessions
4. Creates UploadSession with expires_at = deadline + recovery_minutes, writes audit log, returns session details
5. Client receives session_id, chunk_size, total_chunks

## Chunk Upload Flow
1. Client splits file into 512 KB chunks, sends `PUT /api/uploads/{id}/chunks/{index}` with raw chunk bytes
2. `main.py` calls `enforce_limit(user, "other")` - not rate limited in session-aware mode
3. `upload_service.receive_chunk()` validates ownership (404 if not), session status active, `check_existing_session()` allows (deadline or recovery window), chunk index in range, exact chunk size
4. Computes chunk SHA-256, checks for existing chunk with same index - if same hash returns already_received (idempotent), if different hash returns 409
5. Writes chunk to `storage/tmp/{session_id}/{chunk_index}.part`, adds UploadChunk record, sets session status to UPLOADING
6. UNIQUE constraint guards against races

## Resume After Disconnect/Refresh
1. Client calls `GET /api/uploads/active/{assignment_id}` to find unfinished session
2. Client re-selects same file, calls start_upload again - service finds existing same-file active session and returns it
3. Client calls `GET /api/uploads/{id}/status` to get received/missing chunks
4. Client only uploads missing chunks
5. Continues with finalize

## Finalize Flow
1. Client sends `POST /api/uploads/{id}/finalize`
2. `enforce_limit(user, "other")` - not rate limited
3. `upload_service.finalize_submission()` checks if already COMPLETED returns existing receipt (idempotent)
4. Validates session active, `check_existing_session()` allows, all chunks present
5. Sets status to FINALIZING, assembles chunks in order into `storage/final/{assignment_id}_{student_id}_{session_id}.pdf`, computes SHA-256
6. Validates assembled size matches expected, SHA-256 matches expected_file_hash, file starts with `%PDF`
7. Creates Submission record, sets session status to COMPLETED, writes audit log - all in one commit
8. Deletes temp chunks, returns receipt with classification (SUBMITTED_ON_TIME or RECOVERED_WITHIN_GRACE)
9. If any validation fails, calls `fail_session()` which marks FAILED, cleans up files, raises error

## Rate Limiting
- **Session-aware (default)**: Only "new_session" kind checked against session_limiter (3/min). "other" kind returns True.
- **Naive**: All requests checked against naive_limiter.
