from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from database import Base


def utcnow():
    """Current UTC time from the SERVER clock. tzinfo is dropped so SQLite
    stores and returns values in exactly the same (naive-UTC) form."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "student" or "faculty"
    created_at = Column(DateTime, default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    course = Column(String, nullable=False, default='Demo course')
    description = Column(String, default="")
    faculty_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    deadline_at = Column(DateTime, nullable=False)
    recovery_minutes = Column(Integer, default=10)
    max_file_size = Column(Integer, default=25 * 1024 * 1024)
    created_at = Column(DateTime, default=utcnow)


class UploadSession(Base):
    __tablename__ = "upload_sessions"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    original_filename = Column(String, nullable=False)
    expected_file_size = Column(Integer, nullable=False)
    expected_file_hash = Column(String, nullable=False)
    chunk_size = Column(Integer, nullable=False)
    total_chunks = Column(Integer, nullable=False)
    # CREATED -> UPLOADING -> FINALIZING -> COMPLETED  (or EXPIRED / CANCELLED / FAILED)
    status = Column(String, nullable=False, default="CREATED")
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)


class UploadChunk(Base):
    __tablename__ = "upload_chunks"
    id = Column(Integer, primary_key=True)
    upload_session_id = Column(Integer, ForeignKey("upload_sessions.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_hash = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    received_at = Column(DateTime, default=utcnow)
    # the database itself refuses a second row for the same chunk of the same session
    __table_args__ = (UniqueConstraint("upload_session_id", "chunk_index"),)


class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    upload_session_id = Column(Integer, ForeignKey("upload_sessions.id"), nullable=False)
    stored_file_path = Column(String, nullable=False)
    final_file_hash = Column(String, nullable=False)
    submitted_at = Column(DateTime, default=utcnow)
    submission_status = Column(String, nullable=False)  # SUBMITTED_ON_TIME / RECOVERED_WITHIN_GRACE
    # one final submission per student per assignment
    __table_args__ = (UniqueConstraint("student_id", "assignment_id"),)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    upload_session_id = Column(Integer, ForeignKey("upload_sessions.id"), nullable=False)
    event = Column(String, nullable=False)
    detail = Column(String, default="")
    created_at = Column(DateTime, default=utcnow)
