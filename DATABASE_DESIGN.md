> Supplied background document. For the combined build, INTEGRATION_NOTES.md and VALIDATION.md supersede conflicting API, limit, or test details below.

# Database Design

## ER Diagram (textual)

```
users (1)----< assignments
  |                |
  |                |
  v                v
upload_sessions > submissions
  |                ^
  v                |
upload_chunks       |
  |                |
  v                |
audit_log           |
                    |
                  (FKs)
```

## Tables

### users
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | User ID |
| username | String | UNIQUE, NOT NULL | Login username |
| password_hash | String | NOT NULL | PBKDF2 hash (salt$hash) |
| role | String | NOT NULL | "student" or "faculty" |
| created_at | DateTime | DEFAULT utcnow() | Creation time (naive UTC) |

### assignments
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Assignment ID |
| title | String | NOT NULL | Assignment title |
| description | String | DEFAULT "" | Description |
| faculty_id | Integer | FK(users.id), NOT NULL | Creating faculty |
| deadline_at | DateTime | NOT NULL | Deadline (naive UTC) |
| recovery_minutes | Integer | DEFAULT 10 | Recovery window in minutes |
| max_file_size | Integer | DEFAULT 10MB | Max file size in bytes |
| created_at | DateTime | DEFAULT utcnow() | Creation time |

### upload_sessions
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Session ID |
| student_id | Integer | FK(users.id), NOT NULL | Student owner |
| assignment_id | Integer | FK(assignments.id), NOT NULL | Target assignment |
| original_filename | String | NOT NULL | Original filename (basename only) |
| expected_file_size | Integer | NOT NULL | Expected file size |
| expected_file_hash | String | NOT NULL | Expected SHA-256 hex |
| chunk_size | Integer | NOT NULL | Chunk size (512KB) |
| total_chunks | Integer | NOT NULL | Total number of chunks |
| status | String | NOT NULL, DEFAULT "CREATED" | CREATED/UPLOADING/FINALIZING/COMPLETED/EXPIRED/CANCELLED/FAILED |
| created_at | DateTime | DEFAULT utcnow() | Creation time |
| expires_at | DateTime | NOT NULL | deadline_at + recovery_minutes |

### upload_chunks
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Chunk ID |
| upload_session_id | Integer | FK(upload_sessions.id), NOT NULL | Parent session |
| chunk_index | Integer | NOT NULL | Chunk index (0-based) |
| chunk_hash | String | NOT NULL | SHA-256 of chunk bytes |
| stored_path | String | NOT NULL | Path to stored .part file |
| received_at | DateTime | DEFAULT utcnow() | Receipt time |

**Constraints:** UNIQUE(upload_session_id, chunk_index)

### submissions
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Submission ID |
| student_id | Integer | FK(users.id), NOT NULL | Student |
| assignment_id | Integer | FK(assignments.id), NOT NULL | Assignment |
| upload_session_id | Integer | FK(upload_sessions.id), NOT NULL | Source session |
| stored_file_path | String | NOT NULL | Path to final PDF |
| final_file_hash | String | NOT NULL | Final SHA-256 hash |
| submitted_at | DateTime | DEFAULT utcnow() | Submission time |
| submission_status | String | NOT NULL | SUBMITTED_ON_TIME or RECOVERED_WITHIN_GRACE |

**Constraints:** UNIQUE(student_id, assignment_id) - one final submission per student per assignment

### audit_log
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Log entry ID |
| upload_session_id | Integer | FK(upload_sessions.id), NOT NULL | Related session |
| event | String | NOT NULL | Event type |
| detail | String | DEFAULT "" | Event details |
| created_at | DateTime | DEFAULT utcnow() | Event time |

## Notes
- All foreign keys are used
- Timestamps are naive UTC for SQLite consistency
- Unique constraints prevent duplicate chunks and duplicate submissions
