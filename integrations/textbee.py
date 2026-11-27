"""Optional SMS delivery through TextBee (https://textbee.dev), an SMS gateway that sends from an Android phone.

This is the ONLY module that talks to the network, and only when an officer presses "Send" in the Dispatch
center. Forecasting, allocation, routing, simulation and notice generation never import it, so the core system
still runs fully offline. If the gateway is not configured or the internet is down, sending fails with a clear
message and nothing else is affected.

API used (TextBee README, github.com/vernu/textbee):
    POST {base_url}/api/v1/gateway/send-sms
    headers: x-api-key: <API key>, Content-Type: application/json
    body:    {"recipients": ["+8801..."], "message": "...", "deviceId": "<optional>"}

The README does not document the response body, so a 2xx reply is reported as "accepted by TextBee" (queued on
the phone), never as "delivered". Delivery can be confirmed in the TextBee dashboard.

Configuration (never commit the key):
    TEXTBEE_API_KEY    required   from the TextBee dashboard
    TEXTBEE_DEVICE_ID  optional   which phone to send from; default device otherwise
    TEXTBEE_BASE_URL   optional   default https://api.textbee.dev (change for a self-hosted gateway)
Read from environment variables or Streamlit secrets (.streamlit/secrets.toml, git-ignored).
"""
import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.textbee.dev"
SEND_PATH = "/api/v1/gateway/send-sms"
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")      # E.164: + country code + number, 8-15 digits


def load_config(secrets=None):
    """Read settings from Streamlit secrets (if given) then environment variables. Returns None if no key."""
    def get(name):
        if secrets is not None:
            try:
                if name in secrets and str(secrets[name]).strip():
                    return str(secrets[name]).strip()
            except Exception:
                pass
        v = os.environ.get(name, "").strip()
        return v or None

    key = get("TEXTBEE_API_KEY")
    if not key:
        return None
    return {"api_key": key, "device_id": get("TEXTBEE_DEVICE_ID"),
            "base_url": (get("TEXTBEE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")}


def normalize_phone(raw):
    """Clean a phone number to E.164. Bangladeshi local numbers (01XXXXXXXXX) get +880. Returns None if invalid."""
    if raw is None:
        return None
    s = re.sub(r"[\s\-().]", "", str(raw))
    if s.startswith("00"):
        s = "+" + s[2:]
    if re.fullmatch(r"01\d{9}", s):            # Bangladesh mobile, local format
        s = "+88" + s
    elif re.fullmatch(r"8801\d{9}", s):
        s = "+" + s
    return s if PHONE_RE.fullmatch(s) else None


def _mask(key):
    return (key[:3] + "…" + key[-2:]) if key and len(key) > 8 else "***"


def send_sms(recipients, message, config, timeout=15, opener=None):
    """Send one message to one or more numbers. Never raises; never includes the API key in the result.

    Returns {"ok": bool, "status": int|None, "detail": str, "recipients": [...]}.
    """
    opener = opener or urllib.request.urlopen
    if not config or not config.get("api_key"):
        return {"ok": False, "status": None, "detail": "TextBee is not configured (no API key).", "recipients": []}
    nums = [normalize_phone(r) for r in recipients]
    bad = [r for r, n in zip(recipients, nums) if n is None]
    if bad:
        return {"ok": False, "status": None, "detail": f"Invalid phone number(s): {', '.join(map(str, bad))}",
                "recipients": []}
    if not message or not message.strip():
        return {"ok": False, "status": None, "detail": "Empty message.", "recipients": nums}

    body = {"recipients": nums, "message": message}
    if config.get("device_id"):
        body["deviceId"] = config["device_id"]
    req = urllib.request.Request(
        config["base_url"] + SEND_PATH, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"x-api-key": config["api_key"], "Content-Type": "application/json",
                 "User-Agent": "dengue-early-warning-dispatch"})
    try:
        with opener(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            text = resp.read(2000).decode("utf-8", "replace")
        ok = 200 <= int(status) < 300
        return {"ok": ok, "status": int(status), "recipients": nums,
                "detail": ("Accepted by TextBee (queued on the phone). Check delivery in the TextBee dashboard."
                           if ok else f"Unexpected reply: {text[:300]}")}
    except urllib.error.HTTPError as e:
        try:
            text = e.read(2000).decode("utf-8", "replace")
        except Exception:
            text = ""
        hint = {401: "API key rejected.", 403: "Not allowed (check key, plan limits or device).",
                404: "Endpoint or device not found (check TEXTBEE_DEVICE_ID / base URL).",
                429: "Rate or plan limit reached."}.get(e.code, "")
        return {"ok": False, "status": e.code, "recipients": nums,
                "detail": f"TextBee error {e.code}. {hint} {text[:300]}".strip().replace(config["api_key"],
                                                                                         _mask(config["api_key"]))}
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return {"ok": False, "status": None, "recipients": nums,
                "detail": f"Could not reach TextBee (offline or blocked): {getattr(e, 'reason', e)}"}
