"""翻译 + 设置路由"""
import json
import os

import requests
from flask import Blueprint, current_app, jsonify, render_template, request

bp = Blueprint("translate", __name__)

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
            api_key = settings.get("deepseek_api_key", "")
            if not api_key:
                return jsonify({"error": "未配置 DeepSeek API Key，请前往设置页面配置"}), 400
            result = _translate_deepseek(text, api_key)
        else:
            result = _translate_google(text)
    except requests.Timeout:
        return jsonify({"error": "翻译超时，请稍后重试"}), 504
    except Exception as e:
        return jsonify({"error": f"翻译失败: {e}"}), 500

    return jsonify({"result": result, "engine": engine})


def _translate_google(text):
    """Google Translate 免费接口"""
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": "zh-CN",
        "dt": "t",
        "q": text,
    }
    resp = requests.get(url, params=params, timeout=10)
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
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
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
        "has_deepseek_key": bool(settings.get("deepseek_api_key")),
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
    return render_template("settings.html", settings=settings)
