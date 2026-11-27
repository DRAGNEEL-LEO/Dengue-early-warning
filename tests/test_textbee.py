"""Tests for the optional TextBee SMS integration. A fake opener stands in for the network: no real SMS is sent."""
import io
import json
import sys
import urllib.error

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT))
from integrations import textbee  # noqa: E402

CFG = {"api_key": "tb_secret_key_123456", "device_id": "dev123", "base_url": "https://api.textbee.dev"}


class FakeResp:
    def __init__(self, status=201, body=b'{"data":{"success":true}}'):
        self.status, self._b = status, body

    def read(self, n=-1):
        return self._b

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_sends_correct_request_and_reports_accepted():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["method"] = req.full_url, req.get_method()
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["body"] = json.loads(req.data)
        return FakeResp(201)

    res = textbee.send_sms(["01712345678"], "Dengue alert", CFG, opener=opener)
    assert res["ok"] and res["status"] == 201
    assert "Accepted by TextBee" in res["detail"] and "deliver" not in res["detail"].lower().split("check")[0]
    assert seen["url"] == "https://api.textbee.dev/api/v1/gateway/send-sms" and seen["method"] == "POST"
    assert seen["headers"]["x-api-key"] == CFG["api_key"]
    assert seen["body"] == {"recipients": ["+8801712345678"], "message": "Dengue alert", "deviceId": "dev123"}


def test_http_error_is_reported_without_leaking_key():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     io.BytesIO(f"bad key {CFG['api_key']}".encode()))
    res = textbee.send_sms(["+8801712345678"], "x", CFG, opener=opener)
    assert not res["ok"] and res["status"] == 401
    assert "API key rejected" in res["detail"] and CFG["api_key"] not in res["detail"]


def test_rate_limit_and_offline_do_not_raise():
    def limited(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b""))

    def offline(req, timeout):
        raise urllib.error.URLError("network disabled")
    assert "limit" in textbee.send_sms(["+8801712345678"], "x", CFG, opener=limited)["detail"].lower()
    res = textbee.send_sms(["+8801712345678"], "x", CFG, opener=offline)
    assert not res["ok"] and "Could not reach TextBee" in res["detail"]


def test_not_configured_or_bad_input_never_calls_network():
    def boom(req, timeout):
        raise AssertionError("network must not be called")
    assert not textbee.send_sms(["+8801712345678"], "x", None, opener=boom)["ok"]
    assert "Invalid phone" in textbee.send_sms(["12345"], "x", CFG, opener=boom)["detail"]
    assert "Empty message" in textbee.send_sms(["+8801712345678"], "  ", CFG, opener=boom)["detail"]


@pytest.mark.parametrize("raw,expected", [
    ("01712345678", "+8801712345678"), ("+880 1712-345678", "+8801712345678"), ("8801712345678", "+8801712345678"),
    ("008801712345678", "+8801712345678"), ("+12025550123", "+12025550123"), ("12345", None), ("", None), (None, None),
])
def test_normalize_phone(raw, expected):
    assert textbee.normalize_phone(raw) == expected


def test_load_config(monkeypatch):
    for k in ("TEXTBEE_API_KEY", "TEXTBEE_DEVICE_ID", "TEXTBEE_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    assert textbee.load_config() is None
    monkeypatch.setenv("TEXTBEE_API_KEY", "abc")
    cfg = textbee.load_config()
    assert cfg == {"api_key": "abc", "device_id": None, "base_url": "https://api.textbee.dev"}
    cfg = textbee.load_config({"TEXTBEE_API_KEY": "from_secrets", "TEXTBEE_BASE_URL": "http://192.168.1.5:3001/"})
    assert cfg["api_key"] == "from_secrets" and cfg["base_url"] == "http://192.168.1.5:3001"


def test_core_modules_still_never_import_the_gateway():
    for f in (ROOT / "src").glob("*.py"):
        assert "textbee" not in f.read_text().lower(), f.name
