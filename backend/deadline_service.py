from datetime import timedelta, timezone
from models import utcnow


def to_naive_utc(dt):
    """Convert any incoming datetime to naive UTC so all comparisons match."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def session_expiry(assignment):
    """Last moment a session created before the deadline may still finish."""
    return assignment.deadline_at + timedelta(minutes=assignment.recovery_minutes)


def check_new_session(assignment, now=None):
    """May a NEW upload session start? Only strictly before the deadline."""
    now = now or utcnow()
    if now < assignment.deadline_at:
        return True, "BEFORE_DEADLINE"
    return False, "DEADLINE_PASSED"


def check_existing_session(session, assignment, now=None):
    """May an EXISTING session keep uploading / finalize?"""
    now = now or utcnow()
    if now < assignment.deadline_at:
        return True, "BEFORE_DEADLINE"
    if now < session.expires_at:
        return True, "IN_RECOVERY_WINDOW"
    return False, "RECOVERY_EXPIRED"


def classify_submission(assignment, now=None):
    """Label decided at finalization time, using the server clock."""
    now = now or utcnow()
    if now < assignment.deadline_at:
        return "SUBMITTED_ON_TIME"
    return "RECOVERED_WITHIN_GRACE"
