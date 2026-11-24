import asyncio
import aiohttp
import logging
import re
from typing import Optional, List, Dict, Any

import discord
from discord.voice_client import VoiceClient

logger = logging.getLogger("LavalinkVoice")

LAVALINK_NODES = [
    {
        "identifier": "MilloHost-SSL",
        "rest_uri": "https://lava-v4.millohost.my.id",
        "ws_uri": "wss://lava-v4.millohost.my.id/v4/websocket",
        "password": "https://discord.gg/mjS5J2K3ep"
    },
    {
        "identifier": "AjieBlogs-SSL",
        "rest_uri": "https://lava-v4.ajieblogs.eu.org",
        "ws_uri": "wss://lava-v4.ajieblogs.eu.org/v4/websocket",
        "password": "https://dsc.gg/ajidevserver"
    },
    {
        "identifier": "Serenetia-SSL",
        "rest_uri": "https://lavalinkv4.serenetia.com",
        "ws_uri": "wss://lavalinkv4.serenetia.com/v4/websocket",
        "password": "https://seretia.link/discord"
    }
]

# Lavalink >= 4.2.0 moi ho tro DAVE (E2EE voice) va BAT BUOC client gui kem
# "channelId" trong voice payload. Node cu hon -> phai dung cau DAVE cuc bo.
DAVE_MIN_LAVALINK = (4, 2, 0)


def _safe_log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(str(msg).encode("ascii", "ignore").decode("ascii"), flush=True)
        except Exception:
            pass


class LavalinkNode:
    def __init__(self, identifier: str, rest_uri: str, ws_uri: str, password: str, client_user_id: str):
        self.identifier = identifier
        self.rest_uri = rest_uri.rstrip("/")
        self.ws_uri = ws_uri
        self.password = password
        self.client_user_id = str(client_user_id)
        self.session_id: Optional[str] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.is_connected = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._closing: bool = False
        self._lock = asyncio.Lock()

    def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=15)
            )
        return self._session

    async def _close_ws_internal(self):
        if self.ws and not self.ws.closed:
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None

    async def connect(self, timeout: float = 10.0) -> bool:
        async with self._lock:
            if self.is_connected and self.session_id and self.ws and not self.ws.closed:
                return True

            await self._close_ws_internal()
            self.is_connected = False
            self.session_id = None

            session = self._get_session()
            headers = {
                "Authorization": self.password,
                "User-Id": self.client_user_id,
                "Client-Name": "SelfBot-Lavalink/1.0"
            }

            try:
                self.ws = await session.ws_connect(
                    self.ws_uri,
                    headers=headers,
                    heartbeat=30.0,
                    timeout=aiohttp.ClientWSTimeout(ws_close=10.0)
                )
            except Exception as e:
                logger.warning(f"[Lavalink] Failed ws_connect to {self.identifier}: {e}")
                return False

            # Bat buoc cho nhan 'op': 'ready' de lay sessionId
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                try:
                    time_left = max(0.5, deadline - asyncio.get_event_loop().time())
                    msg = await asyncio.wait_for(self.ws.receive(), timeout=min(time_left, 5.0))
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.warning(f"[Lavalink] Receive error during handshake on {self.identifier}: {e}")
                    break

                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = msg.json()
                    except Exception:
                        continue
                    if data.get("op") == "ready":
                        self.session_id = data.get("sessionId")
                        self.is_connected = True
                        logger.info(f"[Lavalink READY] Node {self.identifier} session: {self.session_id}")
                        _safe_log(f"[Lavalink READY] Node {self.identifier} session: {self.session_id}")

                        if self._listen_task and not self._listen_task.done():
                            self._listen_task.cancel()
                        self._listen_task = asyncio.create_task(self._listen_loop())
                        return True
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                    close_code = getattr(self.ws, "close_code", None)
                    logger.warning(f"[Lavalink] WS closed early on {self.identifier} (code={close_code})")
                    break

            await self._close_ws_internal()
            self.is_connected = False
            self.session_id = None
            return False

    async def _listen_loop(self):
        try:
            if not self.ws:
                return
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = msg.json()
                        if data.get("op") == "ready":
                            self.session_id = data.get("sessionId")
                    except Exception:
                        pass
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSING):
                    break
        except Exception as e:
            logger.debug(f"[Lavalink] Listen loop ended for {self.identifier}: {e}")
        finally:
            self.is_connected = False
            self.session_id = None
            if not self._closing:
                self._trigger_reconnect()

    def _trigger_reconnect(self):
        if self._closing:
            return
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_worker())

    async def _reconnect_worker(self):
        delay = 2.0
        max_delay = 30.0
        while not self._closing and not (self.is_connected and self.session_id):
            await asyncio.sleep(delay)
            if self._closing:
                break
            logger.info(f"[Lavalink 🔄] Dang ket noi lai node {self.identifier} (backoff {delay:.1f}s)...")
            ok = await self.connect(timeout=8.0)
            if ok:
                logger.info(f"[Lavalink 🟢] Da ket noi lai thanh cong node {self.identifier}!")
                break
            delay = min(max_delay, delay * 1.5)

    async def close(self):
        self._closing = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        await self._close_ws_internal()
        if self._session and not self._session.closed:
            await self._session.close()
        self.is_connected = False
        self.session_id = None

    async def search(self, identifier: str) -> List[Dict[str, Any]]:
        session = self._get_session()
        url = f"{self.rest_uri}/v4/loadtracks"
        params = {"identifier": identifier}
        headers = {"Authorization": self.password}

        try:
            async with session.get(
                url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    load_type = data.get("loadType")
                    if load_type in ("track", "short"):
                        t_data = data.get("data")
                        return [t_data] if t_data else []
                    elif load_type == "playlist":
                        p_data = data.get("data", {})
                        if isinstance(p_data, dict):
                            return p_data.get("tracks", [])
                        return []
                    elif load_type in ("search", "empty"):
                        s_data = data.get("data", [])
                        return s_data if isinstance(s_data, list) else []
        except Exception as e:
            logger.error(f"[Lavalink SEARCH ERR] {self.identifier}: {e}")
        return []

    async def get_info(self) -> Optional[dict]:
        """Thong tin node (version, sourceManagers...) de biet co ho tro DAVE hay khong."""
        session = self._get_session()
        try:
            async with session.get(
                f"{self.rest_uri}/v4/info",
                headers={"Authorization": self.password},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.debug(f"[Lavalink INFO ERR] {self.identifier}: {e}")
        return None

    async def get_player(self, guild_id: int) -> Optional[dict]:
        """Trang thai player (track/volume/state.connected) - dung de biet Lavalink
        da thuc su noi duoc voice gateway chua (node cu / DAVE bi tu choi -> False)."""
        if not self.session_id:
            return None
        session = self._get_session()
        url = f"{self.rest_uri}/v4/sessions/{self.session_id}/players/{guild_id}"
        try:
            async with session.get(
                url, headers={"Authorization": self.password}, timeout=aiohttp.ClientTimeout(total=6)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.debug(f"[Lavalink PLAYER GET ERR] {self.identifier}: {e}")
        return None

    async def update_player(self, guild_id: int, payload: dict) -> bool:
        if not self.session_id:
            return False
        session = self._get_session()
        url = f"{self.rest_uri}/v4/sessions/{self.session_id}/players/{guild_id}"
        headers = {"Authorization": self.password, "Content-Type": "application/json"}

        try:
            async with session.patch(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status not in (200, 204):
                    err_txt = await resp.text()
                    logger.error(f"[Lavalink PLAYER UPDATE ERR] {self.identifier} HTTP {resp.status}: {err_txt}")
                    _safe_log(f"[Lavalink PLAYER UPDATE ERR] HTTP {resp.status}: {err_txt}")
                    return False
                return True
        except Exception as e:
            logger.error(f"[Lavalink PLAYER UPDATE ERR] {self.identifier}: {e}")
            return False

    async def destroy_player(self, guild_id: int) -> bool:
        if not self.session_id:
            return False
        session = self._get_session()
        url = f"{self.rest_uri}/v4/sessions/{self.session_id}/players/{guild_id}"
        headers = {"Authorization": self.password}
        try:
            async with session.delete(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False


def _extract_bot_user_id(bot) -> str:
    """Lay Discord Snowflake User-Id hop le (Lavalink cam User-Id: 0)."""
    if bot and getattr(bot, "user", None) and getattr(bot.user, "id", None):
        return str(bot.user.id)
    try:
        from apps.user_discord.utils.prefix import token_of
        from apps.shared.token_crypto import decrypt
        tok = decrypt(token_of(bot)) if bot else ""
        if tok and "." in tok:
            import base64
            p1 = tok.split(".")[0]
            p1 += "=" * ((4 - len(p1) % 4) % 4)
            uid = base64.b64decode(p1.encode("ascii")).decode("ascii", "ignore").strip()
            if uid.isdigit() and len(uid) >= 15:
                return uid
    except Exception:
        pass
    return "1399783451397193840"


class LavalinkManager:
    _instance = None

    def __init__(self, bot):
        self.bot = bot
        user_id = _extract_bot_user_id(self.bot)
        self.nodes: List[LavalinkNode] = [
            LavalinkNode(
                identifier=n["identifier"],
                rest_uri=n["rest_uri"],
                ws_uri=n["ws_uri"],
                password=n["password"],
                client_user_id=user_id
            )
            for n in LAVALINK_NODES
        ]
        self._active_node: Optional[LavalinkNode] = None
        self._init_task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls, bot=None):
        if cls._instance is None and bot is not None:
            cls._instance = cls(bot)
        return cls._instance

    async def initialize(self):
        user_id = _extract_bot_user_id(self.bot)
        # Cap nhat user_id cho tat ca node
        for node in self.nodes:
            node.client_user_id = user_id
        # Ket noi tat ca nodes song song
        tasks = [asyncio.create_task(self._safe_connect_node(node)) for node in self.nodes]
        # Doi toi da 10 giay de it nhat 1 node co WS session
        for _ in range(50):
            if self._active_node and self._active_node.is_connected and self._active_node.session_id:
                break
            await asyncio.sleep(0.2)

    async def _safe_connect_node(self, node: LavalinkNode):
        connected = await node.connect()
        if connected and (not self._active_node or not self._active_node.is_connected or not self._active_node.session_id):
            self._active_node = node
            _safe_log(f"[LAVALINK] Active Node Chinh: {node.identifier} (Session: {node.session_id})")

    def ensure_connecting(self):
        """Kích hoạt kết nối nền nếu chưa chạy."""
        if not self._init_task or self._init_task.done():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    self._init_task = loop.create_task(self.initialize())
            except Exception:
                pass

    def get_node(self) -> Optional[LavalinkNode]:
        if self._active_node and self._active_node.is_connected and self._active_node.session_id:
            return self._active_node
        # Failover sang node tiep theo dang san sang
        for n in self.nodes:
            if n.is_connected and n.session_id:
                if self._active_node != n:
                    _safe_log(f"[LAVALINK FAILOVER] Chuyen sang node: {n.identifier} (Session: {n.session_id})")
                self._active_node = n
                return n
        # Neu chua co node nao san sang, kich hoat connect ngay
        self.ensure_connecting()
        # Tra ve node dau tien lam fallback REST
        return self.nodes[0] if self.nodes else None

    async def close(self):
        for n in self.nodes:
            try:
                await n.close()
            except Exception:
                pass
        self._active_node = None

    async def get_player(self, guild_id: int) -> Optional[dict]:
        """Trang thai player tren node dang hoat dong (de kiem tra state.connected)."""
        node = self.get_node() or (self.nodes[0] if self.nodes else None)
        if not node:
            return None
        return await node.get_player(guild_id)

    async def node_dave_support(self) -> Optional[bool]:
        """Node Lavalink co ho tro DAVE (E2EE) native hay khong.

        True  -> >= 4.2.0: node tu ma hoa DAVE (chi can gui channelId)
        False -> node cu: phai dung cau DAVE cuc bo (yt-dlp + davey)
        None  -> build SNAPSHOT/dev nen khong doc duoc version
        """
        node = self.get_node() or (self.nodes[0] if self.nodes else None)
        if not node:
            return None
        info = await node.get_info()
        if not info:
            return None
        semver = str((info.get("version") or {}).get("semver") or "")
        m = re.match(r"(\d+)\.(\d+)\.(\d+)", semver)
        if not m:
            return None
        return tuple(int(x) for x in m.groups()) >= DAVE_MIN_LAVALINK

    async def search(self, query: str, limit: int = 20, source: str = "ytsearch") -> List[Dict[str, Any]]:
        is_url = query.startswith("http://") or query.startswith("https://")
        identifier = query if is_url else f"{source}:{query}"

        # Thử node active trước
        primary_node = self.get_node()
        nodes_to_try = [primary_node] if primary_node else []
        for n in self.nodes:
            if n not in nodes_to_try:
                nodes_to_try.append(n)

        for n in nodes_to_try:
            try:
                raw = await n.search(identifier)
                if raw:
                    return self._format_results(raw[:limit])
            except Exception:
                continue

        return []

    def _format_results(self, raw_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for it in raw_list:
            info = it.get("info", {})
            length_ms = info.get("length") or 0
            secs = int(length_ms / 1000)
            mins, s = divmod(secs, 60)
            dur_str = f"{mins:02d}:{s:02d}"
            v_id = info.get("identifier") or ""
            thumb = info.get("artworkUrl") or f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"
            out.append({
                "title": info.get("title", "Unknown Title"),
                "author": info.get("author", "Unknown Artist"),
                "duration": dur_str,
                "thumb_url": thumb,
                "encoded": it.get("encoded", ""),
                "uri": info.get("uri", ""),
                "id": v_id
            })
        return out


class LavalinkPlayer(discord.VoiceProtocol):
    """
    VoiceProtocol chuẩn cho Lavalink V4 SSL (tương đương wavelink.Player).
    Chỉ chuyển giao voice credentials (session_id, token, endpoint) cho Lavalink.
    Toàn bộ kết nối âm thanh và stream do Node Lavalink đảm nhiệm 100%,
    triệt tiêu hoàn toàn xung đột Voice WebSocket cục bộ (lỗi 4006).
    """

    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        self.guild = channel.guild
        self.lavalink_node: Optional[LavalinkNode] = None
        self.current_track: Optional[dict] = None
        self._lavalink_ready: bool = False
        self._voice_state_data: dict = {}
        self._voice_server_data: dict = {}
        self._connected: bool = False

    def is_connected(self) -> bool:
        return self._connected

    def is_playing(self) -> bool:
        return bool(self.current_track and self._lavalink_ready)

    async def on_voice_state_update(self, data: dict) -> None:
        self._voice_state_data = data
        channel_id = data.get("channel_id")
        if not channel_id:
            self._connected = False
            self.current_track = None
            self._lavalink_ready = False
            return
        self._connected = True
        await self._forward_voice_data()

    async def on_voice_server_update(self, data: dict) -> None:
        self._voice_server_data = data
        await self._forward_voice_data()

    async def _forward_voice_data(self) -> bool:
        token = self._voice_server_data.get("token")
        endpoint = self._voice_server_data.get("endpoint")
        session_id = self._voice_state_data.get("session_id")
        if not (token and endpoint and session_id):
            return False

        # Chuẩn payload theo đặc tả Lavalink V4 API: token, endpoint, sessionId, channelId
        channel_id = self._voice_state_data.get("channel_id") or (self.channel.id if self.channel else None)
        voice_payload = {
            "token": token,
            "endpoint": endpoint,
            "sessionId": session_id,
        }
        if channel_id:
            voice_payload["channelId"] = str(channel_id)

        if not self.lavalink_node:
            mgr = LavalinkManager.get_instance(self.client)
            if mgr:
                self.lavalink_node = mgr.get_node()

        if self.lavalink_node:
            # Đồng bộ user_id chính xác của bot account hiện tại
            if self.client and getattr(self.client, "user", None):
                self.lavalink_node.client_user_id = str(self.client.user.id)

            guild_id = self.channel.guild.id
            success = await self.lavalink_node.update_player(guild_id, {"voice": voice_payload})
            if success:
                self._lavalink_ready = True
                _safe_log(f"[LavalinkPlayer 🟢] Voice credentials forwarded to {self.lavalink_node.identifier} OK (guild={guild_id})")
                return True
            else:
                # Thử lại với clean endpoint nếu endpoint có port bị từ chối
                if ":" in endpoint:
                    voice_payload["endpoint"] = endpoint.split(":")[0]
                    success = await self.lavalink_node.update_player(guild_id, {"voice": voice_payload})
                    if success:
                        self._lavalink_ready = True
                        _safe_log(f"[LavalinkPlayer 🟢] Voice credentials (clean endpoint) forwarded to {self.lavalink_node.identifier} OK")
                        return True
                _safe_log(f"[LavalinkPlayer ⚠️] Lavalink tu choi voice credentials!")
        return False

    async def connect(
        self,
        *,
        reconnect: bool = True,
        timeout: float = 20.0,
        self_deaf: bool = True,
        self_mute: bool = False,
        self_video: bool = False,
    ) -> None:
        # 1. Khởi tạo & chọn Lavalink Node sẵn sàng
        mgr = LavalinkManager.get_instance(self.client)
        if not mgr:
            mgr = LavalinkManager(self.client)
            LavalinkManager._instance = mgr
        mgr.ensure_connecting()

        for _ in range(30):
            self.lavalink_node = mgr.get_node()
            if self.lavalink_node and self.lavalink_node.session_id:
                break
            await asyncio.sleep(0.2)

        if not self.lavalink_node and mgr.nodes:
            self.lavalink_node = mgr.nodes[0]

        # 2. Gửi Gateway Op 4 (Voice State Update) để yêu cầu vào phòng Voice
        await self.channel.guild.change_voice_state(
            channel=self.channel, self_mute=self_mute, self_deaf=self_deaf
        )

        # 3. Đợi Gateway phản hồi và Lavalink nhận voice session
        loop = asyncio.get_event_loop()
        deadline = loop.time() + max(timeout, 3.0)
        while loop.time() < deadline:
            if self._lavalink_ready:
                self._connected = True
                _safe_log(f"[LavalinkPlayer 🟢] Connected to {self.channel.name} via Lavalink V4")
                return
            await asyncio.sleep(0.2)

        if self._connected:
            return
        raise asyncio.TimeoutError("Timeout kết nối vào kênh Voice qua Lavalink")

    async def play_track(self, track_info: dict, volume: int = 100) -> bool:
        if not self.lavalink_node:
            mgr = LavalinkManager.get_instance(self.client)
            if mgr:
                self.lavalink_node = mgr.get_node()
        if not self.lavalink_node:
            return False

        if not self._lavalink_ready:
            await self._forward_voice_data()

        encoded = track_info.get("encoded")
        if not encoded:
            # Nếu chưa có encoded, thử resolve qua Lavalink
            uri = track_info.get("uri") or track_info.get("url") or track_info.get("title")
            if uri:
                resolved = await self.lavalink_node.search(uri)
                if resolved:
                    encoded = resolved[0].get("encoded")
                    track_info["encoded"] = encoded

        if not encoded:
            logger.warning("[LavalinkPlayer] Track khong co 'encoded' field!")
            return False

        guild_id = self.channel.guild.id
        ok = await self.lavalink_node.update_player(
            guild_id, {"track": {"encoded": encoded}, "volume": volume}
        )
        if not ok:
            ok = await self.lavalink_node.update_player(
                guild_id, {"encodedTrack": encoded, "volume": volume}
            )
        if ok:
            self.current_track = track_info
        return ok

    async def play(self, source, volume: int = 100, *, after=None) -> bool:
        """Alias tương thích để gọi vc.play(track_info)"""
        if isinstance(source, dict):
            return await self.play_track(source, volume)
        return False

    async def stop_track(self) -> bool:
        if self.lavalink_node and self._lavalink_ready:
            guild_id = self.channel.guild.id
            ok = await self.lavalink_node.update_player(
                guild_id, {"track": {"encoded": None}}
            )
            if not ok:
                ok = await self.lavalink_node.update_player(
                    guild_id, {"encodedTrack": None}
                )
            self.current_track = None
            return ok
        return False

    def stop(self):
        """Alias cho vc.stop()"""
        if self.lavalink_node:
            asyncio.create_task(self.stop_track())

    async def set_volume(self, volume: int) -> bool:
        if self.lavalink_node and self._lavalink_ready:
            return await self.lavalink_node.update_player(
                self.channel.guild.id, {"volume": volume}
            )
        return False

    async def move_to(self, channel: discord.abc.Connectable, *, timeout: Optional[float] = 30.0) -> None:
        self.channel = channel
        self.guild = channel.guild
        await self.channel.guild.change_voice_state(channel=channel)

    async def disconnect(self, *, force: bool = False) -> None:
        self.current_track = None
        self._lavalink_ready = False
        self._connected = False

        if self.lavalink_node:
            try:
                await self.lavalink_node.destroy_player(self.channel.guild.id)
            except Exception:
                pass

        try:
            await self.channel.guild.change_voice_state(channel=None)
        except Exception:
            pass


# =========================================================================
# VOICE GIA LAP: bot tu vao voice that, con Lavalink day Opus ve
# Fake Discord Voice Gateway (apps/user_discord/utils/fake_voice_gateway.py).
# Endpoint gui cho Lavalink bi thay bang ten mien DuckDNS cua ta.
# =========================================================================
def get_voice_connection_state(vc):
    """Tra ve VoiceConnectionState cua discord.py-self (chua token/endpoint/session_id)."""
    for attr in ("_connection", "connection"):
        conn = getattr(vc, attr, None)
        if conn is not None and hasattr(conn, "token"):
            return conn
    return None


async def wait_voice_credentials(vc, timeout: float = 20.0):
    """Doi Discord ban giao token + session_id cho bot user sau khi vao voice."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + max(timeout, 3.0)
    while loop.time() < deadline:
        conn = get_voice_connection_state(vc)
        if conn is not None:
            token = getattr(conn, "token", None)
            session_id = getattr(conn, "session_id", None)
            if token and session_id:
                return token, session_id
        await asyncio.sleep(0.2)
    return None, None


async def forward_voice_to_lavalink(
    bot,
    guild_id: int,
    token: str,
    session_id: str,
    channel_id: int,
    *,
    encoded: Optional[str] = None,
    volume: int = 100,
) -> bool:
    """
    Gui thong tin voice cho Lavalink nhung THAY endpoint bang Fake Voice Gateway.
    Neu co `encoded`, phat luon track sau khi da set voice.
    """
    from apps.shared.voice_gateway_config import ENDPOINT as VOICE_GATEWAY_ENDPOINT

    mgr = LavalinkManager.get_instance(bot)
    if not mgr:
        mgr = LavalinkManager(bot)
        LavalinkManager._instance = mgr
    mgr.ensure_connecting()

    node = None
    for _ in range(40):
        node = mgr.get_node()
        if node and node.session_id:
            break
        await asyncio.sleep(0.25)

    if not node or not node.session_id:
        _safe_log("[FakeVoice] ❌ Khong co Lavalink node nao san sang")
        return False

    if bot and getattr(bot, "user", None):
        node.client_user_id = str(bot.user.id)

    voice_payload = {
        "token": token,
        "endpoint": VOICE_GATEWAY_ENDPOINT,   # <-- endpoint gia (DuckDNS:port)
        "sessionId": session_id,
        "channelId": str(channel_id),
    }
    ok = await node.update_player(guild_id, {"voice": voice_payload})
    _safe_log(
        f"[FakeVoice] Da gui voice -> Lavalink (endpoint={VOICE_GATEWAY_ENDPOINT}): {ok}"
    )
    if not ok:
        return False

    if encoded:
        ok2 = await node.update_player(
            guild_id, {"track": {"encoded": encoded}, "volume": volume}
        )
        if not ok2:
            ok2 = await node.update_player(
                guild_id, {"encodedTrack": encoded, "volume": volume}
            )
        return ok2
    return True


async def stop_fake_voice_playback(bot, guild_id: int) -> None:
    """Dung track va huy player tren Lavalink cho guild nay."""
    mgr = LavalinkManager.get_instance(bot)
    if not mgr:
        return
    node = mgr.get_node()
    if not node:
        return
    try:
        await node.update_player(guild_id, {"track": {"encoded": None}})
    except Exception:
        pass
    try:
        await node.destroy_player(guild_id)
    except Exception:
        pass


async def setup(bot):
    pass

