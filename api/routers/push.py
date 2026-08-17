"""
Web Push notifications (focus-timer session end) -- thin wrapper around
procrastination_tool.push_notifications.

GET  /api/push/vapid-public-key -- the public key the frontend needs to
                                    call pushManager.subscribe(). null if
                                    VAPID isn't configured yet on this
                                    server (see push_notifications.is_configured()).
POST /api/push/subscribe        -- register/refresh a browser's push
                                    subscription. Idempotent (upsert on the
                                    endpoint's own UNIQUE constraint).
POST /api/push/unsubscribe      -- forget a subscription (e.g. the user
                                    turned notifications off).
"""
from fastapi import APIRouter

from procrastination_tool import push_notifications
from procrastination_tool.config import VAPID_PUBLIC_KEY

from ..schemas import PushSubscribeRequest, PushUnsubscribeRequest

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-public-key")
def get_vapid_public_key() -> dict:
    return {"public_key": VAPID_PUBLIC_KEY}


@router.post("/subscribe")
def subscribe(body: PushSubscribeRequest) -> dict:
    push_notifications.add_subscription(body.endpoint, body.keys.p256dh, body.keys.auth)
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(body: PushUnsubscribeRequest) -> dict:
    push_notifications.remove_subscription(body.endpoint)
    return {"ok": True}
