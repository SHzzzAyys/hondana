"""pytest fixtures - 临时 instance 目录 + 内存数据库的 Flask app"""
import os
import sys

import pytest

# 让测试能直接 import 项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def app(tmp_path):
    """每个测试一个干净的 Flask app + SQLite 文件库"""
    os.environ["SECRET_KEY"] = "test-secret"
    from app import create_app
    from config import Config

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"

    flask_app = create_app(config_class=TestConfig, instance_path=str(tmp_path))

    with flask_app.app_context():
        from models import db
        db.create_all()
        yield flask_app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()
