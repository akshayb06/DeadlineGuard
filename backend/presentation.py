"""Translate backend records into React's contract, keeping legacy receipt keys."""
from datetime import timezone
from models import User, Assignment, UploadSession
import upload_service as svc

def timestamp(value):
    return value.replace(tzinfo=timezone.utc).timestamp()

def upload_view(db, user, session):
    value=svc.get_upload_status(db,user,session.id)
    value.update(id=session.id,expected_hash=session.expected_file_hash,
        expected_size=session.expected_file_size,missing_chunks=value['missing'],
        created_at=timestamp(session.created_at),expires_at=timestamp(session.expires_at))
    return value

def receipt_view(db, sub):
    session=db.get(UploadSession,sub.upload_session_id)
    assignment=db.get(Assignment,sub.assignment_id)
    value=svc.submission_to_dict(sub,session,assignment)
    value.update(id=sub.id,student_id=sub.student_id,assignment_id=sub.assignment_id,
        session_id=sub.upload_session_id,final_hash=sub.final_file_hash,
        submitted_at=timestamp(sub.submitted_at),
        status='on_time' if sub.submission_status=='SUBMITTED_ON_TIME' else 'grace_recovered',
        student=db.get(User,sub.student_id).username,title=assignment.title)
    return value
