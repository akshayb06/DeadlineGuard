from datetime import datetime
import asyncio
import json
import time
from pathlib import Path
from contextlib import asynccontextmanager
from threading import BoundedSemaphore
from fastapi import FastAPI, Depends, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field, AliasChoices
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import User, Assignment, Submission, UploadSession, AuditLog, UploadChunk, utcnow
from errors import AppError
from auth import (verify_password, create_login_token, get_current_user,
                  require_faculty, SESSIONS)
from deadline_service import to_naive_utc
from rate_limiter import check_rate_limit
import upload_service as svc
from presentation import upload_view, receipt_view, timestamp

@asynccontextmanager
async def lifespan(app):
    from seed import seed_demo
    seed_demo()
    yield

app = FastAPI(title="DeadlineGuard", lifespan=lifespan)
Base.metadata.create_all(engine)  # creates tables if they do not exist
transfer_slots = BoundedSemaphore(4)

@app.middleware('http')
async def local_browser_safety(request, call_next):
    allowed={'http://127.0.0.1:8002','http://localhost:8002','http://127.0.0.1:5175','http://localhost:5175'}
    if request.method in {'POST','PUT','DELETE'} and request.headers.get('origin') and request.headers['origin'] not in allowed:
        return JSONResponse({'error':'Request origin not allowed'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control']='no-store'
    return response

@app.get('/api/health')
def health():
    return {'status':'ok','server_time':time.time()}


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    headers = {}
    if "retry_after" in exc.extra:
        headers["Retry-After"] = str(exc.extra["retry_after"])
    return JSONResponse(status_code=exc.status_code,
                        content={"error": exc.message, **exc.extra}, headers=headers)


# ---------- request body shapes (Pydantic validates them automatically) ----------
class LoginBody(BaseModel):
    username: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=1,max_length=128)


class AssignmentBody(BaseModel):
    title: str = Field(min_length=1,max_length=140)
    course: str = Field(default='Demo course',min_length=1,max_length=100)
    description: str = Field(default='',max_length=4000)
    deadline_at: datetime
    recovery_minutes: int = Field(default=5,ge=0,le=60)
    max_file_size: int = Field(default=25*1024*1024,gt=0,le=25*1024*1024)


class StartUploadBody(BaseModel):
    assignment_id: int
    filename: str = Field(default='assignment.pdf',max_length=200)
    file_size: int = Field(validation_alias=AliasChoices('file_size','expected_size'),gt=0,le=25*1024*1024)
    file_hash: str = Field(validation_alias=AliasChoices('file_hash','expected_hash'),pattern=r'^[a-fA-F0-9]{64}$')


def enforce_limit(user, kind):
    allowed, retry_after = check_rate_limit(user.id, kind)
    if not allowed:
        raise AppError(429, "Too many requests", {"retry_after": retry_after})


def iso(dt):
    return dt.isoformat() + "Z"


# ---------- authentication ----------
@app.post("/api/auth/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError(401, "Wrong username or password")
    token = create_login_token(user.id)
    response.set_cookie("dg_session", token, httponly=True, samesite="strict")
    return {"id":user.id,"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(response: Response, user: User = Depends(get_current_user)):
    for token in [t for t, uid in SESSIONS.items() if uid == user.id]:
        del SESSIONS[token]
    response.delete_cookie("dg_session")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


# ---------- assignments ----------
def assignment_to_dict(a):
    return {"id": a.id, "title": a.title, "course":a.course,"description": a.description,
            "deadline_at": iso(a.deadline_at), "recovery_minutes": a.recovery_minutes,
            "max_file_size": a.max_file_size}


@app.post("/api/assignments")
def create_assignment(body: AssignmentBody, faculty: User = Depends(require_faculty),
                      db: Session = Depends(get_db)):
    if body.deadline_at.tzinfo is None:
        raise AppError(422,'Deadline must include a timezone')
    a = Assignment(title=body.title, course=body.course,description=body.description, faculty_id=faculty.id,
                   deadline_at=to_naive_utc(body.deadline_at),
                   recovery_minutes=body.recovery_minutes, max_file_size=body.max_file_size)
    db.add(a)
    db.commit()
    return assignment_to_dict(a)


@app.get("/api/assignments")
def list_assignments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query=db.query(Assignment).order_by(Assignment.deadline_at)
    if user.role=='faculty':
        query=query.filter(Assignment.faculty_id==user.id)
    items=[]
    for a in query:
        item=assignment_to_dict(a)
        sub=db.query(Submission).filter_by(student_id=user.id,assignment_id=a.id).first()
        session=svc.find_active_session(db,user,a.id)
        item.update(deadline_at=timestamp(a.deadline_at),faculty=db.get(User,a.faculty_id).username,
                    receipt=receipt_view(db,sub) if sub else None,
                    session=upload_view(db,user,session) if session else None)
        items.append(item)
    return {'assignments':items,'server_time':time.time()}


# ---------- uploads ----------
@app.post("/api/uploads/start")
def start_upload(body: StartUploadBody, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    with svc.mutation_lock:
        enforce_limit(user, "new_session")
        s = svc.create_upload_session(db, user, body.assignment_id, body.filename, body.file_size, body.file_hash)
        return upload_view(db,user,s)


async def read_chunk_body(request: Request, limit: int):
    data=bytearray()
    async for piece in request.stream():
        if len(data)+len(piece)>limit:
            raise AppError(413,'Chunk too large')
        data.extend(piece)
    return bytes(data)


@app.put("/api/uploads/{session_id}/chunks/{chunk_index}")
async def upload_chunk(session_id: int, chunk_index: int, request: Request,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_limit(user, "other")
    svc.get_owned_session(db,user,session_id)
    if not transfer_slots.acquire(blocking=False):
        raise AppError(429,'Four transfers are already active',{'retry_after':1})
    try:
        try:
            data = await asyncio.wait_for(read_chunk_body(request, svc.CHUNK_SIZE), timeout=30)
        except asyncio.TimeoutError:
            raise AppError(408,'Chunk transfer timed out; resume to retry')
        return await run_in_threadpool(save_chunk,db,user,session_id,chunk_index,data)
    finally:
        transfer_slots.release()

def save_chunk(db,user,session_id,index,data):
    with svc.mutation_lock:
        db.expire_all()
        return svc.receive_chunk(db,user,session_id,index,data)


@app.get("/api/uploads/{session_id}/status")
def upload_status(session_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    enforce_limit(user, "other")
    return upload_view(db,user,svc.get_owned_session(db,user,session_id))


@app.get("/api/uploads/active/{assignment_id}")
def active_upload(assignment_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    s = svc.find_active_session(db, user, assignment_id)
    return {"session_id": s.id if s else None}


@app.post("/api/uploads/{session_id}/finalize")
def finalize(session_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    enforce_limit(user, "other")
    with svc.mutation_lock:
        svc.finalize_submission(db, user, session_id)
        sub=db.query(Submission).filter_by(upload_session_id=session_id).one()
        return receipt_view(db,sub)


@app.delete("/api/uploads/{session_id}")
def cancel(session_id: int, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    enforce_limit(user, "other")
    with svc.mutation_lock:
        return svc.cancel_upload(db, user, session_id)


# ---------- submissions ----------
@app.get("/api/submissions/me")
def my_submissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Submission).filter_by(student_id=user.id).all()
    return [{"submission_id": r.id, "assignment_id": r.assignment_id,
             "submitted_at": iso(r.submitted_at), "classification": r.submission_status}
            for r in rows]


@app.get("/api/submissions/{submission_id}/download")
def download(submission_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    sub = authorized_submission(db,user,submission_id)
    return FileResponse(sub.stored_file_path, media_type="application/pdf",
                        filename=f"submission_{sub.id}.pdf")


@app.get("/api/faculty/submissions")
def faculty_submissions(assignment_id: int = None, status: str = None,
                        faculty: User = Depends(require_faculty), db: Session = Depends(get_db)):
    q = db.query(Submission).join(Assignment).filter(Assignment.faculty_id==faculty.id)
    if assignment_id is not None:
        q = q.filter(Assignment.id==assignment_id)
    if status is not None:
        q = q.filter(Submission.submission_status == status)
    return [{"submission_id": r.id, "student_id": r.student_id,
             "assignment_id": r.assignment_id, "submitted_at": iso(r.submitted_at),
             "classification": r.submission_status, "session_id": r.upload_session_id} for r in q]


@app.get("/api/faculty/audit/{session_id}")
def audit(session_id: int, faculty: User = Depends(require_faculty),
          db: Session = Depends(get_db)):
    session=db.get(UploadSession,session_id)
    if not session or db.get(Assignment,session.assignment_id).faculty_id!=faculty.id:
        raise AppError(404,'Upload session not found')
    rows = db.query(AuditLog).filter_by(upload_session_id=session_id).order_by(AuditLog.id)
    return [{"event": r.event, "detail": r.detail, "at": iso(r.created_at)} for r in rows]


@app.get("/api/faculty/analytics")
def faculty_analytics(faculty: User = Depends(require_faculty), db: Session = Depends(get_db)):
    from sqlalchemy import func
    total_submissions = db.query(func.count(Submission.id)).join(Assignment).filter(Assignment.faculty_id == faculty.id).scalar() or 0
    on_time = db.query(func.count(Submission.id)).join(Assignment).filter(Assignment.faculty_id == faculty.id).filter(Submission.submission_status == "SUBMITTED_ON_TIME").scalar() or 0
    recovered = db.query(func.count(Submission.id)).join(Assignment).filter(Assignment.faculty_id == faculty.id).filter(Submission.submission_status == "RECOVERED_WITHIN_GRACE").scalar() or 0
    total_sessions = db.query(func.count(UploadSession.id)).join(Assignment).filter(Assignment.faculty_id == faculty.id).scalar() or 0
    completed = db.query(func.count(UploadSession.id)).join(Assignment).filter(Assignment.faculty_id == faculty.id).filter(UploadSession.status=="COMPLETED").scalar() or 0
    expired = db.query(func.count(UploadSession.id)).join(Assignment).filter(Assignment.faculty_id == faculty.id).filter(UploadSession.status=="EXPIRED").scalar() or 0
    failed = db.query(func.count(UploadSession.id)).join(Assignment).filter(Assignment.faculty_id == faculty.id).filter(UploadSession.status=="FAILED").scalar() or 0
    cancelled = db.query(func.count(UploadSession.id)).join(Assignment).filter(Assignment.faculty_id == faculty.id).filter(UploadSession.status=="CANCELLED").scalar() or 0
    return {
        "submissions": {"total": total_submissions, "on_time": on_time, "recovered_within_grace": recovered},
        "sessions": {"total": total_sessions, "completed": completed, "expired": expired, "failed": failed, "cancelled": cancelled}
    }


@app.get("/api/faculty/sessions")
def faculty_sessions(assignment_id: int = None, status: str = None,
                     faculty: User = Depends(require_faculty), db: Session = Depends(get_db)):
    q = db.query(UploadSession).join(Assignment).filter(Assignment.faculty_id==faculty.id)
    if assignment_id is not None:
        q = q.filter(Assignment.id==assignment_id)
    if status is not None:
        q = q.filter(UploadSession.status==status)
    sessions = q.order_by(UploadSession.created_at.desc()).all()
    result = []
    for s in sessions:
        received = db.query(UploadChunk).filter_by(upload_session_id=s.id).count()
        result.append({
            "session_id": s.id,
            "student_id": s.student_id,
            "assignment_id": s.assignment_id,
            "filename": s.original_filename,
            "status": s.status,
            "total_chunks": s.total_chunks,
            "received_chunks": received,
            "file_size": s.expected_file_size,
            "created_at": iso(s.created_at),
            "expires_at": iso(s.expires_at),
        })
    return result


# React compatibility routes. Legacy /status and /submissions/me still work.
@app.get('/api/uploads/{session_id}')
def session_for_frontend(session_id: int, user: User=Depends(get_current_user), db: Session=Depends(get_db)):
    return upload_view(db,user,svc.get_owned_session(db,user,session_id))

@app.get('/api/submissions')
def submissions_for_frontend(user: User=Depends(get_current_user), db: Session=Depends(get_db)):
    query=db.query(Submission)
    if user.role=='faculty':
        query=query.join(Assignment).filter(Assignment.faculty_id==user.id)
    else:
        query=query.filter(Submission.student_id==user.id)
    return [receipt_view(db,row) for row in query.order_by(Submission.submitted_at.desc())]

def authorized_submission(db,user,submission_id):
    sub=db.get(Submission,submission_id)
    if not sub:
        raise AppError(404,'Submission not found')
    owns_assignment=user.role=='faculty' and db.get(Assignment,sub.assignment_id).faculty_id==user.id
    if sub.student_id!=user.id and not owns_assignment:
        raise AppError(404,'Submission not found')
    return sub

@app.get('/api/submissions/{submission_id}/receipt')
def receipt_download(submission_id: int,user: User=Depends(get_current_user),db: Session=Depends(get_db)):
    value=receipt_view(db,authorized_submission(db,user,submission_id))
    return Response(json.dumps(value,indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="receipt-{submission_id}.json"'})

@app.get('/api/demo-files/{size}')
def demo_file(size:int,user:User=Depends(get_current_user)):
    if size not in {5,20}:
        raise AppError(404,'Sample not found')
    path=Path(__file__).resolve().parents[1]/'samples'/f'demo-assignment-{size}mib.pdf'
    return FileResponse(path,filename=path.name,media_type='application/pdf')

@app.get('/api/comparison')
def comparison(user:User=Depends(get_current_user)):
    from experiments.compare_limiters import run_comparison
    return run_comparison()

dist=Path(__file__).resolve().parents[1]/'frontend'/'dist'
if dist.exists():
    app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
