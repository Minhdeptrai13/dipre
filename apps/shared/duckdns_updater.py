"""
Tu dong cap nhat ban ghi A cua DuckDNS ve dung IP cong khai cua may host.

Tac dung: neu router nha (hoac bot DuckDNS nao khac) lo ghi IP nha vao domain,
tien trinh nay se tu dong tra no ve IP that cua panel (~5 phut/1 lan).
=> Khong can vao duckdns.org bam tay nua.

Bien moi truong:
    DUCKDNS_TOKEN      (tuy chon) token DuckDNS, mac dinh da hardcode
                          trong apps/shared/voice_gateway_config.py
    DUCKDNS_DOMAIN     (tuy chon)  mac dinh lay tu voice_gateway_config.DOMAIN
    DUCKDNS_INTERVAL   (tuy chon)  giay giua 2 lan cap nhat, mac dinh 300
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import aiohttp

from apps.shared.voice_gateway_config import DOMAIN as _DEFAULT_DOMAIN
from apps.shared.voice_gateway_config import DUCKDNS_TOKEN as _DEFAULT_TOKEN

DUCKDNS_UPDATE_URL = "https://www.duckdns.org/update"
IP_ECHO_URLS = (
    "https://api.ipify.org",
    "https://icanhazip.com",
    "https://ifconfig.me/ip",
)


def _log(msg: str) -> None:
    try:
        print(f"[DUCKDNS] {msg}", flush=True)
    except Exception:
        pass


def _subdomain(domain: str) -> str:
    """minhnvb.duckdns.org -> minhnvb"""
    return domain.strip().split(".")[0]


async def get_public_ip(session: aiohttp.ClientSession, timeout: float = 10.0) -> Optional[str]:
    """Lay IP cong khai cua container (chinh la IP cua may host)."""
    for url in IP_ECHO_URLS:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                if r.status == 200:
                    txt = (await r.text()).strip()
                    if txt and len(txt) <= 45 and " " not in txt:
                        return txt
        except Exception:
            continue
    return None


async def update_duckdns(
    session: aiohttp.ClientSession,
    subdomain: str,
    token: str,
    ip: Optional[str] = None,
    timeout: float = 15.0,
) -> bool:
    """
    Goi API DuckDNS. Neu `ip` None thi DuckDNS tu lay IP nguon goi.
    Tra ve True neu DuckDNS tra 'OK'.
    """
    params = {"domains": subdomain, "token": token}
    if ip:
        params["ip"] = ip
    try:
        async with session.get(
            DUCKDNS_UPDATE_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as r:
            body = (await r.text()).strip()
            return r.status == 200 and body.upper() == "OK"
    except Exception as e:
        _log(f"Goi DuckDNS loi: {e}")
        return False


async def update_duckdns_once(
    domain: Optional[str] = None, token: Optional[str] = None
) -> bool:
    """Cap nhat 1 lan (dung khi vua khoi dong)."""
    domain = (domain or os.getenv("DUCKDNS_DOMAIN") or _DEFAULT_DOMAIN).strip()
    token = (token or os.getenv("DUCKDNS_TOKEN") or _DEFAULT_TOKEN or "").strip()
    if not token:
        _log("Thieu DUCKDNS_TOKEN -> bo qua cap nhat IP")
        return False

    sub = _subdomain(domain)
    async with aiohttp.ClientSession() as session:
        ip = await get_public_ip(session)
        ok = await update_duckdns(session, sub, token, ip)
        _log(f"{sub}.duckdns.org -> {ip or '(tu dong)'} : {'OK' if ok else 'THAT BAI'}")
        return ok


async def duckdns_keepalive_loop(
    interval: Optional[float] = None,
    domain: Optional[str] = None,
    token: Optional[str] = None,
) -> None:
    """Vong lap nen: giu ban ghi A luon tro ve IP that cua panel."""
    token = (token or os.getenv("DUCKDNS_TOKEN") or _DEFAULT_TOKEN or "").strip()
    if not token:
        _log("Thieu DUCKDNS_TOKEN -> khong bat vong lap cap nhat IP")
        return

    domain = (domain or os.getenv("DUCKDNS_DOMAIN") or _DEFAULT_DOMAIN).strip()
    sub = _subdomain(domain)
    if interval is None:
        try:
            interval = float(os.getenv("DUCKDNS_INTERVAL") or 300)
        except Exception:
            interval = 300.0
    interval = max(60.0, interval)

    _log(f"Bat dau giu IP cho {sub}.duckdns.org (moi {int(interval)}s)")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                ip = await get_public_ip(session)
                ok = await update_duckdns(session, sub, token, ip)
                if not ok:
                    _log(f"Cap nhat that bai (ip={ip})")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log(f"Loi vong lap: {e}")
            await asyncio.sleep(interval)


async def setup(bot):
    """Extension loader hook (utility thuan, khong phai cog)."""
    pass
