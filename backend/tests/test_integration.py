"""Exercise the precise JSON contract used by the supplied React screens."""
from pathlib import Path
from datetime import timedelta
import hashlib
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
from models import User, Assignment, UploadSession, utcnow
from auth import hash_password
import rate_limiter

def accounts():
    with SessionLocal() as db:
        for name,role in [('teacher','faculty'),('otherteacher','faculty'),('learner','student'),('outsider','student')]:
            if not db.query(User).filter_by(username=name).first():
                db.add(User(username=name,role=role,password_hash=hash_password('testpass')))
        db.commit()
    rate_limiter.reset()

def signed_in(name):
    client=TestClient(app)
    response=client.post('/api/auth/login',json={'username':name,'password':'testpass'})
    assert response.status_code==200
    return client

def assignment(teacher):
    response=teacher.post('/api/assignments',json={'title':'Integration demo','course':'CS204',
        'description':'Real PDF transfer','deadline_at':(utcnow()+timedelta(minutes=5)).isoformat()+'Z',
        'recovery_minutes':5})
    assert response.status_code==200
    return response.json()['id']

def test_frontend_contract_twenty_mib_resume_and_receipt():
    accounts();teacher=signed_in('teacher');student=signed_in('learner')
    aid=assignment(teacher)
    dashboard=student.get('/api/assignments').json()
    item=next(a for a in dashboard['assignments'] if a['id']==aid)
    assert isinstance(item['deadline_at'],float) and item['course']=='CS204'
    assert item['session'] is None and item['receipt'] is None and dashboard['server_time']>0
    data=student.get('/api/demo-files/20').content
    assert len(data)==20*1024*1024
    digest=hashlib.sha256(data).hexdigest()
    session=student.post('/api/uploads/start',json={'assignment_id':aid,'filename':'demo.pdf',
        'expected_size':len(data),'expected_hash':digest}).json()
    sid=session['id'];size=session['chunk_size']
    assert session['expected_hash']==digest and session['total_chunks']==40
    for i in range(24):
        assert student.put(f'/api/uploads/{sid}/chunks/{i}',content=data[i*size:(i+1)*size]).status_code==200
    status=student.get(f'/api/uploads/{sid}').json()
    assert status['missing_chunks']==list(range(24,40))
    item=next(a for a in student.get('/api/assignments').json()['assignments'] if a['id']==aid)
    assert item['session']['id']==sid and item['session']['missing_chunks']==list(range(24,40))
    with SessionLocal() as db:
        db.get(Assignment,aid).deadline_at=utcnow()-timedelta(seconds=1)
        db.get(UploadSession,sid).expires_at=utcnow()+timedelta(minutes=5)
        db.commit()
    for i in status['missing_chunks']:
        assert student.put(f'/api/uploads/{sid}/chunks/{i}',content=data[i*size:(i+1)*size]).status_code==200
    assert not any(r['assignment_id']==aid for r in student.get('/api/submissions').json())
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda _:student.post(f'/api/uploads/{sid}/finalize'),range(2)))
    assert all(r.status_code==200 for r in responses)
    receipt=responses[0].json()
    assert receipt['id']==responses[1].json()['id'] and receipt['status']=='grace_recovered'
    assert receipt['final_hash']==digest and isinstance(receipt['submitted_at'],float)
    rid=receipt['id']
    assert student.get(f'/api/submissions/{rid}/receipt').json()['id']==rid
    assert teacher.get(f'/api/submissions/{rid}/download').content==data
    other=signed_in('otherteacher');outsider=signed_in('outsider')
    for client in [other,outsider]:
        assert client.get(f'/api/submissions/{rid}/receipt').status_code==404
        assert client.get(f'/api/submissions/{rid}/download').status_code==404
    assert other.get('/api/faculty/submissions').json()==[]
    assert other.get('/api/faculty/analytics').json()['submissions']['total']==0
    assert other.get(f'/api/faculty/audit/{sid}').status_code==404

def test_errors_demo_files_comparison_and_stream_bounds():
    accounts();teacher=signed_in('teacher');student=signed_in('learner')
    assert student.get('/api/demo-files/99').status_code==404
    assert TestClient(app).get('/api/demo-files/5').status_code==401
    assert student.get('/api/comparison').json()['kind']=='limiter_simulation'
    assert len(student.get('/api/comparison').json()['rows'])==3
    aid=assignment(teacher)
    data=student.get('/api/demo-files/5').content
    sid=student.post('/api/uploads/start',json={'assignment_id':aid,'expected_size':len(data),
        'expected_hash':hashlib.sha256(data).hexdigest()}).json()['id']
    response=student.put(f'/api/uploads/{sid}/chunks/0',content=b'x'*(512*1024+1))
    assert response.status_code==413 and 'error' in response.json()
    assert student.delete(f'/api/uploads/{sid}').status_code==200
    assert student.post('/api/auth/logout',headers={'Origin':'https://foreign.example'}).status_code==403
