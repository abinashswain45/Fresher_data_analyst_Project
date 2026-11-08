import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..automation.engine import AutomationError, manager
from ..db import get_db
from ..models import ApplicationStatus, User
from ..security import get_current_user
from .applications import owned_app

router = APIRouter(prefix="/api/automation", tags=["automation"])


class StartIn(BaseModel):
    headless: bool | None = None


class InputIn(BaseModel):
    action: str = Field(pattern="^(click|type|key|scroll|back)$")
    x: float | None = None
    y: float | None = None
    text: str | None = Field(default=None, max_length=500)
    key: str | None = None
    dy: int | None = None


def _session(app_id: int, user: User):
    s = manager.get(app_id, user.id)
    if not s:
        raise HTTPException(404, "No active automation session for this application")
    return s


@router.post("/{app_id}/start")
async def start(app_id: int, body: StartIn | None = None, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    if app.status == ApplicationStatus.SUBMITTED.value:
        raise HTTPException(400, "This application has already been submitted")
    if not app.resume_id:
        raise HTTPException(400, "Approve a resume version before starting the application")
    try:
        s = await manager.start(app_id, user.id, body.headless if body else None)
    except AutomationError as exc:
        raise HTTPException(409, str(exc)) from exc
    await asyncio.sleep(0.2)
    return s.to_dict()


@router.get("/{app_id}/state")
def state(app_id: int, user: User = Depends(get_current_user)):
    s = manager.get(app_id, user.id)
    return s.to_dict() if s else {"application_id": app_id, "state": "none"}


async def _bg(coro_fn):
    try:
        await coro_fn()
    except AutomationError:
        pass


@router.post("/{app_id}/continue")
async def continue_application(app_id: int, user: User = Depends(get_current_user)):
    s = _session(app_id, user)
    if s.state not in ("paused", "error"):
        raise HTTPException(409, "Automation is not waiting for you right now")
    asyncio.create_task(_bg(s.resume))
    await asyncio.sleep(0.1)  # let resume() take the lock and flip the state to running
    return s.to_dict()


@router.post("/{app_id}/approve-submit")
async def approve_submit(app_id: int, user: User = Depends(get_current_user)):
    """Explicit final approval. The ONLY path by which the agent clicks a final submit button."""
    s = _session(app_id, user)
    if not (s.state == "paused" and s.checkpoint and s.checkpoint.kind == "final_approval"):
        raise HTTPException(409, "The application is not at the final approval step")
    asyncio.create_task(_bg(s.approve_and_submit))
    await asyncio.sleep(0.1)
    return s.to_dict()


@router.post("/{app_id}/stop")
async def stop(app_id: int, user: User = Depends(get_current_user)):
    _session(app_id, user)
    await manager.stop(app_id)
    return {"application_id": app_id, "state": "closed"}


@router.get("/{app_id}/screenshot")
async def screenshot(app_id: int, user: User = Depends(get_current_user)):
    s = _session(app_id, user)
    try:
        img = await s.screenshot()
    except Exception as exc:
        raise HTTPException(409, "Browser view not available yet") from exc
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{app_id}/input")
async def remote_input(app_id: int, body: InputIn, user: User = Depends(get_current_user)):
    """Forward the user's own clicks/keystrokes to the browser (for OTP, CAPTCHA, login from any device).
    Typed text is never logged or stored."""
    s = _session(app_id, user)
    try:
        if body.action == "click" and body.x is not None and body.y is not None:
            await s.remote("click", x=body.x, y=body.y)
        elif body.action == "type" and body.text:
            await s.remote("type", text=body.text)
        elif body.action == "key" and body.key:
            await s.remote("key", key=body.key)
        elif body.action == "scroll":
            await s.remote("scroll", dy=body.dy or 400)
        elif body.action == "back":
            await s.remote("back")
        else:
            raise HTTPException(400, "Invalid input")
    except AutomationError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}
