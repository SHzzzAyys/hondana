"""验证翻译路由的重试 + 错误码分级 (P0-5)"""
from unittest.mock import MagicMock, patch

import pytest
import requests


def _mock_resp(status=200, json_body=None, raise_for_status_err=None):
    """构造一个 requests.Response 风格的 Mock"""
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body or [[]]
    if raise_for_status_err is not None:
        r.raise_for_status.side_effect = raise_for_status_err
    else:
        r.raise_for_status.return_value = None
    return r


# ---------- 错误码分级 ----------

def test_translate_timeout_returns_504(app, client):
    """requests.Timeout → 504 + code=timeout"""
    with patch("routes.translate._http.get", side_effect=requests.Timeout()):
        resp = client.post("/api/translate", json={"text": "hello", "engine": "google"})
    assert resp.status_code == 504
    body = resp.get_json()
    assert body["code"] == "timeout"


def test_translate_connection_error_returns_502_network(app, client):
    with patch("routes.translate._http.get", side_effect=requests.ConnectionError()):
        resp = client.post("/api/translate", json={"text": "hello", "engine": "google"})
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "network"


def test_translate_429_returns_429_rate_limited(app, client):
    """上游 429(经 Retry 仍失败)应映射为 429 + code=rate_limited"""
    bad = _mock_resp(status=429)
    err = requests.HTTPError(response=bad)
    bad.raise_for_status.side_effect = err
    with patch("routes.translate._http.get", return_value=bad):
        resp = client.post("/api/translate", json={"text": "hi", "engine": "google"})
    assert resp.status_code == 429
    assert resp.get_json()["code"] == "rate_limited"


def test_translate_5xx_returns_502_upstream(app, client):
    bad = _mock_resp(status=503)
    err = requests.HTTPError(response=bad)
    bad.raise_for_status.side_effect = err
    with patch("routes.translate._http.get", return_value=bad):
        resp = client.post("/api/translate", json={"text": "hi", "engine": "google"})
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "upstream"


def test_translate_deepseek_auth_401_returns_401_auth(app, client, monkeypatch):
    """DeepSeek 401(key 错)应映射为 401 + code=auth"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-wrong-key")
    bad = _mock_resp(status=401)
    err = requests.HTTPError(response=bad)
    bad.raise_for_status.side_effect = err
    with patch("routes.translate._http.post", return_value=bad):
        resp = client.post("/api/translate", json={"text": "hi", "engine": "deepseek"})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "auth"


def test_translate_deepseek_without_key_returns_400_no_key(app, client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    resp = client.post("/api/translate", json={"text": "hi", "engine": "deepseek"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "no_key"


# ---------- 重试策略本身 ----------

def test_session_has_retry_adapter():
    """Session 应挂载了带重试的 HTTPAdapter"""
    from routes.translate import _http
    adapter = _http.get_adapter("https://example.com/")
    # urllib3.util.Retry 实例
    retries = adapter.max_retries
    assert retries.total == 3
    assert 429 in retries.status_forcelist
    assert 500 in retries.status_forcelist
    assert 503 in retries.status_forcelist


# ---------- 成功路径 ----------

def test_translate_google_success(app, client):
    """正常路径:Google 返回有效 JSON,接口返回 result + engine"""
    ok = _mock_resp(
        status=200,
        json_body=[[["你好", "hello", None, None, 0]]],
    )
    with patch("routes.translate._http.get", return_value=ok):
        resp = client.post("/api/translate", json={"text": "hello", "engine": "google"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["result"] == "你好"
    assert body["engine"] == "google"


def test_translate_empty_text_rejected(app, client):
    resp = client.post("/api/translate", json={"text": "   "})
    assert resp.status_code == 400
    assert "text 必填" in resp.get_json()["error"]
