from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional


class CookieStore:
    """持久化抖音登录 Cookie。文件格式：{"cookies": [...], "fetched_at": <unix_ts>}"""

    def __init__(self, cookie_path: Path) -> None:
        self.cookie_path = Path(cookie_path)

    def load(self) -> Optional[dict]:
        """读取 cookie 文件。不存在或损坏返回 None。"""
        try:
            with self.cookie_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, OSError):
            return None

    def save(self, cookies: list, ts: float | None = None) -> None:
        """保存 cookies 列表 + 时间戳。父目录不存在时自动创建。ts 默认 time.time()。"""
        if ts is None:
            ts = time.time()

        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {"cookies": cookies, "fetched_at": ts}

        # 写入临时文件后原子替换，避免半写。
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(self.cookie_path.parent),
            prefix=".tmp_cookie_",
            suffix=".json",
            delete=False,
        )
        tmp_path = tmp.name
        try:
            json.dump(payload, tmp, ensure_ascii=False)
            tmp.close()
            os.replace(tmp_path, self.cookie_path)
        except Exception:
            # 出错时清理临时文件。
            try:
                tmp.close()
            except OSError:
                pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def is_expired(self, max_age: int = 86400) -> bool:
        """判断 cookie 是否过期。文件不存在、缺 fetched_at 字段、或超过 max_age 秒都返回 True。"""
        data = self.load()
        if data is None:
            return True
        fetched_at = data.get("fetched_at")
        if fetched_at is None:
            return True
        return (time.time() - float(fetched_at)) > max_age

    def clear(self) -> None:
        """删除 cookie 文件（如果存在）。文件不存在时静默返回。"""
        try:
            self.cookie_path.unlink()
        except FileNotFoundError:
            pass

    def get_cookies(self) -> list[dict]:
        """方便方法：返回 cookies 列表，不存在时返回空列表。"""
        data = self.load()
        if data is None:
            return []
        cookies = data.get("cookies")
        if isinstance(cookies, list):
            return cookies
        return []
