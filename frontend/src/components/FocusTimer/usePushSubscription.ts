import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "../../api/client";

// Web Push subscription management for focus-session notifications (see
// procrastination_tool/push_notifications.py). Scoped to FocusTimerWidget
// specifically rather than a global app-wide settings surface -- the focus
// timer is the only feature currently wired to send pushes, and this app
// has no accounts/settings page to put a more generic toggle into.

export type PushSubscriptionState = "unsupported" | "not-subscribed" | "subscribed" | "denied";

// Standard conversion: applicationServerKey must be a Uint8Array, not the
// base64url string GET /push/vapid-public-key returns.
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const output = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    output[i] = rawData.charCodeAt(i);
  }
  return output;
}

interface UsePushSubscriptionResult {
  state: PushSubscriptionState;
  subscribe: () => Promise<void>;
}

export function usePushSubscription(): UsePushSubscriptionResult {
  const [state, setState] = useState<PushSubscriptionState>("not-subscribed");

  useEffect(() => {
    let cancelled = false;

    async function detect() {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        if (!cancelled) setState("unsupported");
        return;
      }
      if (Notification.permission === "denied") {
        if (!cancelled) setState("denied");
        return;
      }
      try {
        const registration = await navigator.serviceWorker.ready;
        const existing = await registration.pushManager.getSubscription();
        if (!cancelled) setState(existing ? "subscribed" : "not-subscribed");
      } catch {
        if (!cancelled) setState("not-subscribed");
      }
    }

    detect();
    return () => {
      cancelled = true;
    };
  }, []);

  const subscribe = useCallback(async () => {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      setState("denied");
      return;
    }
    const { public_key } = await apiGet<{ public_key: string | null }>("/push/vapid-public-key");
    if (!public_key) {
      // Backend not configured yet (no VAPID keypair generated) -- nothing
      // to subscribe to.
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    const sub = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    });
    const json = sub.toJSON();
    await apiPost("/push/subscribe", { endpoint: json.endpoint, keys: json.keys });
    setState("subscribed");
  }, []);

  return { state, subscribe };
}
