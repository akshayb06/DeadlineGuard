"""Idempotent setup: invoked on startup or with python seed.py."""
from datetime import timedelta
from database import Base, engine, SessionLocal
from models import User, Assignment, utcnow
from auth import hash_password

def seed_demo():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for name, role in [('faculty1','faculty'),('student1','student'),('student2','student')]:
            if not db.query(User).filter_by(username=name).first():
                db.add(User(username=name,password_hash=hash_password('pass1234'),role=role))
        db.flush()
        faculty=db.query(User).filter_by(username='faculty1').one()
        if not db.query(Assignment).first():
            for title,course,hours in [('Process scheduling analysis','CS204 · Operating Systems',24),
                                      ('Relational database design','CS206 · Database Systems',48),
                                      ('Graph traversal lab report','CS202 · Data Structures',72)]:
                db.add(Assignment(title=title,course=course,description='Demo assignment. Submit your report as one PDF.',
                    faculty_id=faculty.id,deadline_at=utcnow()+timedelta(hours=hours),recovery_minutes=5,max_file_size=25*1024*1024))
        db.commit()

if __name__=='__main__':
    seed_demo()
    print('Users ready: faculty1, student1, student2 (password: pass1234)')
