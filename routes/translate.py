"""翻译 + 设置路由

翻译支持三种引擎,并带自动兜底:
- google   : Google 免费接口(无需 key,双向中英)
- deepseek : DeepSeek AI(需 API Key,api.deepseek.com 国内可达)
- ollama   : 本地 Ollama(离线,localhost,最稳)

重要修复:用户的 Windows 系统代理可能指向一个已失效的本地端口
(如 127.0.0.1:1088)。requests 默认会从注册表继承系统代理,导致所有外连
被中止(WinError 10053 "你的主机中的软件中止了一个已建立的连接")。
这里统一用 trust_env=False 的 Session **直连**、绕过失效代理 —— 这是翻译
"突然不能用"的根因。
"""
import json
import os

import requests
from flask import Blueprint, current_app, jsonify, render_template, request

bp = Blueprint("translate", __name__)

_SETTINGS_FILE = None

# 浏览器 UA:部分网络边界对默认 python-requests UA 更敏感,顺手带上更稳。
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"

ENGINE_LABELS = {"google": "Google", "deepseek": "DeepSeek", "ollama": "本地 Ollama"}


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


def _session():
    """忽略系统/环境代理的 requests.Session(直连),绕过失效的系统代理。"""
    s = requests.Session()
    s.trust_env = False   # 不读环境变量/系统代理
    s.proxies = {}        # 显式清空,双保险
    s.headers.update({"User-Agent": _UA})
    return s


# ---------- 翻译 API ----------

def _looks_chinese(text: str) -> bool:
    """粗略判断文本是否以中文为主(用于决定 Google 翻译方向)。"""
    han = sum(1 for ch in text if "一" <= ch <= "鿿")
    stripped = text.strip()
    return bool(stripped) and han >= max(1, len(stripped) * 0.3)


def _engine_order(settings, requested):
    """返回要依次尝试的引擎列表。

    requested 非空时只用它(设置页"测试"指定引擎的场景);
    否则:用户选定的引擎优先,其余作为自动兜底(DeepSeek→Google→Ollama)。
    没配置 key 的 DeepSeek 会被跳过。
    """
    if requested:
        order = [requested]
    else:
        chosen = settings.get("translate_engine", "google")
        order = [chosen]
        for e in ("deepseek", "google", "ollama"):
            if e not in order:
                order.append(e)
    out = []
    for e in order:
        if e == "deepseek" and not settings.get("deepseek_api_key"):
            continue
        if e in ENGINE_LABELS and e not in out:
            out.append(e)
    return out or ["google"]


@bp.route("/api/translate", methods=["POST"])
def translate():
    """翻译接口。按引擎顺序尝试,任一成功即返回;全失败给出可操作的错误。"""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text 必填"}), 400

    settings = _load_settings()
    requested = (body.get("engine") or "").strip()
    engines = _engine_order(settings, requested)

    sess = _session()
    errors = []
    for eng in engines:
        try:
            if eng == "deepseek":
                key = settings.get("deepseek_api_key", "")
                if not key:
                    errors.append("DeepSeek: 未配置 API Key")
                    continue
                result = _translate_deepseek(sess, text, key)
            elif eng == "ollama":
                host = settings.get("ollama_host") or DEFAULT_OLLAMA_HOST
                model = settings.get("ollama_model") or DEFAULT_OLLAMA_MODEL
                result = _translate_ollama(sess, text, host, model)
            else:
                result = _translate_google(sess, text)

            if result and result.strip():
                return jsonify({"result": result.strip(), "engine": eng})
            errors.append(f"{ENGINE_LABELS.get(eng, eng)}: 返回为空")
        except requests.Timeout:
            errors.append(f"{ENGINE_LABELS.get(eng, eng)}: 超时")
        except requests.ConnectionError:
            errors.append(f"{ENGINE_LABELS.get(eng, eng)}: 连接失败")
        except Exception as e:
            errors.append(f"{ENGINE_LABELS.get(eng, eng)}: {e}")

    hint = "；".join(errors) or "无可用引擎"
    return jsonify({
        "error": f"翻译失败（{hint}）。可在设置切换引擎：配置 DeepSeek Key，或启动本地 Ollama。",
    }), 502


def _translate_google(sess, text):
    """Google 翻译免费接口(双向:非中文→中文,中文→英文)。"""
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": "en" if _looks_chinese(text) else "zh-CN",
        "dt": "t",
        "q": text,
    }
    resp = sess.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    parts = []
    if data and data[0]:
        for seg in data[0]:
            if seg and seg[0]:
                parts.append(seg[0])
    return "".join(parts)


def _translate_deepseek(sess, text, api_key):
    """DeepSeek 翻译(双向)。"""
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
    resp = sess.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _translate_ollama(sess, text, host, model):
    """本地 Ollama 翻译(双向,离线最稳)。"""
    url = host.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业翻译。请将用户提供的文本翻译成中文。如果文本已经是中文，则翻译成英文。只输出翻译结果，不要添加任何解释、思考过程或标注。",
            },
            {"role": "user", "content": text},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    resp = sess.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message", {}).get("content") or "").strip()


# ---------- 设置 API ----------

@bp.route("/api/settings/translate", methods=["GET"])
def get_translate_settings():
    """读取翻译设置"""
    settings = _load_settings()
    return jsonify({
        "translate_engine": settings.get("translate_engine", "google"),
        "has_deepseek_key": bool(settings.get("deepseek_api_key")),
        "ollama_host": settings.get("ollama_host", DEFAULT_OLLAMA_HOST),
        "ollama_model": settings.get("ollama_model", DEFAULT_OLLAMA_MODEL),
        "reading_goal_yearly": settings.get("reading_goal_yearly", 0),
        "reward_interval_minutes": settings.get("reward_interval_minutes", 30),
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
    if "ollama_host" in body:
        host = (body["ollama_host"] or "").strip()
        if host:
            settings["ollama_host"] = host
        else:
            settings.pop("ollama_host", None)
    if "ollama_model" in body:
        model = (body["ollama_model"] or "").strip()
        if model:
            settings["ollama_model"] = model
        else:
            settings.pop("ollama_model", None)
    if "reading_goal_yearly" in body:
        try:
            settings["reading_goal_yearly"] = int(body["reading_goal_yearly"])
        except (ValueError, TypeError):
            settings["reading_goal_yearly"] = 0
    if "reward_interval_minutes" in body:
        try:
            v = int(body["reward_interval_minutes"])
            settings["reward_interval_minutes"] = v if v >= 1 else 30
        except (ValueError, TypeError):
            settings["reward_interval_minutes"] = 30

    _save_settings(settings)
    return jsonify({"ok": True})


# ---------- 设置页面 ----------

@bp.route("/settings")
def settings_page():
    """设置页面"""
    settings = _load_settings()
    return render_template("settings.html", settings=settings)
