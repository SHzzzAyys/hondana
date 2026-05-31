"""验证 P0-2: CSRF 保护 + SECRET_KEY 强校验 + DeepSeek key 环境变量优先"""
import os

import pytest


# ---------- CSRF 保护 ----------

@pytest.fixture
def app_csrf_on(tmp_path):
    """专为 CSRF 测试构造的 app:打开 CSRF + 给一个稳定的 secret key"""
    os.environ["SECRET_KEY"] = "test-secret-for-csrf"
    from app import create_app
    from config import Config

    class CsrfConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'csrf.db'}"
        WTF_CSRF_ENABLED = True
        SECRET_KEY = "test-secret-for-csrf"

    flask_app = create_app(config_class=CsrfConfig, instance_path=str(tmp_path))
    with flask_app.app_context():
        from models import db
        db.create_all()
        yield flask_app


def test_post_without_csrf_token_is_rejected(app_csrf_on):
    """无 token 的表单 POST 应被 CSRF 中间件拦截"""
    from models import Book, db
    with app_csrf_on.app_context():
        book = Book(title="t", author="a", status="reading")
        db.session.add(book)
        db.session.commit()
        book_id = book.id

    client = app_csrf_on.test_client()
    # 用 form 类型 POST,不带 csrf_token
    resp = client.post(f"/books/{book_id}/delete", data={})
    # Flask-WTF 默认返回 400
    assert resp.status_code == 400


def test_ajax_without_csrf_header_is_rejected(app_csrf_on):
    """无 X-CSRFToken header 的 AJAX 写请求也应被拒"""
    from models import Book, db
    with app_csrf_on.app_context():
        book = Book(title="t", author="a", status="reading")
        db.session.add(book)
        db.session.commit()
        book_id = book.id

    client = app_csrf_on.test_client()
    resp = client.patch(
        f"/books/{book_id}/reading-time",
        json={"seconds": 30},
    )
    assert resp.status_code == 400


def test_ajax_with_csrf_header_passes(app_csrf_on):
    """带 X-CSRFToken header 的 AJAX 写请求应被放行"""
    from flask_wtf.csrf import generate_csrf
    from models import Book, db
    with app_csrf_on.app_context():
        book = Book(title="t", author="a", status="reading")
        db.session.add(book)
        db.session.commit()
        book_id = book.id

    client = app_csrf_on.test_client()
    # generate_csrf 必须在请求上下文里取 token,这里用 GET 任意页面拿一次
    with client:
        # 触发一次 GET,让 session 里有 csrf_token
        client.get("/")
        with app_csrf_on.test_request_context():
            token = generate_csrf()
        # 注意: generate_csrf 把 token 放入 session,
        # test_client 用同一个 session,跨请求保持
        resp = client.patch(
            f"/books/{book_id}/reading-time",
            json={"seconds": 30},
            headers={"X-CSRFToken": token},
        )
        # 200 即未被 CSRF 拦截(业务正常)
        assert resp.status_code == 200


def test_csrf_meta_tag_present_on_all_pages(app_csrf_on):
    """base.html 渲染的页面应包含 csrf-token meta 标签,供前端 fetch 包装器读取"""
    client = app_csrf_on.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'name="csrf-token"' in html


# ---------- SECRET_KEY 强校验 ----------

def test_default_secret_key_rejected_in_production(tmp_path, monkeypatch):
    """非 TESTING + 非 debug 模式,若 SECRET_KEY 仍是默认值,create_app 应拒绝启动"""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from app import create_app
    from config import Config, DEFAULT_DEV_SECRET_KEY

    class ProdishConfig(Config):
        # 不开 TESTING,不开 DEBUG
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'p.db'}"
        SECRET_KEY = DEFAULT_DEV_SECRET_KEY  # 故意保持默认

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(config_class=ProdishConfig, instance_path=str(tmp_path))


def test_custom_secret_key_passes(tmp_path, monkeypatch):
    """配置了真正的 SECRET_KEY 时应正常启动"""
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    from app import create_app
    from config import Config

    class GoodConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'g.db'}"
        SECRET_KEY = "x" * 40

    flask_app = create_app(config_class=GoodConfig, instance_path=str(tmp_path))
    assert flask_app.config["SECRET_KEY"] == "x" * 40


# ---------- DeepSeek key 环境变量优先 ----------

def test_deepseek_env_overrides_settings(app, monkeypatch):
    """环境变量 DEEPSEEK_API_KEY 应优先于 settings.json"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    from routes.translate import _get_deepseek_key
    settings = {"deepseek_api_key": "sk-from-settings"}
    with app.app_context():
        assert _get_deepseek_key(settings) == "sk-from-env"


def test_deepseek_falls_back_to_settings(app, monkeypatch):
    """无环境变量时,应回退到 settings.json"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from routes.translate import _get_deepseek_key
    settings = {"deepseek_api_key": "sk-from-settings"}
    with app.app_context():
        assert _get_deepseek_key(settings) == "sk-from-settings"


def test_deepseek_source_reporting(app, monkeypatch):
    """GET /api/settings/translate 应在 has_deepseek_key + source 上反映真实来源"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-only")
    client = app.test_client()
    resp = client.get("/api/settings/translate")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["has_deepseek_key"] is True
    assert data["deepseek_key_source"] == "env"
