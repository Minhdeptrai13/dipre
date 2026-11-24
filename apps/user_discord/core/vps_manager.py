"""
vps_manager.py - Core Engine quản lý máy ảo Cloud siêu nhẹ (Zero Browser RAM)
Hỗ trợ tạo VPS Linux Ubuntu/Docker, mã PIN bí mật, cổng Auth bo góc VIP và Auto Keep-Alive.
"""
from __future__ import annotations
import asyncio
import json
import logging
import random
import re
import string
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("VPSManager")

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "vps_sessions.json"
PORTAL_HTML = Path(__file__).resolve().parent / "vps_portal.html"

BINDER_BUILD_URL = "https://mybinder.org/build/gh/binder-examples/minimal-dockerfile/HEAD"


@dataclass
class VPSSession:
    user_id: int
    vps_name: str
    pin_code: str
    binder_url: str
    binder_token: str
    terminal_url: str
    portal_url: str
    created_at: float
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def time_left_str(self) -> str:
        left = max(0, int(self.expires_at - time.time()))
        mins = left // 60
        secs = left % 60
        return f"{mins:02d}m {secs:02d}s"


class VPSManager:
    _instance: Optional[VPSManager] = None

    def __init__(self):
        self.sessions: Dict[int, VPSSession] = {}
        self.portal_port = 14088
        self.tunnel_url: Optional[str] = None
        self._server_task: Optional[asyncio.Task] = None
        self._tunnel_proc: Optional[asyncio.subprocess.Process] = None
        self._load_sessions()

    @classmethod
    def get_instance(cls) -> VPSManager:
        if cls._instance is None:
            cls._instance = VPSManager()
        return cls._instance

    def _load_sessions(self):
        try:
            if DATA_FILE.exists():
                data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                now = time.time()
                for uid_str, item in data.items():
                    sess = VPSSession(**item)
                    if not sess.is_expired():
                        self.sessions[int(uid_str)] = sess
        except Exception as e:
            logger.warning(f"Lỗi đọc vps_sessions.json: {e}")

    def _save_sessions(self):
        try:
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {str(uid): asdict(s) for uid, s in self.sessions.items()}
            DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Lỗi lưu vps_sessions.json: {e}")

    def get_session(self, user_id: int) -> Optional[VPSSession]:
        sess = self.sessions.get(user_id)
        if sess and sess.is_expired():
            del self.sessions[user_id]
            self._save_sessions()
            return None
        return sess

    def delete_session(self, user_id: int) -> bool:
        if user_id in self.sessions:
            del self.sessions[user_id]
            self._save_sessions()
            return True
        return False

    async def ensure_portal_server(self):
        """Khởi động micro aiohttp server và Cloudflare tunnel nếu chưa chạy."""
        if self._server_task is None or self._server_task.done():
            self._server_task = asyncio.create_task(self._run_portal_server())
            await asyncio.sleep(0.5)

        if not self.tunnel_url:
            await self._start_tunnel()

    async def _run_portal_server(self):
        from aiohttp import web

        app = web.Application()

        async def handle_portal(req):
            sid = req.query.get("sid", "")
            name = req.query.get("name", "Linux-VPS")
            html = PORTAL_HTML.read_text(encoding="utf-8")
            html = html.replace("{{VPS_NAME}}", name)
            return web.Response(text=html, content_type="text/html")

        async def handle_verify(req):
            try:
                body = await req.json()
                sid = str(body.get("sid", "")).strip()
                pin = str(body.get("pin", "")).strip().upper()

                # Tìm session theo sid (uid)
                target_sess: Optional[VPSSession] = None
                for sess in self.sessions.values():
                    if str(sess.user_id) == sid or sid == "":
                        if sess.pin_code == pin:
                            target_sess = sess
                            break

                if target_sess:
                    return web.json_response({
                        "ok": True,
                        "terminal_url": target_sess.terminal_url
                    })
                return web.json_response({"ok": False, "msg": "Mã PIN không chính xác!"})
            except Exception as ex:
                return web.json_response({"ok": False, "msg": f"Lỗi: {ex}"})

        app.router.add_get("/", handle_portal)
        app.router.add_get("/vps", handle_portal)
        app.router.add_post("/api/vps/verify", handle_verify)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.portal_port)
        await site.start()
        print(f"[VPS-PORTAL] Đang chạy web tại 0.0.0.0:{self.portal_port}")
        while True:
            await asyncio.sleep(3600)

    async def _start_tunnel(self):
        """Dựng Cloudflare Quick Tunnel cho Portal Server."""
        try:
            cmd = f"cloudflared tunnel --url http://127.0.0.1:{self.portal_port}"
            self._tunnel_proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # Chờ đọc URL tunnel
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                line = await self._tunnel_proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", text)
                if m:
                    self.tunnel_url = m.group(0)
                    print(f"[VPS-TUNNEL] ✅ Tunnel sẵn sàng: {self.tunnel_url}")
                    # Chờ 3s cho DNS Cloudflare kịp phân giải
                    await asyncio.sleep(3.0)
                    break
        except Exception as e:
            print(f"[VPS-TUNNEL] Không bật được cloudflared: {e}")

    async def spawn_vps(self, user_id: int, vps_name: str) -> VPSSession:
        """Kéo container máy ảo Linux từ MyBinder qua REST API stream (chỉ tốn ~8MB RAM)."""
        await self.ensure_portal_server()

        # Tạo mã PIN 6 số bí mật
        pin_code = "".join(random.choices(string.digits, k=6))

        # Stream build API
        loop = asyncio.get_running_loop()

        def _do_binder_stream():
            req = urllib.request.Request(BINDER_BUILD_URL, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                for line in resp:
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if line_str.startswith("data:"):
                        payload = line_str[5:].strip()
                        try:
                            d = json.loads(payload)
                            if d.get("phase") == "ready":
                                return d.get("url"), d.get("token")
                        except Exception:
                            pass
            return None, None

        base_url, token = await loop.run_in_executor(None, _do_binder_stream)

        if not base_url:
            raise RuntimeError("Máy chủ đám mây đang bận, vui lòng thử lại sau giây lát!")

        # Endpoint chuẩn để khởi tạo session và mở terminal
        clean_base = base_url.rstrip("/")
        terminal_url = f"{clean_base}/?token={token}"

        # Link Portal nhập PIN
        portal_base = self.tunnel_url or f"http://127.0.0.1:{self.portal_port}"
        final_portal_url = f"{portal_base}/vps?sid={user_id}&name={urllib.parse.quote(vps_name)}"

        now = time.time()
        # Thời hạn mỗi session là 60 phút
        expires_at = now + 3600.0

        sess = VPSSession(
            user_id=user_id,
            vps_name=vps_name,
            pin_code=pin_code,
            binder_url=base_url,
            binder_token=token,
            terminal_url=terminal_url,
            portal_url=final_portal_url,
            created_at=now,
            expires_at=expires_at
        )

        self.sessions[user_id] = sess
        self._save_sessions()
        return sess
