"""Кто пришёл.

Боевой режим: подпись initData от Telegram WebApp (HMAC-SHA256, ключ — bot token).
Dev-режим: заголовок ``X-Dev-User: <id>[:<имя>]`` — без подписи, только локально.
Имя в заголовке percent-encoded (заголовки — latin-1).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote

from fastapi import Header, HTTPException, Request


@dataclass(frozen=True)
class Identity:
    player_id: str  # tg:<id> или dev:<id>
    display_name: str
    tg_id: int | None = None


def verify_init_data(init_data: str, bot_token: str, max_age_s: int) -> Identity:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise HTTPException(401, "initData без hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise HTTPException(401, "подпись initData не сходится")
    if time.time() - int(pairs.get("auth_date", "0")) > max_age_s:
        raise HTTPException(401, "initData устарела")
    user = json.loads(pairs.get("user", "{}"))
    if "id" not in user:
        raise HTTPException(401, "initData без user")
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or user.get("username") or str(user["id"])
    return Identity(player_id=f"tg:{user['id']}", display_name=name, tg_id=int(user["id"]))


def current_identity(
    request: Request,
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
) -> Identity:
    settings = request.app.state.settings
    if authorization and authorization.startswith("tma "):
        if not settings.bot_token:
            raise HTTPException(401, "сервер без токена бота не проверяет initData")
        return verify_init_data(authorization[4:], settings.bot_token, settings.initdata_max_age_s)
    if settings.dev_auth and x_dev_user:
        uid, _, name = x_dev_user.partition(":")
        return Identity(player_id=f"dev:{uid}", display_name=unquote(name) or uid)
    raise HTTPException(401, "нет авторизации")
