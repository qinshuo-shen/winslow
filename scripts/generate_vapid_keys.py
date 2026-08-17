"""
One-time VAPID keypair generation for Web Push (see
procrastination_tool/push_notifications.py).

IMPORTANT: run this ONCE, on whichever machine (local or the VPS) generates
the keypair first, then COPY the resulting data/vapid_private_key.pem to
every other environment (local <-> VPS) that needs to send push
notifications to the same subscriptions -- do NOT run this script
independently on both. A push subscription is bound to the public key it
was created with; sending with a different private key later will make
every send to that subscription fail.
"""
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from py_vapid.utils import b64urlencode

from procrastination_tool.config import VAPID_PRIVATE_KEY_PATH


def main() -> None:
    if VAPID_PRIVATE_KEY_PATH.exists():
        print(f"Key already exists at {VAPID_PRIVATE_KEY_PATH} -- refusing to overwrite.")
        print("Delete it first if you really want to regenerate "
              "(this will orphan every existing subscription).")
        return

    vapid = Vapid02()
    vapid.generate_keys()
    vapid.save_key(str(VAPID_PRIVATE_KEY_PATH))

    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public_key = b64urlencode(raw)

    print(f"Private key written to {VAPID_PRIVATE_KEY_PATH}")
    print("Set this in your .env on BOTH local and the VPS (same value everywhere):")
    print(f"VAPID_PUBLIC_KEY={public_key}")


if __name__ == "__main__":
    main()
