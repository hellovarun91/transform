from __future__ import annotations

import json
import logging

from pywebpush import WebPushException, webpush  # noqa: F401  (re-exported for tests)

from .config import Settings
from .db import Store

log = logging.getLogger("transform.push")


def send_push(store: Store, settings: Settings, title: str, body: str, url: str = "/", tag: str | None = None) -> int:
    if not settings.vapid_private_key or not settings.vapid_public_key:
        return 0
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or title})
    sent = 0
    for sub in store.list_subscriptions():
        info = {"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}
        try:
            webpush(subscription_info=info, data=payload, vapid_private_key=settings.vapid_private_key,
                    vapid_claims={"sub": settings.vapid_claims_email}, ttl=3600)
            sent += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                store.remove_subscription(sub["endpoint"])
                log.info("removed dead push subscription %s", sub["endpoint"])
            else:
                log.warning("push failed (%s): %s", status, e)
        except Exception as e:  # noqa: BLE001
            log.warning("push error: %s", e)
    return sent
