import hashlib
import os
import shutil
from threading import RLock
from pathlib import Path
from sqlalchemy.exc import IntegrityError
from models import Assignment, UploadSession, UploadChunk, Submission, AuditLog, utcnow
from deadline_service import (check_new_session, check_existing_session,
                              session_expiry, classify_submission)
from errors import AppError

STORAGE = Path(os.environ.get("DG_STORAGE", Path(__file__).resolve().parents[1] / 'data' / 'storage')).resolve()
CHUNK_SIZE = 512 * 1024
MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_ACTIVE_SESSIONS = 2
ACTIVE = ["CREATED", "UPLOADING"]
mutation_lock = RLock()  # one local process only; routes serialize mutations


def write_audit(db, session_id, event, detail=""):
    db.add(AuditLog(upload_session_id=session_id, event=event, detail=detail))


def get_owned_session(db, student, session_id):
    session = db.get(UploadSession, session_id)
    # 404 (not 403) so we do not reveal that someone else's session exists
    if session is None or session.student_id != student.id:
        raise AppError(404, "Upload session not found")
    return session


def create_upload_session(db, student, assignment_id, filename, file_size, file_hash):
    if student.role != "student":
        raise AppError(403, "Only students can upload")
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise AppError(404, "Assignment not found")

    allowed, reason = check_new_session(assignment)
    if not allowed:
        raise AppError(403, "Deadline has passed; new uploads are closed", {"reason": reason})

    if file_size <= 0 or file_size > min(MAX_FILE_SIZE, assignment.max_file_size):
        raise AppError(413, "File size is not allowed for this assignment")
    file_hash = file_hash.lower()
    if len(file_hash) != 64 or any(c not in "0123456789abcdef" for c in file_hash):
        raise AppError(400, "file_hash must be a 64-character SHA-256 hex string")

    if db.query(Submission).filter_by(student_id=student.id, assignment_id=assignment_id).first():
        raise AppError(409, "You already have a submission for this assignment")

    # same file again? hand back the unfinished session instead of making a new one
    same = db.query(UploadSession).filter(
        UploadSession.student_id == student.id,
        UploadSession.assignment_id == assignment_id,
        UploadSession.status.in_(ACTIVE),
        UploadSession.expected_file_hash == file_hash,
        UploadSession.expected_file_size == file_size).first()
    if same:
        return same

    active_count = db.query(UploadSession).filter(
        UploadSession.student_id == student.id,
        UploadSession.status.in_(ACTIVE)).count()
    if active_count >= MAX_ACTIVE_SESSIONS:
        raise AppError(429, "Too many unfinished sessions. Resume or cancel one.")

    session = UploadSession(
        student_id=student.id, assignment_id=assignment_id,
        original_filename=os.path.basename(filename)[:200],  # never used as a path
        expected_file_size=file_size, expected_file_hash=file_hash,
        chunk_size=CHUNK_SIZE, total_chunks=(file_size + CHUNK_SIZE - 1) // CHUNK_SIZE,
        status="CREATED", created_at=utcnow(), expires_at=session_expiry(assignment))
    db.add(session)
    db.flush()  # gives the session its id before commit
    write_audit(db, session.id, "SESSION_CREATED", f"{file_size} bytes")
    db.commit()
    return session


def receive_chunk(db, student, session_id, chunk_index, data):
    session = get_owned_session(db, student, session_id)
    if session.status not in ACTIVE:
        raise AppError(409, f"Session is {session.status}")
    assignment = db.get(Assignment, session.assignment_id)
    allowed, reason = check_existing_session(session, assignment)
    if not allowed:
        session.status = "EXPIRED"
        write_audit(db, session.id, "EXPIRED", reason)
        db.commit()
        raise AppError(403, "Recovery window has ended", {"reason": reason})

    if chunk_index < 0 or chunk_index >= session.total_chunks:
        raise AppError(400, "chunk_index out of range")
    if chunk_index == session.total_chunks - 1:
        expected = session.expected_file_size - chunk_index * session.chunk_size
    else:
        expected = session.chunk_size
    if len(data) != expected:
        raise AppError(400, f"Chunk must be exactly {expected} bytes")

    chunk_hash = hashlib.sha256(data).hexdigest()
    old = db.query(UploadChunk).filter_by(
        upload_session_id=session.id, chunk_index=chunk_index).first()
    if old:
        if old.chunk_hash == chunk_hash:  # idempotent: same bytes again is harmless
            return chunk_status(db, session, chunk_index, "already_received")
        raise AppError(409, "Chunk already received with different content")

    folder = STORAGE / "tmp" / str(session.id)
    folder.mkdir(parents=True, exist_ok=True)
    part_path = folder / f"{chunk_index}.part"  # server-made name
    temporary = folder / f'{chunk_index}.tmp'
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(part_path)

    db.add(UploadChunk(upload_session_id=session.id, chunk_index=chunk_index,
                       chunk_hash=chunk_hash, stored_path=str(part_path)))
    session.status = "UPLOADING"
    try:
        db.commit()
    except IntegrityError:  # two identical requests raced; the UNIQUE rule caught it
        db.rollback()
        return chunk_status(db, session, chunk_index, "already_received")
    return chunk_status(db, session, chunk_index, "stored")


def received_indexes(db, session):
    rows = db.query(UploadChunk.chunk_index).filter_by(upload_session_id=session.id).all()
    return sorted(r[0] for r in rows)


def chunk_status(db, session, chunk_index, result):
    return {"chunk_index": chunk_index, "result": result,
            "received_count": len(received_indexes(db, session)),
            "total_chunks": session.total_chunks}


def get_upload_status(db, student, session_id):
    session = get_owned_session(db, student, session_id)
    received = received_indexes(db, session)
    missing = [i for i in range(session.total_chunks) if i not in received]
    return {"session_id": session.id, "status": session.status,
            "assignment_id": session.assignment_id,
            "total_chunks": session.total_chunks, "chunk_size": session.chunk_size,
            "received": received, "missing": missing,
            "expires_at": session.expires_at.isoformat() + "Z"}


def find_active_session(db, student, assignment_id):
    """Lets the frontend recover its session after a refresh."""
    return db.query(UploadSession).filter(
        UploadSession.student_id == student.id,
        UploadSession.assignment_id == assignment_id,
        UploadSession.status.in_(ACTIVE)).first()


def cancel_upload(db, student, session_id):
    session = get_owned_session(db, student, session_id)
    if session.status not in ACTIVE:
        raise AppError(409, f"Session is {session.status}")
    session.status = "CANCELLED"
    write_audit(db, session.id, "CANCELLED")
    db.commit()
    shutil.rmtree(STORAGE / "tmp" / str(session.id), ignore_errors=True)
    return {"status": "CANCELLED"}


def submission_to_dict(sub, session, assignment):
    return {"submission_id": sub.id, "assignment": assignment.title,
            "original_filename": session.original_filename,
            "file_size": session.expected_file_size, "file_hash": sub.final_file_hash,
            "session_created_at": session.created_at.isoformat() + "Z",
            "submitted_at": sub.submitted_at.isoformat() + "Z",
            "classification": sub.submission_status}


def fail_session(db, session, reason, final_path=None):
    if final_path is not None and final_path.exists():
        final_path.unlink()
    session.status = "FAILED"
    write_audit(db, session.id, "FAILED", reason)
    db.commit()
    raise AppError(400, reason)


def finalize_submission(db, student, session_id):
    session = get_owned_session(db, student, session_id)
    assignment = db.get(Assignment, session.assignment_id)

    if session.status == "COMPLETED":  # duplicate request: return the same receipt
        sub = db.query(Submission).filter_by(upload_session_id=session.id).first()
        return submission_to_dict(sub, session, assignment)
    if session.status not in ACTIVE:
        raise AppError(409, f"Session is {session.status}")

    allowed, reason = check_existing_session(session, assignment)
    if not allowed:
        session.status = "EXPIRED"
        write_audit(db, session.id, "EXPIRED", reason)
        db.commit()
        raise AppError(403, "Recovery window has ended", {"reason": reason})

    received = set(received_indexes(db, session))
    missing = [i for i in range(session.total_chunks) if i not in received]
    if missing:
        raise AppError(400, "Some chunks are missing", {"missing": missing})

    session.status = "FINALIZING"
    db.commit()

    final_dir = STORAGE / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_path = final_dir / f"{assignment.id}_{student.id}_{session.id}.pdf"

    hasher = hashlib.sha256()
    with open(final_path, "wb") as out:
        for i in range(session.total_chunks):  # strictly in order
            data = (STORAGE / "tmp" / str(session.id) / f"{i}.part").read_bytes()
            hasher.update(data)
            out.write(data)

    if final_path.stat().st_size != session.expected_file_size:
        fail_session(db, session, "Assembled file size is wrong", final_path)
    if hasher.hexdigest() != session.expected_file_hash:
        fail_session(db, session, "SHA-256 mismatch: file changed or corrupted", final_path)
    with open(final_path, "rb") as f:
        if f.read(4) != b"%PDF":
            fail_session(db, session, "File is not a PDF", final_path)

    from pypdf import PdfReader
    try:
        pdf = PdfReader(final_path, strict=True)
        if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 200:
            raise ValueError('Unsupported PDF')
    except Exception:
        fail_session(db, session, 'Use a readable, unencrypted PDF with 1-200 pages', final_path)
    completed_at = utcnow()
    allowed, reason = check_existing_session(session, assignment, completed_at)
    if not allowed:
        fail_session(db, session, 'Recovery window ended during verification', final_path)

    sub = Submission(student_id=student.id, assignment_id=assignment.id,
                     upload_session_id=session.id, stored_file_path=str(final_path),
                     final_file_hash=hasher.hexdigest(), submitted_at=completed_at,
                     submission_status=classify_submission(assignment, completed_at))
    db.add(sub)
    session.status = "COMPLETED"
    write_audit(db, session.id, "COMPLETED", sub.submission_status)
    try:
        db.commit()  # submission row + COMPLETED status are saved together or not at all
    except IntegrityError:
        db.rollback()
        final_path.unlink(missing_ok=True)
        raise AppError(409, "You already have a submission for this assignment")

    shutil.rmtree(STORAGE / "tmp" / str(session.id), ignore_errors=True)
    return submission_to_dict(sub, session, assignment)
