import hashlib
import os
import secrets
from fastapi import Cookie, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import User
from errors import AppError

# token -> user_id. In memory: restarting the server logs everyone out.
SESSIONS = {}


def hash_password(password, salt=None):
    """PBKDF2-SHA256 with a random salt. Returns 'salt$hash' (both hex)."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    salt_hex = stored.split("$")[0]
    attempt = hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(attempt, stored)  # constant-time compare


def create_login_token(user_id):
    token = secrets.token_hex(32)
    SESSIONS[token] = user_id
    return token


def get_current_user(dg_session: str = Cookie(default=None), db: Session = Depends(get_db)):
    """Identify the user from the HTTP-only cookie, never from client-sent IDs."""
    user_id = SESSIONS.get(dg_session)
    if user_id is None:
        raise AppError(401, "Not logged in")
    user = db.get(User, user_id)
    if user is None:
        raise AppError(401, "Not logged in")
    return user


def require_faculty(user: User = Depends(get_current_user)):
    if user.role != "faculty":
        raise AppError(403, "Faculty only")
    return user
