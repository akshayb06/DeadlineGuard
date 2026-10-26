import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
from models import User
from auth import hash_password
import rate_limiter
from deadline_service import check_new_session, check_existing_session
import upload_service as svc

CHUNK = svc.CHUNK_SIZE


def make_pdf(size):
    from io import BytesIO
    from pypdf import PdfWriter
    padding=max(0,size-900)
    for _ in range(8):
        writer=PdfWriter();writer.add_blank_page(100,100)
        writer.add_attachment('test.bin',b'x'*padding)
        stream=BytesIO();writer.write(stream);data=stream.getvalue()
        if len(data)==size:return data
        padding+=size-len(data)
    raise AssertionError('Could not generate exact-size valid PDF')


def setup_users():
    db = SessionLocal()
    for name, role in [("fac", "faculty"), ("s1", "student"), ("s2", "student")]:
        if not db.query(User).filter_by(username=name).first():
            db.add(User(username=name, password_hash=hash_password("pw"), role=role))
    db.commit()
    db.close()


def login(username):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": username, "password": "pw"}).status_code == 200
    return c


def new_assignment(fac, deadline_delta_min=30, recovery=10):
    dl = datetime.now(timezone.utc) + timedelta(minutes=deadline_delta_min)
    r = fac.post("/api/assignments", json={"title": "A", "deadline_at": dl.isoformat(),
                                           "recovery_minutes": recovery})
    assert r.status_code == 200
    return r.json()["id"]


def start(c, aid, data, name="a.pdf"):
    return c.post("/api/uploads/start", json={"assignment_id": aid, "filename": name,
                  "file_size": len(data), "file_hash": hashlib.sha256(data).hexdigest()})


def put(c, sid, data, i):
    return c.put(f"/api/uploads/{sid}/chunks/{i}", content=data[i * CHUNK:(i + 1) * CHUNK])


def setup_function():
    setup_users()
    rate_limiter.reset()
    rate_limiter.MODE["value"] = "session_aware"


def test_deadline_boundaries():
    dl = datetime(2026, 1, 1, 12, 0)
    a = SimpleNamespace(deadline_at=dl)
    s = SimpleNamespace(expires_at=dl + timedelta(minutes=10))
    assert check_new_session(a, dl - timedelta(seconds=1))[0] is True
    assert check_new_session(a, dl)[0] is False            # exactly at deadline: closed
    assert check_existing_session(s, a, dl + timedelta(minutes=5))[1] == "IN_RECOVERY_WINDOW"
    assert check_existing_session(s, a, dl + timedelta(minutes=11))[0] is False


def test_full_flow_with_interruption_and_resume():
    fac, st = login("fac"), login("s1")
    aid = new_assignment(fac)
    data = make_pdf(int(CHUNK * 2.5))                      # 3 chunks
    sid = start(st, aid, data).json()["session_id"]
    assert put(st, sid, data, 0).json()["result"] == "stored"
    # --- connection "drops" here; browser refreshes and asks what is missing ---
    status = st.get(f"/api/uploads/{sid}/status").json()
    assert status["received"] == [0] and status["missing"] == [1, 2]
    assert st.get(f"/api/uploads/active/{aid}").json()["session_id"] == sid
    assert put(st, sid, data, 0).json()["result"] == "already_received"   # idempotent
    put(st, sid, data, 1); put(st, sid, data, 2)
    r = st.post(f"/api/uploads/{sid}/finalize")
    assert r.status_code == 200 and r.json()["classification"] == "SUBMITTED_ON_TIME"
    assert st.post(f"/api/uploads/{sid}/finalize").json()["submission_id"] == r.json()["submission_id"]
    sub_id = r.json()["submission_id"]
    assert fac.get(f"/api/faculty/submissions").status_code == 200
    assert st.get(f"/api/submissions/{sub_id}/download").content == data


def test_modified_chunk_missing_chunk_and_bad_hash():
    fac, st = login("fac"), login("s2")
    aid = new_assignment(fac)
    data = make_pdf(int(CHUNK * 1.5))
    sid = start(st, aid, data).json()["session_id"]
    put(st, sid, data, 0)
    changed = bytes([data[0] ^ 1]) + data[1:CHUNK]
    assert st.put(f"/api/uploads/{sid}/chunks/0", content=changed).status_code == 409
    assert st.post(f"/api/uploads/{sid}/finalize").status_code == 400      # chunk 1 missing
    assert st.put(f"/api/uploads/{sid}/chunks/1", content=b"x").status_code == 400  # wrong size
    # a corrupted last chunk of the right length -> hash mismatch at finalize
    st.put(f"/api/uploads/{sid}/chunks/1", content=b"\x00" * (len(data) - CHUNK))
    r = st.post(f"/api/uploads/{sid}/finalize")
    assert r.status_code == 400 and "SHA-256" in r.json()["error"]


def test_other_student_and_faculty_routes_blocked():
    fac, s1, s2 = login("fac"), login("s1"), login("s2")
    aid = new_assignment(fac)
    data = make_pdf(1000)
    sid = start(s1, aid, data).json()["session_id"]
    assert s2.get(f"/api/uploads/{sid}/status").status_code == 404
    assert s1.post("/api/assignments", json={"title": "x", "deadline_at": "2030-01-01T00:00:00Z"}).status_code == 403
    assert s1.get("/api/faculty/submissions").status_code == 403


def test_after_deadline_new_session_rejected_and_recovery_window():
    fac, st = login("fac"), login("s1")
    data = make_pdf(1000)
    late = new_assignment(fac, deadline_delta_min=-1)
    assert start(st, late, data).status_code == 403
    # session created before deadline, deadline then passes, still inside recovery window
    aid = new_assignment(fac, deadline_delta_min=30, recovery=10)
    sid = start(st, aid, data).json()["session_id"]
    db = SessionLocal()
    from models import Assignment, UploadSession
    a = db.get(Assignment, aid)
    a.deadline_at = datetime.utcnow() - timedelta(minutes=2)
    s = db.get(UploadSession, sid)
    s.expires_at = a.deadline_at + timedelta(minutes=10)
    db.commit()
    put(st, sid, data, 0)
    r = st.post(f"/api/uploads/{sid}/finalize")
    assert r.json()["classification"] == "RECOVERED_WITHIN_GRACE"
    # a second session whose window already ended
    aid2 = new_assignment(fac)
    sid2 = start(st, aid2, data).json()["session_id"]
    a2 = db.get(Assignment, aid2)
    a2.deadline_at = datetime.utcnow() - timedelta(minutes=20)
    db.get(UploadSession, sid2).expires_at = datetime.utcnow() - timedelta(minutes=10)
    db.commit()
    assert put(st, sid2, data, 0).status_code == 403


def test_session_creation_limited_but_chunks_are_not():
    fac, st = login("fac"), login("s2")
    aids = [new_assignment(fac) for _ in range(5)]
    data = make_pdf(1000)
    codes = []
    for aid in aids:
        r = start(st, aid, data)
        codes.append(r.status_code)
        if r.status_code == 200:
            st.delete(f"/api/uploads/{r.json()['session_id']}")
    assert codes[:3] == [200, 200, 200] and 429 in codes[3:]
    assert "retry-after" in start(st, aids[0], data).headers
    # a different user is unaffected, and many chunk-type requests never hit 429
    s1 = login("s1")
    big = make_pdf(int(CHUNK * 8))
    sid = start(s1, aids[0], big).json()["session_id"]
    for i in range(8):
        assert put(s1, sid, big, i).status_code == 200
    for _ in range(40):
        assert s1.get(f"/api/uploads/{sid}/status").status_code == 200
