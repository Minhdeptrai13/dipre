"""
Cau hinh chung cho "Fake Discord Voice Gateway".

Vi sao phai chia 2 tien trinh:
  - Pterodactyl chi mo DUY NHAT 1 allocation (20276) cho ca TCP lan UDP.
  - TCP 20276 dang bi web dashboard (Quart / apps/discord_bot/web/web.py) chiem.
  - Server voice gia lap can them 1 cong TCP cho WebSocket + 1 cong UDP hung Opus.

=> Gop chung:
     Internet --wss://minhnvb.duckdns.org:20276/?v=4-->  Quart (web.py, SSL)
                                                            |
                                                            +-- proxy noi bo -->  127.0.0.1:20277 (Fake Voice WS)
     Internet --udp://minhnvb.duckdns.org:20276------>  Fake Voice Gateway (tien trinh user_discord)

Moi gia tri deu co the ghi de bang bien moi truong (Pterodactyl Startup / .env).
"""

import os

# ── Ten mien cong khai tro ve may host (DuckDNS) ────────────────────────────
DOMAIN = os.getenv("VOICE_GATEWAY_DOMAIN", "minhnvb.duckdns.org").strip()

# IP cong khai cua may host. Neu trong, se dung DOMAIN cho goi Ready (op2).
# Java resolve hostname rat tot, nen de trong cung chay duoc.
PUBLIC_IP = os.getenv("VOICE_GATEWAY_PUBLIC_IP", "").strip()

# Cong allocation cua Pterodactyl: TCP dung chung dashboard + WSS, UDP hung Opus.
# Pterodactyl tu dat bien SERVER_PORT = cong allocation.
PUBLIC_PORT = int(
    os.getenv("VOICE_GATEWAY_PUBLIC_PORT") or os.getenv("SERVER_PORT") or "20276"
)

# Cong WS noi bo: chi nghe tren localhost, Quart (web.py) se proxy ra ngoai.
LOCAL_WS_HOST = os.getenv("VOICE_GATEWAY_LOCAL_WS_HOST", "127.0.0.1").strip()
LOCAL_WS_PORT = int(os.getenv("VOICE_GATEWAY_LOCAL_WS_PORT", "20277"))

# Endpoint "gai" cho Lavalink: host:port, KHONG kem scheme (Lavalink tu them wss://).
ENDPOINT = f"{DOMAIN}:{PUBLIC_PORT}"

# Dia chi UDP quang ba trong goi op2 Ready (Lavalink se gui Opus toi day).
UDP_ADVERTISE_HOST = PUBLIC_IP or DOMAIN

# Chu ky heartbeat cua voice gateway (giay).
HEARTBEAT_INTERVAL = 41.25

# Mode ma hoa ma ta quang ba. Chi dung xsalsa20_poly1305 de de giai ma bang PyNaCl.
TRANSPORT_MODES = ["xsalsa20_poly1305"]


# ── Token/Email DuckDNS (hardcode san, van co the ghi de bang env) ──────────
# DUCKDNS_TOKEN dung cho:
#   1) tu cap nhat ban ghi A (apps/shared/duckdns_updater.py)
#   2) ghi TXT _acme-challenge de xin SSL (apps/discord_bot/utils/acme_duckdns.py)
DUCKDNS_TOKEN = os.getenv("DUCKDNS_TOKEN", "b4f3d33f-9ad5-4fa2-80ee-0f4cc6f2780b").strip()

# Email dang ky Let's Encrypt (chi de nhan thong bao het han)
LETSENCRYPT_EMAIL = os.getenv("LETSENCRYPT_EMAIL", "binhminhnguvubinhminh@gmail.com").strip()


def summary() -> str:
    return (
        f"domain={DOMAIN} endpoint={ENDPOINT} "
        f"udp={UDP_ADVERTISE_HOST}:{PUBLIC_PORT} "
        f"local_ws={LOCAL_WS_HOST}:{LOCAL_WS_PORT}"
    )
