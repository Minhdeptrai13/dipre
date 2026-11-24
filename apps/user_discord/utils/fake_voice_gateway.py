"""
Fake Discord Voice Gateway
==========================
Gia lap may chu voice cua Discord de "lua" Lavalink ket noi vao va day cac
khung Opus tho (Lavalink da giai ma tu YouTube) ve cho bot.

  Lavalink --wss--> Quart(:20276, SSL) --proxy--> FakeVoiceGateway(:20277 noi bo)
  Lavalink --udp--> :20276 --> giai ma xsalsa20_poly1305 --> hang doi Opus
  OpusGatewaySource.read() --> discord.py-self VoiceClient --> voice that Discord

Diem manh: KHONG giai ma va KHONG ma hoa lai Opus => gan nhu 0% CPU.
DAVE/E2EE bi vo hieu hoa mot cach tu nhien: ta KHONG quang ba
`dave_protocol_version` trong goi op2 Ready, nen Lavalink chi dung
ma hoa transport (xsalsa20_poly1305) - thu ta giai ma duoc bang PyNaCl.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import secrets
import threading
import time
from typing import Dict, List, Optional

import aiohttp
from aiohttp import web
import discord

try:
    import nacl.secret  # type: ignore
    _HAS_NACL = True
except Exception:  # pragma: no cover - PyNaCl luon co trong requirements
    _HAS_NACL = False

from apps.shared.voice_gateway_config import (
    HEARTBEAT_INTERVAL,
    LOCAL_WS_HOST,
    LOCAL_WS_PORT,
    PUBLIC_PORT,
    TRANSPORT_MODES,
    UDP_ADVERTISE_HOST,
    summary as _cfg_summary,
)

# ── Voice gateway opcodes (theo discord/discord-api-docs) ───────────────────
OP_IDENTIFY = 0
OP_SELECT_PROTOCOL = 1
OP_READY = 2
OP_HEARTBEAT = 3
OP_SESSION_DESCRIPTION = 4
OP_SPEAKING = 5
OP_HEARTBEAT_ACK = 6
OP_HELLO = 8


def _safe_log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(str(msg).encode("ascii", "ignore").decode("ascii"), flush=True)
        except Exception:
            pass


class FakeVoiceSession:
    """Mot phien voice gia cho 1 guild (bot <-> Lavalink)."""

    __slots__ = ("guild_id", "ssrc", "secret_key", "mode", "ws", "created",
                 "secretbox", "_frame_count")

    def __init__(self, guild_id: int, ssrc: int, secret_key: bytes, mode: str, ws):
        self.guild_id = guild_id
        self.ssrc = ssrc
        self.secret_key = secret_key
        self.mode = mode
        self.ws = ws
        self.created = time.time()
        self._frame_count = 0
        self.secretbox = nacl.secret.SecretBox(secret_key) if _HAS_NACL else None

    def decrypt(self, body: bytes, nonce: bytes) -> Optional[bytes]:
        if not self.secretbox:
            return None
        try:
            return self.secretbox.decrypt(body, nonce)
        except Exception:
            return None


class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, gateway: "FakeVoiceGateway"):
        self.gateway = gateway

    def datagram_received(self, data: bytes, addr) -> None:
        self.gateway.handle_udp(data, addr)

    def error_received(self, exc) -> None:  # pragma: no cover
        _safe_log(f"[VOICE-GW UDP] error: {exc}")


class FakeVoiceGateway:
    """
    Singleton chua toan bo logic server voice gia lap.
    start() phai duoc goi trong event loop cua bot (user_discord).
    """

    _instance: Optional["FakeVoiceGateway"] = None

    def __init__(self) -> None:
        self._sessions: Dict[int, FakeVoiceSession] = {}     # guild_id -> session
        self._by_ssrc: Dict[int, FakeVoiceSession] = {}      # ssrc -> session
        self._listeners: Dict[int, List[queue.Queue]] = {}   # guild_id -> [queue]
        self._udp_transport: Optional[asyncio.DatagramTransport] = None
        self._runner: Optional[web.AppRunner] = None
        self._started = False
        self._lock = asyncio.Lock()

    # ── vong doi ────────────────────────────────────────────────────────────
    @classmethod
    def instance(cls) -> "FakeVoiceGateway":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self) -> None:
        """Khoi dong WS noi bo + UDP hung Opus. An toan khi goi nhieu lan."""
        async with self._lock:
            if self._started:
                return
            self._started = True

        # 1) WebSocket server noi bo (Quart se proxy ra ngoai qua :PUBLIC_PORT)
        try:
            app = web.Application()
            app.router.add_get("/", self._handle_ws)
            app.router.add_get("/voice", self._handle_ws)
            self._runner = web.AppRunner(app)
            await self._runner.setup()
            site = web.TCPSite(self._runner, LOCAL_WS_HOST, LOCAL_WS_PORT)
            await site.start()
            _safe_log(f"[VOICE-GW] ✅ WS noi bo: ws://{LOCAL_WS_HOST}:{LOCAL_WS_PORT}/")
        except Exception as e:
            _safe_log(f"[VOICE-GW] ❌ Khong mo duoc WS noi bo: {e}")

        # 2) UDP server hung Opus tren cong cong khai
        try:
            loop = asyncio.get_event_loop()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(self),
                local_addr=("0.0.0.0", PUBLIC_PORT),
            )
            self._udp_transport = transport
            _safe_log(f"[VOICE-GW] ✅ UDP dang nghe tren 0.0.0.0:{PUBLIC_PORT}")
        except Exception as e:
            _safe_log(f"[VOICE-GW] ❌ Khong bind duoc UDP {PUBLIC_PORT}: {e}")

        _safe_log(f"[VOICE-GW] 🚀 San sang | {_cfg_summary()}")

    async def stop(self) -> None:
        if self._udp_transport:
            try:
                self._udp_transport.close()
            except Exception:
                pass
            self._udp_transport = None
        if self._runner:
            try:
                await self._runner.cleanup()
            except Exception:
                pass
            self._runner = None
        self._started = False

    # ── dang ky nguon Opus (phia bot) ───────────────────────────────────────
    def bind_source(self, guild_id: int, q: "queue.Queue") -> None:
        self._listeners.setdefault(int(guild_id), []).append(q)
        _safe_log(f"[VOICE-GW] 🎧 Bot dang cho Opus cua guild {guild_id}")

    def unbind_source(self, guild_id: int, q: "queue.Queue") -> None:
        lst = self._listeners.get(int(guild_id))
        if not lst:
            return
        try:
            lst.remove(q)
        except ValueError:
            pass
        if not lst:
            self._listeners.pop(int(guild_id), None)

    def _push_opus(self, guild_id: int, frame: bytes) -> None:
        for q in list(self._listeners.get(int(guild_id), [])):
            try:
                q.put_nowait(frame)
            except queue.Full:
                try:
                    q.get_nowait()  # bo khung cu de giam do tre
                    q.put_nowait(frame)
                except Exception:
                    pass

    def _finish_guild(self, guild_id: int) -> None:
        for q in list(self._listeners.get(int(guild_id), [])):
            try:
                q.put_nowait(None)
            except Exception:
                pass

    def has_session(self, guild_id: int) -> bool:
        return int(guild_id) in self._sessions


    # ── UDP: IP discovery + giai ma Opus ────────────────────────────────────
    def handle_udp(self, data: bytes, addr) -> None:
        if len(data) < 12:
            return

        # IP Discovery request: type == 0x0001, len == 70, tong 74 byte
        if len(data) >= 74 and data[0:2] == b"\x00\x01":
            ssrc = int.from_bytes(data[4:8], "big")
            resp = bytearray(74)
            resp[0:2] = b"\x00\x02"
            resp[2:4] = (70).to_bytes(2, "big")
            resp[4:8] = ssrc.to_bytes(4, "big")
            host = str(addr[0]).encode("ascii", "ignore")[:63]
            resp[8:8 + len(host)] = host
            resp[72:74] = int(addr[1]).to_bytes(2, "big")
            transport = self._udp_transport
            if transport is not None:
                try:
                    transport.sendto(bytes(resp), addr)
                except Exception:
                    pass
            return

        # Media packet: RTP header (co the kem one-byte extension) + payload
        ssrc = int.from_bytes(data[8:12], "big")
        session = self._by_ssrc.get(ssrc)
        if session is None:
            return

        if data[0] & 0x10:  # extension bit
            if len(data) < 16:
                return
            ext_len = int.from_bytes(data[14:16], "big") * 4
            header_len = 16 + ext_len
        else:
            header_len = 12
        body = data[header_len:]
        if len(body) <= 16:  # chi co tag Poly1305, khong co du lieu
            return

        # xsalsa20_poly1305: nonce = 12 byte dau header + 12 byte 0
        nonce = bytes(data[0:12]) + b"\x00" * 12
        opus = session.decrypt(bytes(body), nonce)
        if not opus:
            return
        session._frame_count += 1
        if session._frame_count == 1:
            _safe_log(
                f"[VOICE-GW] 🎵 Khung Opus dau tien cho guild {session.guild_id} "
                f"({len(opus)} bytes)"
            )
        self._push_opus(session.guild_id, opus)

    # ── quan ly session ─────────────────────────────────────────────────────
    def _register_session(self, session: FakeVoiceSession) -> None:
        self._sessions[session.guild_id] = session
        self._by_ssrc[session.ssrc] = session

    def _drop_session(self, session: FakeVoiceSession) -> None:
        if self._sessions.get(session.guild_id) is session:
            self._sessions.pop(session.guild_id, None)
        if self._by_ssrc.get(session.ssrc) is session:
            self._by_ssrc.pop(session.ssrc, None)
        self._finish_guild(session.guild_id)
        _safe_log(
            f"[VOICE-GW] 🔌 Dong session guild {session.guild_id} "
            f"sau {session._frame_count} khung Opus"
        )


    # ── WebSocket: bat tay gia lap Discord voice gateway ────────────────────
    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(autoping=False, max_msg_size=0, heartbeat=None)
        await ws.prepare(request)
        _safe_log(
            f"[VOICE-GW] 🔌 Lavalink ket noi WS tu {request.remote} (path={request.path})"
        )

        session: Optional[FakeVoiceSession] = None
        try:
            session = await self._handshake(ws)
            if session is None:
                try:
                    await ws.close(code=4000, message=b"handshake-failed")
                except Exception:
                    pass
                return ws
            await self._pump(ws, session)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _safe_log(f"[VOICE-GW] ⚠️ WS loi: {e}")
        finally:
            if session is not None:
                self._drop_session(session)
            try:
                await ws.close()
            except Exception:
                pass
        return ws

    async def _handshake(self, ws: web.WebSocketResponse) -> Optional[FakeVoiceSession]:
        await ws.send_str(json.dumps({
            "op": OP_HELLO,
            "d": {"heartbeat_interval": int(HEARTBEAT_INTERVAL * 1000)},
        }))

        ssrc = secrets.randbelow(2 ** 31) + 1
        secret_key = os.urandom(32)
        guild_id: Optional[int] = None

        while True:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=20.0)
            except asyncio.TimeoutError:
                _safe_log("[VOICE-GW] ⏳ Het han cho Identify/SelectProtocol")
                return None

            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    continue
                op = payload.get("op")
                d = payload.get("d") or {}

                if op == OP_IDENTIFY and "server_id" in d:
                    guild_id = int(d.get("server_id") or 0) or None
                    _safe_log(
                        f"[VOICE-GW] 📨 Identify guild={guild_id} "
                        f"user={d.get('user_id')} session={d.get('session_id')}"
                    )
                    await ws.send_str(json.dumps({
                        "op": OP_READY,
                        "d": {
                            "ssrc": ssrc,
                            "ip": UDP_ADVERTISE_HOST,
                            "port": PUBLIC_PORT,
                            "modes": list(TRANSPORT_MODES),
                            "heartbeat_interval": int(HEARTBEAT_INTERVAL * 1000),
                            "experiments": [],
                            # Co y KHONG gui "dave_protocol_version" => tat E2EE/DAVE
                        },
                    }))

                elif op == OP_SELECT_PROTOCOL:
                    data = d.get("data") or {}
                    mode = (data.get("mode") or TRANSPORT_MODES[0]).lower()
                    if mode not in TRANSPORT_MODES:
                        mode = TRANSPORT_MODES[0]
                    session = FakeVoiceSession(
                        guild_id=int(guild_id or 0), ssrc=ssrc,
                        secret_key=secret_key, mode=mode, ws=ws,
                    )
                    self._register_session(session)
                    await ws.send_str(json.dumps({
                        "op": OP_SESSION_DESCRIPTION,
                        "d": {"mode": mode, "secret_key": list(secret_key)},
                    }))
                    _safe_log(
                        f"[VOICE-GW] 🎧 Session san sang | guild={session.guild_id} "
                        f"ssrc={ssrc} mode={mode} => udp {UDP_ADVERTISE_HOST}:{PUBLIC_PORT}"
                    )
                    return session

                elif op == OP_HEARTBEAT:
                    await self._send_heartbeat_ack(ws, d)

            elif msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.ERROR,
            ):
                return None

    async def _pump(self, ws: web.WebSocketResponse, session: FakeVoiceSession) -> None:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    continue
                op = payload.get("op")
                if op == OP_HEARTBEAT:
                    await self._send_heartbeat_ack(ws, payload.get("d") or {})
                # OP_SPEAKING: khong can xu ly vi ta chi nhan audio
            elif msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.ERROR,
            ):
                break

    @staticmethod
    async def _send_heartbeat_ack(ws: web.WebSocketResponse, d) -> None:
        try:
            await ws.send_str(json.dumps({"op": OP_HEARTBEAT_ACK, "d": d}))
        except Exception:
            pass


class OpusGatewaySource(discord.AudioSource):
    """
    Nguon am thanh Opus lay tu FakeVoiceGateway.

    discord.py-self AudioPlayer se goi read() trong 1 thread rieng moi 20ms va
    tu dong goi `send_audio_packet(..., encode=False)` => bot phat dung nguyen
    khung Opus, khong ton CPU ma hoa.
    """

    def __init__(
        self,
        gateway: FakeVoiceGateway,
        guild_id: int,
        *,
        first_frame_timeout: float = 60.0,
        gap_timeout: float = 30.0,
    ) -> None:
        self._gw = gateway
        self._guild_id = int(guild_id)
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=4000)
        self._first_timeout = first_frame_timeout
        self._gap_timeout = gap_timeout
        self._started = False
        self._closed = threading.Event()
        gateway.bind_source(self._guild_id, self._q)

    def is_opus(self) -> bool:
        return True

    def read(self) -> bytes:
        if self._closed.is_set() and self._q.empty():
            return b""
        timeout = self._gap_timeout if self._started else self._first_timeout
        try:
            frame = self._q.get(timeout=timeout)
        except queue.Empty:
            _safe_log("[VOICE-GW] ⏱️ Het Opus (timeout) -> ket thuc phat")
            return b""
        if frame is None:
            return b""
        self._started = True
        return frame

    def stop(self) -> None:
        self._closed.set()
        try:
            self._q.put_nowait(None)
        except Exception:
            pass

    def cleanup(self) -> None:
        self._closed.set()
        self._gw.unbind_source(self._guild_id, self._q)


def get_gateway() -> FakeVoiceGateway:
    """Tien loi: lay singleton gateway."""
    return FakeVoiceGateway.instance()


async def ensure_gateway_started() -> FakeVoiceGateway:
    """Tien loi: khoi dong gateway (idempotent) va tra ve singleton."""
    gw = FakeVoiceGateway.instance()
    await gw.start()
    return gw


async def setup(bot):
    """Extension loader hook cho main.py (utility thuan, khong phai cog)."""
    pass

