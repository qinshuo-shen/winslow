"""
FastAPI-layer auth dependency. Kept separate from procrastination_tool/
auth.py deliberately -- that module knows nothing about HTTP/cookies, this
is the one place that translates "no valid session cookie" into a real
401, so every router just declares `user: auth.User = Depends(get_current_user)`
and gets an authenticated, already-scoped user or a 401 for free.
"""
from fastapi import HTTPException, Request

from procrastination_tool import auth

SESSION_COOKIE_NAME = "winslow_session"


def get_current_user(request: Request) -> auth.User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = auth.get_user_by_session_token(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
