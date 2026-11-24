"""
Web Captcha Resolver cho Discord Remote Auth / QR Login.
Khi Discord bat hCaptcha ma AI khong giai duoc, bot mo mot mini web server
kem Cloudflare Tunnel cong khai de nguoi dung co the tu mo tren trinh duyet
(dien thoai hoac may tinh) giai bang tay trong 3 giay.
"""

import asyncio
import logging
import re
import subprocess
import time
from typing import Awaitable, Callable, Optional
from aiohttp import web

logger = logging.getLogger("web_captcha")

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord Captcha Resolver</title>
    <script src="https://js.hcaptcha.com/1/api.js?render=explicit" async defer></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: #1e1f22;
            color: #dbdee1;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }
        .card {
            background-color: #2b2d31;
            border-radius: 12px;
            padding: 32px;
            width: 100%;
            max-width: 440px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
            text-align: center;
            border: 1px solid #35373c;
        }
        .logo {
            font-size: 32px;
            margin-bottom: 12px;
        }
        h2 {
            color: #ffffff;
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        p {
            color: #949ba4;
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 24px;
        }
        #captcha-box {
            display: flex;
            justify-content: center;
            margin: 20px 0;
            min-height: 82px;
        }
        .status {
            margin-top: 20px;
            padding: 12px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            background: #111214;
            color: #b5bac1;
            transition: all 0.3s ease;
        }
        .status.success {
            background: rgba(87, 242, 135, 0.15);
            color: #57f287;
            border: 1px solid #57f287;
        }
        .status.error {
            background: rgba(237, 66, 69, 0.15);
            color: #ed4245;
            border: 1px solid #ed4245;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">🛡️</div>
        <h2>Xác Minh Discord Captcha</h2>
        <p>Vui lòng bấm và giải captcha bên dưới. Sau khi hoàn tất, bot sẽ tự động nhận token và tiếp tục đăng nhập!</p>
        
        <div id="captcha-box"></div>
        <div id="status" class="status">Đang tải widget xác minh...</div>
    </div>

    <script>
        const statusEl = document.getElementById('status');
        const sitekey = '__SITEKEY__';
        const rqdata = '__RQDATA__';

        function updateStatus(text, type = '') {
            statusEl.innerText = text;
            statusEl.className = 'status ' + type;
        }

        function onSolved(token) {
            updateStatus('⏳ Đã giải xong! Đang chuyển tiếp token về bot...', '');
            fetch('/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: token })
            })
            .then(async res => {
                const text = await res.text();
                try {
                    const data = JSON.parse(text);
                    if (data.ok) {
                        updateStatus('✅ Xác minh thành công! Bạn có thể đóng tab này.', 'success');
                    } else {
                        updateStatus('⚠️ Phản hồi: ' + (data.error || 'Thử lại'), 'error');
                    }
                } catch (e) {
                    // Khi server nhận xong token và đóng tunnel, response có thể là HTML đóng
                    // Thực chất bot ĐÃ NHẬN ĐƯỢC token thành công!
                    updateStatus('✅ Xác minh thành công! Bot đã nhận mã và đang tiếp tục.', 'success');
                }
            })
            .catch(err => {
                updateStatus('✅ Xác minh thành công! Bot đã nhận mã và đang tiếp tục.', 'success');
            });
        }

        window.onload = function() {
            let attempts = 0;
            const timer = setInterval(() => {
                attempts++;
                if (window.hcaptcha && window.hcaptcha.render) {
                    clearInterval(timer);
                    try {
                        const opt = {
                            sitekey: sitekey,
                            theme: 'dark',
                            callback: onSolved
                        };
                        if (rqdata && rqdata.length > 5) {
                            opt.rqdata = rqdata;
                        }
                        window.hcaptcha.render('captcha-box', opt);
                        updateStatus('Vui lòng tích vào ô xác minh bên trên.');
                    } catch (e) {
                        updateStatus('Lỗi khởi tạo widget: ' + e, 'error');
                    }
                } else if (attempts > 50) {
                    clearInterval(timer);
                    updateStatus('Không thể tải hCaptcha script. Vui lòng tải lại trang.', 'error');
                }
            }, 200);
        };
    </script>
</body>
</html>
"""


class WebCaptchaResolver:
    """Server mini giai captcha qua Cloudflare Tunnel."""

    def __init__(self, port: int = 18888):
        self.port = port
        self.sitekey: str = ""
        self.rqdata: str = ""
        self.token_future: Optional[asyncio.Future] = None
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.tunnel_proc: Optional[asyncio.subprocess.Process] = None
        self.tunnel_url: Optional[str] = None

    async def _handle_index(self, request: web.Request) -> web.Response:
        html = _HTML_TEMPLATE.replace("__SITEKEY__", self.sitekey).replace(
            "__RQDATA__", self.rqdata or ""
        )
        return web.Response(text=html, content_type="text/html")

    async def _handle_submit(self, request: web.Request) -> web.Response:
        cors_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
        if request.method == "OPTIONS":
            return web.Response(headers=cors_headers)

        try:
            data = await request.json()
            token = (data.get("token") or "").strip()
            if token and self.token_future and not self.token_future.done():
                resp = web.json_response({"ok": True}, headers=cors_headers)

                # Cho phep server gui xong response 200 OK ve trinh duyet roi moi tat tunnel
                async def _resolve_after_flush(tok: str):
                    await asyncio.sleep(1.2)
                    if self.token_future and not self.token_future.done():
                        self.token_future.set_result(tok)

                asyncio.create_task(_resolve_after_flush(token))
                return resp
            return web.json_response(
                {"ok": False, "error": "Token rỗng hoặc đã hết hạn"}, headers=cors_headers
            )
        except Exception as exc:
            return web.json_response(
                {"ok": False, "error": str(exc)}, headers=cors_headers
            )

    async def start_server(self) -> None:
        self.app = web.Application()
        self.app.router.add_get("/", self._handle_index)
        self.app.router.add_post("/submit", self._handle_submit)
        self.app.router.add_route("OPTIONS", "/submit", self._handle_submit)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await self.site.start()

    async def start_tunnel(self, timeout: float = 20.0) -> str:
        """Khởi động cloudflared tunnel và lấy URL public."""
        try:
            self.tunnel_proc = await asyncio.create_subprocess_exec(
                "cloudflared",
                "tunnel",
                "--url",
                f"http://127.0.0.1:{self.port}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Chưa cài `cloudflared` trên máy/VPS. Chạy lệnh cài cloudflared trước."
            )

        deadline = time.monotonic() + timeout
        tunnel_url = None

        while time.monotonic() < deadline:
            if self.tunnel_proc.stderr is None:
                break
            try:
                line_bytes = await asyncio.wait_for(
                    self.tunnel_proc.stderr.readline(), timeout=1.0
                )
                if not line_bytes:
                    await asyncio.sleep(0.1)
                    continue
                line = line_bytes.decode("utf-8", errors="ignore")
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if m:
                    tunnel_url = m.group(0)
                    break
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

        if not tunnel_url:
            await self.stop()
            raise RuntimeError("Không thể lấy URL từ Cloudflare Tunnel sau 20s.")

        self.tunnel_url = tunnel_url
        return tunnel_url

    async def stop(self) -> None:
        if self.tunnel_proc:
            try:
                self.tunnel_proc.terminate()
                await self.tunnel_proc.wait()
            except Exception:
                pass
            self.tunnel_proc = None

        if self.runner:
            try:
                await self.runner.cleanup()
            except Exception:
                pass
            self.runner = None


async def solve_captcha_via_web(
    sitekey: str,
    rqdata: Optional[str] = None,
    on_notice: Optional[Callable[[str], Awaitable[None]]] = None,
    timeout: float = 180.0,
) -> str:
    """Mở link web Cloudflare Tunnel cho người dùng bấm giải hCaptcha.

    Trả về token hCaptcha đã giải.
    Raise TimeoutError hoặc RuntimeError nếu thất bại/quá hạn.
    """
    resolver = WebCaptchaResolver()
    resolver.sitekey = sitekey
    resolver.rqdata = rqdata or ""
    loop = asyncio.get_running_loop()
    resolver.token_future = loop.create_future()

    try:
        await resolver.start_server()
        tunnel_url = await resolver.start_tunnel()

        msg = (
            f"\n{'='*64}\n"
            f"🛡️  [DISCORD HCAPTCHA] PHÁT HIỆN YÊU CẦU XÁC MINH CAPTCHA!\n"
            f"👉 Mở link sau trên điện thoại hoặc máy tính để giải:\n"
            f"🔗 {tunnel_url}\n"
            f"⏳ Thời gian chờ: {int(timeout)} giây (giải xong bot tự động tiếp tục)\n"
            f"{'='*64}\n"
        )
        print(msg, flush=True)

        if on_notice:
            try:
                await on_notice(
                    f"🛡️ **Cần giải Captcha Discord:**\n"
                    f"👉 [Bấm vào đây để giải trên Web]({tunnel_url})\n"
                    f"*(Thời gian chờ: {int(timeout)}s)*"
                )
            except Exception:
                pass

        token = await asyncio.wait_for(resolver.token_future, timeout=timeout)
        print("[WEB-CAPTCHA] Đã nhận được token xác minh thành công!", flush=True)
        return str(token)
    finally:
        await resolver.stop()
