"""
Remote Browser Screencast Resolver cho Discord Login & Captcha.
Mo truc tiep trang https://discord.com/login chinh chu cua Discord tren VPS Chromium.
Stream giao dien ve trinh duyet nguoi dung qua Cloudflare Tunnel.
Nguoi dung quet ma QR hoac dang nhap / giai Captcha truc tiep tren giao dien Discord that!
Khi dang nhap thanh cong, bot lay Token truc tiep tu phien Discord tren VPS.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from typing import Awaitable, Callable, Optional, Set, Any
from aiohttp import web, WSMsgType, ClientSession, ClientTimeout

logger = logging.getLogger("remote_screen")

_SCREEN_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Discord Web Login - Trực Tiếp Trên VPS</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: #111214;
            color: #dbdee1;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            min-height: 100vh;
            padding: 12px;
            overflow-x: hidden;
            user-select: none;
            -webkit-user-select: none;
        }
        .header {
            width: 100%;
            max-width: 1020px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #2b2d31;
            padding: 10px 16px;
            border-radius: 8px;
            margin-bottom: 10px;
            border: 1px solid #35373c;
        }
        .title {
            font-size: 15px;
            font-weight: 600;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .status-badge {
            font-size: 12px;
            font-weight: 500;
            padding: 4px 10px;
            border-radius: 12px;
            background: #313338;
            color: #949ba4;
            transition: all 0.2s ease;
        }
        .status-badge.live { background: rgba(87, 242, 135, 0.15); color: #57f287; }
        .status-badge.done { background: rgba(88, 101, 242, 0.2); color: #5865f2; font-weight: bold; }
        .viewport-box {
            position: relative;
            width: 100%;
            max-width: 1000px;
            background: #1e1f22;
            border: 2px solid #35373c;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            touch-action: none;
        }
        #screen {
            display: block;
            width: 100%;
            height: auto;
            cursor: pointer;
            background-color: #1e1f22;
        }
        .instructions {
            width: 100%;
            max-width: 1000px;
            margin-top: 10px;
            font-size: 13px;
            color: #949ba4;
            text-align: center;
            line-height: 1.6;
        }
        .instructions b { color: #57f287; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">🖥️ Discord Web Login (Giao Diện VPS Thật 100%)</div>
        <div id="status" class="status-badge">Đang kết nối VPS...</div>
    </div>

    <div class="viewport-box">
        <canvas id="screen" width="1000" height="800" tabindex="0"></canvas>
    </div>

    <div class="instructions">
        👉 <b>Mẹo:</b> Mở app Discord trên điện thoại quét <b>mã QR ở góc phải</b> (hoặc nhập tài khoản / mật khẩu).<br>
        Nếu Discord yêu cầu giải Captcha, nhấp chuột trực tiếp trên màn hình này để giải. Đăng nhập xong bot tự lưu token!
    </div>

    <div id="solved-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.88); z-index:9999; flex-direction:column; align-items:center; justify-content:center;">
        <div style="background:#2b2d31; border:2px solid #57f287; padding:32px; border-radius:12px; text-align:center; max-width:440px; box-shadow:0 10px 30px rgba(0,0,0,0.6);">
            <div style="font-size:46px; margin-bottom:10px;">🎉</div>
            <h2 style="color:#57f287; margin-bottom:10px; font-size:22px;">ĐĂNG NHẬP THÀNH CÔNG!</h2>
            <p style="color:#dbdee1; margin-bottom:15px; font-size:14px; line-height:1.5;">Đã lưu Token Discord an toàn vào hệ thống Bot!</p>
            <div id="countdown-text" style="color:#949ba4; font-size:13px; margin-bottom:20px;">Tự động đóng tab sau 3s...</div>
            <button onclick="try { window.close(); } catch(e){}; location.replace('about:blank');" style="background:#5865f2; color:#fff; border:none; padding:12px 28px; border-radius:6px; font-weight:bold; font-size:14px; cursor:pointer;">Đóng Tab Ngay</button>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('screen');
        const ctx = canvas.getContext('2d');
        const statusEl = document.getElementById('status');

        let ws = null;
        let isConnected = false;
        let ripples = [];
        let currentImage = null;

        function updateStatus(text, className = '') {
            statusEl.innerText = text;
            statusEl.className = 'status-badge ' + className;
        }

        function addRipple(x, y) {
            ripples.push({ x: x, y: y, r: 5, maxR: 28, alpha: 0.85 });
            requestRender();
        }

        let renderRequested = false;
        function renderScene() {
            renderRequested = false;
            if (currentImage) {
                ctx.drawImage(currentImage, 0, 0, canvas.width, canvas.height);
            }
            if (ripples.length > 0) {
                for (let i = ripples.length - 1; i >= 0; i--) {
                    const rip = ripples[i];
                    ctx.save();
                    ctx.beginPath();
                    ctx.arc(rip.x, rip.y, rip.r, 0, Math.PI * 2);
                    ctx.strokeStyle = 'rgba(87, 242, 135, ' + rip.alpha + ')';
                    ctx.lineWidth = 3;
                    ctx.stroke();
                    ctx.restore();

                    rip.r += 2.5;
                    rip.alpha -= 0.08;
                    if (rip.alpha <= 0 || rip.r >= rip.maxR) {
                        ripples.splice(i, 1);
                    }
                }
                if (ripples.length > 0) {
                    requestRender();
                }
            }
        }

        function requestRender() {
            if (!renderRequested) {
                renderRequested = true;
                requestAnimationFrame(renderScene);
            }
        }

        function connectWS() {
            const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = proto + '//' + window.location.host + '/ws';
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                isConnected = true;
                updateStatus('🟢 VPS Đang Phát Trực Tiếp', 'live');
                while (clickQueue.length > 0) {
                    const item = clickQueue.shift();
                    ws.send(JSON.stringify(item));
                }
            };

            ws.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    if (data.type === 'frame') {
                        const img = new Image();
                        img.onload = () => {
                            // Tự động đồng bộ kích thước canvas đúng 100% với viewport thực tế của VPS
                            if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
                                canvas.width = img.naturalWidth;
                                canvas.height = img.naturalHeight;
                            }
                            currentImage = img;
                            requestRender();
                        };
                        img.src = 'data:image/jpeg;base64,' + data.data;
                    } else if (data.type === 'solved') {
                        updateStatus('🎉 ĐÃ ĐĂNG NHẬP THÀNH CÔNG!', 'done');
                        const modal = document.getElementById('solved-modal');
                        if (modal) modal.style.display = 'flex';
                        let sec = 2;
                        const cd = document.getElementById('countdown-text');
                        const itv = setInterval(() => {
                            sec--;
                            if (cd) cd.innerText = 'Đã lấy token xong! Đang đóng tab (' + sec + 's)...';
                            if (sec <= 0) {
                                clearInterval(itv);
                                try { window.close(); } catch (err) {}
                                setTimeout(() => {
                                    try { window.location.replace("about:blank"); } catch (err) {}
                                }, 300);
                            }
                        }, 1000);
                    }
                } catch (err) {}
            };

            ws.onclose = () => {
                isConnected = false;
                if (statusEl.innerText.indexOf('THÀNH CÔNG') === -1) {
                    updateStatus('🔄 Đang kết nối lại...', 'live');
                    setTimeout(connectWS, 400);
                }
            };
        }

        let lastTouchTime = 0;
        let pendingQueue = [];
        let isInteracting = false;
        let lastMoveSent = 0;
        let startCoord = null;
        let hasMoved = false;

        function sendMsg(type, payload = {}) {
            if (!isConnected || !ws || ws.readyState !== WebSocket.OPEN) {
                pendingQueue.push({ type, ...payload });
                return;
            }
            ws.send(JSON.stringify({ type: type, ...payload }));
        }

        function getCoords(clientX, clientY) {
            const rect = canvas.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return null;

            // Tính toán chuẩn xác tỷ lệ màn hình thực tế (chống lệch tâm)
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            const targetX = Math.round((clientX - rect.left) * scaleX);
            const targetY = Math.round((clientY - rect.top) * scaleY);

            return {
                x: Math.max(0, Math.min(canvas.width, targetX)),
                y: Math.max(0, Math.min(canvas.height, targetY))
            };
        }

        function handlePointerDown(clientX, clientY) {
            const pt = getCoords(clientX, clientY);
            if (!pt) return;
            isInteracting = true;
            hasMoved = false;
            startCoord = pt;
            sendMsg('down', { x: pt.x, y: pt.y });
        }

        function handlePointerMove(clientX, clientY) {
            if (!isInteracting) return;
            const pt = getCoords(clientX, clientY);
            if (!pt) return;
            const now = Date.now();
            if (Math.abs(pt.x - startCoord.x) > 4 || Math.abs(pt.y - startCoord.y) > 4) {
                hasMoved = true;
            }
            // Throttle 30ms (~33 FPS kéo) mượt mà không làm ngập mạng
            if (now - lastMoveSent > 30) {
                lastMoveSent = now;
                sendMsg('move', { x: pt.x, y: pt.y });
            }
        }

        function handlePointerUp(clientX, clientY) {
            if (!isInteracting) return;
            isInteracting = false;
            const pt = getCoords(clientX, clientY) || startCoord;
            if (pt) {
                sendMsg('up', { x: pt.x, y: pt.y });
                if (!hasMoved) {
                    addRipple(pt.x, pt.y);
                }
            }
            startCoord = null;
        }

        // Hỗ trợ cảm ứng điện thoại (Vuốt, Chạm, Kéo mảnh ghép slider captcha)
        canvas.addEventListener('touchstart', (e) => {
            e.preventDefault();
            lastTouchTime = Date.now();
            if (e.touches && e.touches.length > 0) {
                const t = e.touches[0];
                handlePointerDown(t.clientX, t.clientY);
            }
        }, { passive: false });

        window.addEventListener('touchmove', (e) => {
            if (!isInteracting) return;
            e.preventDefault();
            if (e.touches && e.touches.length > 0) {
                const t = e.touches[0];
                handlePointerMove(t.clientX, t.clientY);
            }
        }, { passive: false });

        window.addEventListener('touchend', (e) => {
            if (!isInteracting) return;
            e.preventDefault();
            lastTouchTime = Date.now();
            if (e.changedTouches && e.changedTouches.length > 0) {
                const t = e.changedTouches[0];
                handlePointerUp(t.clientX, t.clientY);
            } else {
                handlePointerUp(0, 0);
            }
        }, { passive: false });

        // Chuột trên PC (Click & Kéo thả / Drag & Drop mượt mà)
        canvas.addEventListener('mousedown', (e) => {
            if (Date.now() - lastTouchTime < 600) return;
            canvas.focus();
            handlePointerDown(e.clientX, e.clientY);
        });

        window.addEventListener('mousemove', (e) => {
            if (Date.now() - lastTouchTime < 600) return;
            handlePointerMove(e.clientX, e.clientY);
        });

        window.addEventListener('mouseup', (e) => {
            if (Date.now() - lastTouchTime < 600) return;
            handlePointerUp(e.clientX, e.clientY);
        });

        // Hỗ trợ gõ bàn phím (nếu cần nhập text)
        window.addEventListener('keydown', (e) => {
            if (document.activeElement === canvas || e.target === canvas || e.target === document.body) {
                sendMsg('keydown', { key: e.key });
            }
        });

        connectWS();
    </script>
</body>
</html>
"""


class RemoteScreenResolver:
    """Stream Chromium screencast ve web va forward input chuot + ban phim."""

    def __init__(self, page, port: int = 18888):
        self.page = page
        self.port = port
        self.ws_clients: Set[web.WebSocketResponse] = set()
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.tunnel_proc: Optional[asyncio.subprocess.Process] = None
        self.tunnel_url: Optional[str] = None
        self.is_running = True
        self.last_frame: Optional[str] = None
        self.capture_task: Optional[asyncio.Task] = None

    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=_SCREEN_HTML, content_type="text/html")

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=10.0, max_msg_size=10*1024*1024)
        await ws.prepare(request)
        self.ws_clients.add(ws)

        if self.last_frame:
            try:
                await ws.send_str(json.dumps({"type": "frame", "data": self.last_frame}))
            except Exception:
                pass

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        mtype = data.get("type")
                        x = float(data.get("x", 0))
                        y = float(data.get("y", 0))

                        if mtype == "down":
                            try:
                                await self.page.mouse.move(x, y)
                                await self.page.mouse.down()
                            except Exception:
                                pass
                        elif mtype == "move":
                            try:
                                await self.page.mouse.move(x, y)
                            except Exception:
                                pass
                        elif mtype == "up":
                            try:
                                await self.page.mouse.move(x, y)
                                await self.page.mouse.up()
                            except Exception:
                                pass
                            await asyncio.sleep(0.06)
                            if not self.page.is_closed():
                                shot = await self.page.screenshot(type="jpeg", quality=38)
                                b64 = base64.b64encode(shot).decode("ascii")
                                await self.broadcast_frame(b64)
                        elif mtype == "click":
                            try:
                                await self.page.mouse.move(x, y)
                                await self.page.mouse.click(x, y, delay=60)
                            except Exception:
                                pass
                            await asyncio.sleep(0.05)
                            if not self.page.is_closed():
                                shot = await self.page.screenshot(type="jpeg", quality=38)
                                b64 = base64.b64encode(shot).decode("ascii")
                                await self.broadcast_frame(b64)
                        elif mtype == "keydown":
                            key = str(data.get("key", ""))
                            if key:
                                await self.page.keyboard.press(key)
                    except Exception:
                        pass
        finally:
            self.ws_clients.discard(ws)
        return ws


    async def broadcast_frame(self, b64_frame: str) -> None:
        self.last_frame = b64_frame
        if not self.ws_clients:
            return
        payload = json.dumps({"type": "frame", "data": b64_frame})
        coros = [ws.send_str(payload) for ws in list(self.ws_clients) if not ws.closed]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def broadcast_solved(self) -> None:
        if not self.ws_clients:
            return
        payload = json.dumps({"type": "solved"})
        coros = [ws.send_str(payload) for ws in list(self.ws_clients) if not ws.closed]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def _run_capture_loop(self) -> None:
        """Loop chụp màn hình ổn định 5-6 FPS, chất lượng 38 nhẹ (~20KB) chống nghẽn Cloudflare."""
        while self.is_running:
            try:
                if self.ws_clients and not self.page.is_closed():
                    shot = await self.page.screenshot(type="jpeg", quality=38)
                    b64 = base64.b64encode(shot).decode("ascii")
                    await self.broadcast_frame(b64)
                    await asyncio.sleep(0.18)
                else:
                    await asyncio.sleep(0.25)
            except Exception:
                await asyncio.sleep(0.1)

    async def start(self) -> str:
        self.app = web.Application()
        self.app.router.add_get("/", self._handle_index)
        self.app.router.add_get("/ws", self._handle_ws)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await self.site.start()

        # Start tunnel
        self.tunnel_proc = await asyncio.create_subprocess_exec(
            "cloudflared",
            "tunnel",
            "--url",
            f"http://127.0.0.1:{self.port}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        deadline = time.monotonic() + 20.0
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
                    self.tunnel_url = m.group(0)
                    break
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

        if not self.tunnel_url:
            await self.stop()
            raise RuntimeError("Không thể lấy URL Cloudflare Tunnel.")

        self.capture_task = asyncio.create_task(self._run_capture_loop())
        return self.tunnel_url

    async def stop(self) -> None:
        self.is_running = False
        if self.capture_task:
            self.capture_task.cancel()
            self.capture_task = None

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


async def _extract_discord_app_token(page) -> str:
    """Lấy token người dùng từ phiên đăng nhập thật của Discord (localStorage / webpack / sessionStorage / cookies)."""
    js = """
    (() => {
        const tokenRegex = /[A-Za-z0-9_-]{24,28}\\.[A-Za-z0-9_-]{6}\\.[A-Za-z0-9_-]{27,38}/;

        // 1. Quét toàn bộ localStorage
        try {
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                const val = localStorage.getItem(k);
                if (typeof val === "string") {
                    const m = val.match(tokenRegex);
                    if (m && m[0].length >= 50) return m[0];
                }
            }
        } catch(e) {}

        // 2. Quét sessionStorage
        try {
            for (let i = 0; i < sessionStorage.length; i++) {
                const k = sessionStorage.key(i);
                const val = sessionStorage.getItem(k);
                if (typeof val === "string") {
                    const m = val.match(tokenRegex);
                    if (m && m[0].length >= 50) return m[0];
                }
            }
        } catch(e) {}

        // 3. Webpack chunk inspection
        try {
            const wp = window.webpackChunkdiscord_app;
            if (wp && Array.isArray(wp)) {
                let token = "";
                wp.push([[Symbol("tris_cipher")], {}, e => {
                    if (!e || !e.c) return;
                    for (let m in e.c) {
                        const mod = e.c[m]?.exports;
                        if (!mod) continue;
                        const cand = mod?.default?.getToken?.() || mod?.getToken?.();
                        if (typeof cand === "string" && cand.length >= 50) {
                            token = cand;
                            break;
                        }
                    }
                }]);
                if (token) return token;
            }
        } catch(e) {}

        // 4. Kiểm tra iframe
        try {
            const ifrs = document.querySelectorAll('iframe');
            for (const ifr of ifrs) {
                try {
                    const cWin = ifr.contentWindow;
                    if (cWin && cWin.localStorage) {
                        for (let i = 0; i < cWin.localStorage.length; i++) {
                            const val = cWin.localStorage.getItem(cWin.localStorage.key(i));
                            if (typeof val === "string") {
                                const m = val.match(tokenRegex);
                                if (m && m[0].length >= 50) return m[0];
                            }
                        }
                    }
                } catch(e) {}
            }
        } catch(e) {}

        return "";
    })()
    """
    try:
        val = await page.evaluate(js)
        if val and isinstance(val, str) and len(val) >= 50:
            return val
    except Exception:
        pass
    return ""


async def _fetch_user_profile(token: str) -> dict:
    """Lấy thông tin cơ bản của user bằng token vừa đăng nhập."""
    try:
        async with ClientSession(timeout=ClientTimeout(total=10)) as session:
            async with session.get(
                "https://discord.com/api/v9/users/@me",
                headers={"Authorization": token, "Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return {}


async def solve_via_direct_discord_web(
    on_notice: Optional[Callable[[str], Awaitable[None]]] = None,
    timeout: float = 240.0,
):
    """Mở thẳng giao diện đăng nhập Discord thật (https://discord.com/login) trên VPS.

    Stream màn hình qua Cloudflare Tunnel cho người dùng quét mã QR hoặc đăng nhập.
    Bypass 100% cơ chế chống bot và hCaptcha Enterprise vì chạy trên Client thật của Discord!
    """
    from playwright.async_api import async_playwright
    from .qr_login import _ai_stealth_hook, _UA, RemoteAuthResult, RemoteAuthError

    async with async_playwright() as pw:
        _ai_stealth_hook(pw)
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--lang=vi-VN,vi",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
            ],
        )
        try:
            page = await browser.new_page(
                viewport={"width": 1000, "height": 800},
                user_agent=_UA,
                locale="vi-VN",
                extra_http_headers={"Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"},
            )

            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except Exception:
                pass

            captured_tokens: list = []

            def _on_req(req):
                try:
                    auth = req.headers.get("authorization") or ""
                    if auth and not auth.lower().startswith("bot ") and len(auth) >= 50:
                        clean_tok = auth.strip('"\' ')
                        if clean_tok not in captured_tokens:
                            print(f"[DIRECT-DISCORD] Bắt được token từ request header: {req.url[:60]}...", flush=True)
                            captured_tokens.append(clean_tok)
                except Exception:
                    pass

            async def _on_res(res):
                try:
                    u = res.url or ""
                    if any(ep in u for ep in ("/api/v9/auth/login", "/api/v9/users/@me/remote-auth/login", "/api/v9/users/@me")):
                        if res.status == 200:
                            try:
                                data = await res.json()
                                if isinstance(data, dict):
                                    tok = data.get("token")
                                    if isinstance(tok, str) and len(tok) >= 50 and tok not in captured_tokens:
                                        print(f"[DIRECT-DISCORD] Bắt được token từ auth response JSON: {u[:60]}...", flush=True)
                                        captured_tokens.append(tok.strip('"\' '))
                            except Exception:
                                pass
                except Exception:
                    pass

            page.on("request", _on_req)
            page.on("response", _on_res)

            print("[DIRECT-DISCORD] Đang nạp trang Discord Login thật...", flush=True)
            try:
                await page.goto("https://discord.com/login", wait_until="load", timeout=35000)
            except Exception:
                pass

            # Khởi động Screencast Server & Tunnel
            server = RemoteScreenResolver(page)
            try:
                tunnel_url = await server.start()
                msg = (
                    f"\n{'='*68}\n"
                    f"🖥️  [DISCORD DIRECT LOGIN] MỞ GIAO DIỆN DISCORD THẬT TRÊN VPS:\n"
                    f"👉 Link điều khiển & quét mã QR trực tiếp trên VPS:\n"
                    f"🔗 {tunnel_url}\n"
                    f"⏳ Thời gian chờ: {int(timeout)}s (quét mã QR hoặc đăng nhập trực tiếp!)\n"
                    f"{'='*68}\n"
                )
                print(msg, flush=True)

                if on_notice:
                    try:
                        await on_notice(
                            f"🖥️ **Đăng nhập Discord trực tiếp trên VPS (Chính chủ Discord):**\n"
                            f"👉 [Bấm vào đây để mở màn hình VPS]({tunnel_url})\n"
                            f"*(Mở link -> quét mã QR ở góc phải bằng app Discord mobile hoặc đăng nhập!)*"
                        )
                    except Exception:
                        pass

                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    token = (captured_tokens[0] if captured_tokens else "") or (await _extract_discord_app_token(page))
                    if not token and ("/channels/" in page.url or "@me" in page.url):
                        await asyncio.sleep(0.5)
                        token = (captured_tokens[0] if captured_tokens else "") or (await _extract_discord_app_token(page))

                    if token and len(token) >= 50:
                        print("[DIRECT-DISCORD] Đăng nhập thành công! Bắt được token từ Discord Client!", flush=True)
                        profile = await _fetch_user_profile(token)
                        uid = profile.get("id")
                        uname = profile.get("username")
                        avatar = profile.get("avatar")

                        await server.broadcast_solved()
                        await asyncio.sleep(1.5)
                        return RemoteAuthResult(
                            token=token,
                            user_id=uid,
                            username=uname,
                            avatar=avatar,
                        )

                    await asyncio.sleep(1.0)

                raise RemoteAuthError("timeout", f"Hết thời gian chờ đăng nhập Discord ({int(timeout)}s).")
            finally:
                await server.stop()
        finally:
            await browser.close()


async def solve_via_discord_web_qr(
    on_qr_image: Optional[Callable[[bytes], Awaitable[None]]] = None,
    on_notice: Optional[Callable[[str], Awaitable[None]]] = None,
    timeout: float = 600.0,
) -> RemoteAuthResult:
    """Mở https://discord.com/login trên Chromium VPS SIÊU TỐC, chụp ảnh mã QR gửi ra Discord để quét.
    Chỉ khi Discord xuất hiện hộp thoại giải Captcha thì MỚI kích hoạt Screencast Cloudflare tunnel và gửi link.
    Sau khi quét / giải captcha xong, bắt Token trực tiếp từ Discord client trên VPS và tự tắt tab web.
    """
    from playwright.async_api import async_playwright
    from .qr_login import _ai_stealth_hook, _UA, RemoteAuthResult, RemoteAuthError

    async with async_playwright() as pw:
        _ai_stealth_hook(pw)
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        server: Optional[RemoteScreenResolver] = None
        try:
            page = await browser.new_page(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9,vi;q=0.8"},
            )

            captured_tokens: list = []

            def _on_qr_req(req):
                try:
                    auth = req.headers.get("authorization") or ""
                    if auth and not auth.lower().startswith("bot ") and len(auth) >= 50:
                        clean_tok = auth.strip('"\' ')
                        if clean_tok not in captured_tokens:
                            print(f"[DISCORD-WEB-QR] Bắt được token từ request header: {req.url[:60]}...", flush=True)
                            captured_tokens.append(clean_tok)
                except Exception:
                    pass

            async def _on_qr_res(res):
                try:
                    u = res.url or ""
                    if any(ep in u for ep in ("/api/v9/auth/login", "/api/v9/users/@me/remote-auth/login", "/api/v9/users/@me")):
                        if res.status == 200:
                            try:
                                data = await res.json()
                                if isinstance(data, dict):
                                    tok = data.get("token")
                                    if isinstance(tok, str) and len(tok) >= 50 and tok not in captured_tokens:
                                        print(f"[DISCORD-WEB-QR] Bắt được token từ auth response JSON: {u[:60]}...", flush=True)
                                        captured_tokens.append(tok.strip('"\' '))
                            except Exception:
                                pass
                except Exception:
                    pass

            page.on("request", _on_qr_req)
            page.on("response", _on_qr_res)

            print("[DISCORD-WEB-QR] Đang nạp https://discord.com/login trên VPS...", flush=True)
            try:
                await page.goto("https://discord.com/login", wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"[DISCORD-WEB-QR] Warning goto: {e}", flush=True)

            # ── Vòng lặp chờ mã QR THẬT (loại bỏ spinner) ──
            qr_buf: Optional[bytes] = None
            print("[DISCORD-WEB-QR] Đang chờ mã QR thật hiển thị (bỏ qua loading spinner)...", flush=True)

            for attempt in range(25):
                await asyncio.sleep(1.0)

                # Kiểm tra trạng thái container QR qua JS
                status = await page.evaluate('''() => {
                    // 1. Kiểm tra captcha trước
                    const iframes = Array.from(document.querySelectorAll('iframe'));
                    for (const ifr of iframes) {
                        if ((ifr.src||'').includes('hcaptcha') || (ifr.title||'').toLowerCase().includes('hcaptcha')) {
                            return {captcha: true};
                        }
                    }

                    // 2. Tìm container QR
                    const container = document.querySelector('div[class*="qrCodeContainer"]');
                    if (!container) return {status: 'loading'};

                    // Kiểm tra xem còn spinner hoặc aria-busy không
                    const isBusy = container.querySelector('[aria-busy="true"]') !== null;
                    const hasSpinner = container.querySelector('[class*="spinner"]') !== null;
                    const svgs = container.querySelectorAll('svg');

                    if (!isBusy && !hasSpinner && svgs.length > 0) {
                        return {status: 'ready', svgs: svgs.length};
                    }
                    return {status: 'busy'};
                }''')

                if status.get("captcha"):
                    print("[DISCORD-WEB-QR] Discord yêu cầu giải Captcha trước khi hiện QR.", flush=True)
                    break

                if status.get("status") == "ready":
                    # Mã QR đã render xong! Chụp đúng element chứa QR
                    try:
                        # Thử selector chứa QR style 160px
                        qr_loc = page.locator('div[class*="qrCodeContainer"][style*="160px"]').first
                        if await qr_loc.count() > 0:
                            qr_buf = await qr_loc.screenshot(timeout=3000)

                        if not qr_buf:
                            # Thử SVG parent
                            svg_loc = page.locator('div[class*="qrCodeContainer"] svg').first
                            if await svg_loc.count() > 0:
                                qr_buf = await svg_loc.locator("..").screenshot(timeout=3000)

                        if not qr_buf:
                            # Thử role img
                            role_loc = page.locator('div[role="img"][aria-label*="QR code"]').first
                            if await role_loc.count() > 0:
                                qr_buf = await role_loc.screenshot(timeout=3000)

                        if qr_buf and len(qr_buf) > 1000:
                            print(f"[DISCORD-WEB-QR] ✅ Đã chụp mã QR thật thành công ({len(qr_buf)} bytes) tại attempt {attempt+1}!", flush=True)
                            break
                    except Exception as e:
                        print(f"[DISCORD-WEB-QR] Lỗi khi chụp element: {e}", flush=True)

            # Fallback nếu element screenshot thất bại: crop theo tọa độ chuẩn từ screenshot
            if not qr_buf:
                try:
                    full_shot = await page.screenshot()
                    from PIL import Image
                    import io
                    im = Image.open(io.BytesIO(full_shot))
                    # Vùng QR trên màn hình 1280x720: x: 792..968, y: 200..376
                    cropped = im.crop((790, 198, 970, 378))
                    out_crop = io.BytesIO()
                    cropped.save(out_crop, format="PNG")
                    qr_buf = out_crop.getvalue()
                    print(f"[DISCORD-WEB-QR] Fallback crop tọa độ QR: {len(qr_buf)} bytes.", flush=True)
                except Exception as ex:
                    print(f"[DISCORD-WEB-QR] Fallback crop failed: {ex}", flush=True)

            if qr_buf:
                print(f"[DISCORD-WEB-QR] Gửi ảnh QR ra kênh ({len(qr_buf)} bytes)...", flush=True)
            if on_qr_image:
                try:
                    await on_qr_image(qr_buf)
                except Exception as exc:
                    print(f"[DISCORD-WEB-QR] Lỗi gửi ảnh QR: {exc}", flush=True)

            tunnel_active = False
            captcha_cleared_notified = False
            deadline = time.monotonic() + timeout

            while time.monotonic() < deadline:
                # 1. Kiểm tra nếu đã bắt được token qua network hoặc trích xuất từ Discord Client
                token = (captured_tokens[0] if captured_tokens else "") or (await _extract_discord_app_token(page))
                if not token and ("/channels/" in page.url or "@me" in page.url):
                    await asyncio.sleep(0.5)
                    token = (captured_tokens[0] if captured_tokens else "") or (await _extract_discord_app_token(page))

                if token and len(token) >= 50:
                    print("[DISCORD-WEB-QR] Đăng nhập thành công! Bắt được token từ Discord Client!", flush=True)
                    if server:
                        await server.broadcast_solved()
                        await asyncio.sleep(1.0)
                    profile = await _fetch_user_profile(token)
                    return RemoteAuthResult(
                        token=token,
                        user_id=profile.get("id"),
                        username=profile.get("username"),
                        avatar=profile.get("avatar"),
                    )

                # 2. Kiểm tra nếu Discord bắt giải captcha -> MỚI MỞ LINK SCREENCAST
                if not tunnel_active:
                    has_captcha = await page.evaluate('''() => {
                        const iframes = Array.from(document.querySelectorAll('iframe'));
                        for (const ifr of iframes) {
                            const src = ifr.src || '';
                            const title = ifr.title || '';
                            if (src.includes('hcaptcha.com') || title.toLowerCase().includes('hcaptcha')) return true;
                        }
                        if (document.querySelector('iframe[src*="hcaptcha"], div[class*="h-captcha"]')) return true;
                        return false;
                    }''')
                    if has_captcha:
                        print("[DISCORD-WEB-QR] Discord yêu cầu giải Captcha! Đang mở Remote Screencast...", flush=True)
                        tunnel_active = True
                        server = RemoteScreenResolver(page)
                        try:
                            tunnel_url = await server.start()
                            if on_notice:
                                await on_notice(
                                    f"🧩 Discord yêu cầu xác minh Captcha: [Bấm vào đây để mở màn hình giải trên VPS]({tunnel_url})\n"
                                    f"*(Giải xong trên màn hình, Discord sẽ tự động hoàn tất đăng nhập!)*"
                                )
                        except Exception as exc:
                            print(f"[DISCORD-WEB-QR] Lỗi bật tunnel: {exc}", flush=True)
                            if on_notice:
                                await on_notice(f"⚠️ Lỗi kết nối màn hình giải captcha: {exc}")

                # 3. Khi vừa giải xong Captcha (modal biến mất): Tự động chụp mã QR mới gửi ra kênh
                if tunnel_active and not captcha_cleared_notified:
                    still_captcha = await page.evaluate('''() => {
                        const iframes = Array.from(document.querySelectorAll('iframe'));
                        for (const ifr of iframes) {
                            const src = ifr.src || '';
                            const title = ifr.title || '';
                            if (src.includes('hcaptcha.com') || title.toLowerCase().includes('hcaptcha')) return true;
                        }
                        if (document.querySelector('iframe[src*="hcaptcha"], div[class*="h-captcha"]')) return true;
                        return false;
                    }''')
                    if not still_captcha:
                        captcha_cleared_notified = True
                        print("[DISCORD-WEB-QR] Captcha đã giải xong! Đang cập nhật mã QR sạch...", flush=True)
                        await asyncio.sleep(1.2)
                        if on_notice:
                            await on_notice(
                                "✅ **Đã giải xong Captcha!** Discord đã mở khóa mã QR sạch — "
                                "Tris quét ngay mã ở góc phải màn hình VPS (hoặc ảnh QR mới bên dưới) là vào thẳng:"
                            )
                        try:
                            qr_el = page.locator('div[class*="qrCodeContainer"][style*="160px"]').first
                            new_qr = await qr_el.screenshot(timeout=3000)
                            if on_qr_image:
                                await on_qr_image(new_qr)
                        except Exception as exc:
                            print(f"[DISCORD-WEB-QR] Lỗi chụp QR mới: {exc}", flush=True)

                # 4. Tự click nút refresh QR nếu Discord báo hết hạn trên trang web
                if not tunnel_active:
                    ref_btn = page.locator(
                        "button:has-text('Refresh'), button:has-text('Tải lại'), button:has-text('regenerate')"
                    )
                    if await ref_btn.count() > 0:
                        try:
                            await ref_btn.first.click()
                            # Chờ QR mới render xong rồi chụp lại
                            await asyncio.sleep(2.5)
                            qr_el = page.locator('div[class*="qrCodeContainer"][style*="160px"]').first
                            if await qr_el.count() > 0:
                                new_qr = await qr_el.screenshot(timeout=3000)
                                if new_qr and len(new_qr) > 1000:
                                    print(f"[DISCORD-WEB-QR] 🔄 QR hết hạn → đã lấy QR mới ({len(new_qr)} bytes).", flush=True)
                                    if on_qr_image:
                                        try:
                                            await on_qr_image(new_qr)
                                        except Exception:
                                            pass
                        except Exception:
                            pass

                await asyncio.sleep(1.0)


            raise RemoteAuthError("timeout", f"Hết thời gian chờ đăng nhập Discord ({int(timeout)}s).")
        finally:
            if server:
                try:
                    await server.stop()
                except Exception:
                    pass
            try:
                await browser.close()
            except Exception:
                pass


async def setup(bot):
    """Extension entrypoint (empty cog for utility module)."""
    pass
