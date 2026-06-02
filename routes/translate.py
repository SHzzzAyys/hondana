"""翻译 + 设置路由"""
import json
import os

import requests
from flask import Blueprint, current_app, jsonify, render_template, request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

bp = Blueprint("translate", __name__)

# 环境变量名:优先级高于 settings.json,避免把 API Key 明文写到磁盘。
# 已部署的旧用户若 settings.json 里仍有 key 也兼容工作。
_DEEPSEEK_ENV = "DEEPSEEK_API_KEY"


def _build_session():
    """构造一个带退避重试的 requests Session。

    - 仅对幂等的临时性故障重试:5xx、429、连接重置/读超时
    - 3 次重试,退避因子 0.5(0.5s → 1s → 2s)
    - 不重试 4xx 业务错误(401/403 等,key 不对再试也没用)
    """
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,  # 由我们自己读 .status_code,而不是抛 RetryError
    )
    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


# 复用同一个 Session,连接池跨请求复用
_http = _build_session()


def _get_deepseek_key(settings):
    """按 env > settings.json 顺序返回 key,找不到返回空串"""
    env_key = (os.environ.get(_DEEPSEEK_ENV) or "").strip()
    if env_key:
        return env_key
    return (settings.get("deepseek_api_key") or "").strip()


def _deepseek_source(settings):
    """返回 key 的来源(env/settings/none),用于设置页提示"""
    if (os.environ.get(_DEEPSEEK_ENV) or "").strip():
        return "env"
    if (settings.get("deepseek_api_key") or "").strip():
        return "settings"
    return "none"

_SETTINGS_FILE = None


def _settings_path():
    global _SETTINGS_FILE
    if _SETTINGS_FILE is None:
        _SETTINGS_FILE = os.path.join(current_app.instance_path, "settings.json")
    return _SETTINGS_FILE


def _load_settings():
    path = _settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_settings(data):
    path = _settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- 翻译 API ----------

@bp.route("/api/translate", methods=["POST"])
def translate():
    """翻译接口"""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text 必填"}), 400

    engine = (body.get("engine") or "").strip()
    settings = _load_settings()
    if not engine:
        engine = settings.get("translate_engine", "google")

    try:
        if engine == "deepseek":
            api_key = _get_deepseek_key(settings)
            if not api_key:
                return jsonify({
                    "error": "未配置 DeepSeek API Key,请通过环境变量 DEEPSEEK_API_KEY 设置,或前往设置页面配置",
                    "code": "no_key",
                }), 400
            result = _translate_deepseek(text, api_key)
        else:
            result = _translate_google(text)
    except requests.Timeout:
        return jsonify({"error": "翻译超时,请稍后重试", "code": "timeout"}), 504
    except requests.ConnectionError:
        return jsonify({"error": "网络连接失败,请检查网络后重试", "code": "network"}), 502
    except requests.HTTPError as e:
        # 重试用尽后仍 4xx/5xx,把上游状态分级映射出去
        status = e.response.status_code if e.response is not None else 502
        if status == 429:
            return jsonify({
                "error": "翻译服务请求过于频繁,请稍候再试",
                "code": "rate_limited",
            }), 429
        if status in (401, 403):
            return jsonify({
                "error": "翻译服务认证失败,请检查 API Key",
                "code": "auth",
            }), 401
        if 500 <= status < 600:
            return jsonify({
                "error": "翻译服务暂时不可用,请稍后重试",
                "code": "upstream",
            }), 502
        return jsonify({
            "error": f"翻译失败({status})",
            "code": "http_error",
        }), 502
    except Exception as e:
        return jsonify({"error": f"翻译失败: {e}", "code": "unknown"}), 500

    return jsonify({"result": result, "engine": engine})


def _translate_google(text):
    """Google Translate 免费接口(无 key,但端点可能限流,走带重试的 Session)"""
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": "zh-CN",
        "dt": "t",
        "q": text,
    }
    resp = _http.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    # data[0] 是翻译段落列表
    parts = []
    if data and data[0]:
        for seg in data[0]:
            if seg and seg[0]:
                parts.append(seg[0])
    return "".join(parts)


def _translate_deepseek(text, api_key):
    """DeepSeek 翻译"""
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业翻译。请将用户提供的文本翻译成中文。如果文本已经是中文，则翻译成英文。只输出翻译结果，不要添加任何解释。",
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    resp = _http.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


# ---------- 设置 API ----------

@bp.route("/api/settings/translate", methods=["GET"])
def get_translate_settings():
    """读取翻译设置"""
    settings = _load_settings()
    return jsonify({
        "translate_engine": settings.get("translate_engine", "google"),
        "has_deepseek_key": bool(_get_deepseek_key(settings)),
        "deepseek_key_source": _deepseek_source(settings),
        "reading_goal_yearly": settings.get("reading_goal_yearly", 0),
    })


@bp.route("/api/settings/translate", methods=["PUT"])
def save_translate_settings():
    """保存翻译设置"""
    body = request.get_json(silent=True) or {}
    settings = _load_settings()

    if "translate_engine" in body:
        settings["translate_engine"] = body["translate_engine"]
    if "deepseek_api_key" in body:
        key = (body["deepseek_api_key"] or "").strip()
        if key:
            settings["deepseek_api_key"] = key
        else:
            settings.pop("deepseek_api_key", None)
    if "reading_goal_yearly" in body:
        try:
            settings["reading_goal_yearly"] = int(body["reading_goal_yearly"])
        except (ValueError, TypeError):
            settings["reading_goal_yearly"] = 0

    _save_settings(settings)
    return jsonify({"ok": True})


# ---------- 设置页面 ----------

@bp.route("/settings")
def settings_page():
    """设置页面"""
    settings = _load_settings()
    # 给模板透传一个布尔字段,用于在 UI 上提示"环境变量优先"
    settings["deepseek_env_active"] = bool((os.environ.get(_DEEPSEEK_ENV) or "").strip())
    return render_template("settings.html", settings=settings)
