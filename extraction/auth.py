"""Authentication + multi-tenancy (Phase A7).

Replaces the demo DEMO_USERS/_TOKENS shim with real identity:
- bcrypt-hashed passwords in the `users` table,
- stateless JWTs (so tokens work across any number of API instances — the old
  in-memory _TOKENS dict did not),
- a `current_user` FastAPI dependency; endpoints scope data by the user's
  hospital_id.
"""

import os
import time

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db
from logging_setup import get_logger
from models import Hospital, User

log = get_logger("auth")

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-change-me")
JWT_ALG = "HS256"
JWT_TTL = int(os.environ.get("JWT_TTL_SECONDS", str(12 * 3600)))   # 12h


# --- passwords -------------------------------------------------------------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


# --- tokens ----------------------------------------------------------------
def create_token(user: User) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user.id), "email": user.email, "name": user.name,
        "hospital_id": user.hospital_id, "role": user.role,
        "iat": now, "exp": now + JWT_TTL,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except Exception:
        return None


def _user_from_token(token: str, db: Session) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "user not found")
    return user


def get_current_user(authorization: str = Header(None),
                     db: Session = Depends(get_db)) -> User:
    """Dependency for JSON endpoints: reads `Authorization: Bearer <jwt>`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    return _user_from_token(authorization.split(" ", 1)[1], db)


def user_from_query_token(token: str, db: Session) -> User:
    """For media endpoints (img/href) that can't send an Authorization header —
    they pass ?token=<jwt> instead."""
    if not token:
        raise HTTPException(401, "missing token")
    return _user_from_token(token, db)


# --- demo seed -------------------------------------------------------------
def seed_demo(db: Session) -> None:
    """Idempotently create demo hospitals + users so login works out of the box.
    (Replaces the hardcoded DEMO_USERS dict; same emails/password.)"""
    demo = [
        ("skn", "Shree Krishna Nursing Home",
         "desk@skn.hospital", "Claims Desk", "claims123", "clerk"),
        ("lifecare", "LifeCare Multispeciality Hospital",
         "admin@lifecare.in", "Admin", "claims123", "admin"),
    ]
    for hid, hname, email, name, pw, role in demo:
        if not db.get(Hospital, hid):
            db.add(Hospital(id=hid, name=hname))
        exists = db.execute(
            select(User).where(User.email == email)).scalar_one_or_none()
        if not exists:
            db.add(User(email=email, name=name, password_hash=hash_password(pw),
                        hospital_id=hid, role=role))
            log.info("seeded user %s (%s)", email, hid)
    db.commit()
