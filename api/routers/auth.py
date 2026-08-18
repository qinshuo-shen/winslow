"""
Login/logout/whoami for the multi-user follow-up. No self-serve signup --
both accounts (owner + friend) are created once via scripts/create_user.py,
never through this API.

POST /api/auth/login            -- {username, password} -> sets the session
                                    cookie, 401 on bad credentials.
POST /api/auth/logout           -- revokes the current session, clears the
                                    cookie.
GET  /api/auth/me               -- 401 if not logged in, else {username}.
                                    This is what the frontend polls on load
                                    to decide whether to show the login page.
POST /api/auth/change-password  -- {current_password, new_password}, logged
                                    in only. Requires the current password
                                    (proves it's really you, not just
                                    "has a valid cookie"); revokes every
                                    OTHER session for this account, keeps
                                    the caller's own session alive.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from procrastination_tool import auth

from ..deps import SESSION_COOKIE_NAME, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MeOut(BaseModel):
    username: str


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    # `Secure` is safe to always set once this is reached over HTTPS (the
    # production path, via `tailscale serve`'s HTTPS endpoint) but would
    # silently break local `http://localhost` dev, where the browser drops
    # a Secure cookie set over plain HTTP entirely -- checked dynamically
    # per-request off the scheme actually used, rather than a static
    # dev/prod config flag, so it just works in both.
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=auth.SESSION_LIFETIME_DAYS * 24 * 60 * 60,
    )


@router.post("/login", response_model=MeOut)
def login(body: LoginRequest, request: Request, response: Response) -> MeOut:
    user = auth.verify_password(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = auth.create_session(user.id)
    _set_session_cookie(response, request, token)
    return MeOut(username=user.username)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        auth.revoke_session(token)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: auth.User = Depends(get_current_user)) -> MeOut:
    return MeOut(username=user.username)


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest, request: Request, user: auth.User = Depends(get_current_user)
) -> dict:
    try:
        auth.change_password(
            user.id, body.current_password, body.new_password,
            keep_token=request.cookies.get(SESSION_COOKIE_NAME),
        )
    except ValueError as e:
        # Covers both a wrong current_password (auth.IncorrectPasswordError,
        # a ValueError subclass) and an empty new_password -- same 400
        # shape either way, the message itself tells them which.
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
