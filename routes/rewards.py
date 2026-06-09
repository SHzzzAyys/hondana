"""里程碑奖励(🌸)路由 - 写感想

奖励的"领取/创建"已移到 routes/books.py::update_reading_time(每读满 N 分钟由
服务端在心跳里判定并创建一朵 kind='time' 的🌸)。这里只负责给某朵🌸补写感想。
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from models import ReadingReward, db

bp = Blueprint("rewards", __name__)


@bp.route("/rewards/<int:reward_id>", methods=["PATCH"])
def update(reward_id: int):
    """写入/更新某朵🌸的感想。body: {"reflection": "..."}"""
    reward = ReadingReward.query.get(reward_id)
    if reward is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    if "reflection" in data:
        reward.reflection = (data.get("reflection") or "").strip() or None
        db.session.commit()
    return jsonify(reward.to_dict())
