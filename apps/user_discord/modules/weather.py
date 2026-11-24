# -*- coding: utf-8 -*-
"""
MODULE: weather (Tra cứu Thời Tiết Toàn Cầu Realtime)
- Lệnh chính: (prefix)thoitiet, (prefix)weather, (prefix)wt
- Cú pháp:
  • (prefix)thoitiet : Xem bảng hướng dẫn tra cứu thời tiết Liquid Glass.
  • (prefix)thoitiet <địa điểm> : Tra cứu thời tiết trực tiếp mọi tỉnh thành/quốc gia.
  • (prefix)weather <location> : Tra cứu thời tiết bằng tiếng Anh.
  • (prefix)wt <địa điểm> : Lệnh tắt tra cứu nhanh.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands
import requests

try:
    from apps.user_discord.core.bot_sys import require_permission
    from apps.user_discord.core.alias import alias_declare
    from apps.user_discord.utils.prefix import fmt, get_prefix
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.utils.media_card import async_help_card
    from apps.user_discord.utils.autorep import autorep
    from apps.user_discord.utils.autodelet import autodelet
    from apps.user_discord.utils import glass as G
except ImportError:
    from core.bot_sys import require_permission
    from core.alias import alias_declare
    from utils.prefix import fmt, get_prefix
    from utils.menu_catalog import menu_entry
    from utils.media_card import async_help_card
    from utils.autorep import autorep
    from utils.autodelet import autodelet
    try:
        from utils import glass as G
    except ImportError:
        G = None

WMO_WEATHER_MAP = {
    0: ("Trời quang đãng, Nắng đẹp", "NẮNG ĐẸP", "☀️", (245, 158, 11), ((245, 158, 11), (251, 191, 36))),
    1: ("Trời ít mây, Nắng dịu", "ÍT MÂY", "🌤️", (251, 191, 36), ((251, 191, 36), (148, 163, 184))),
    2: ("Trời có mây rải rác", "CÓ MÂY", "⛅", (148, 163, 184), ((148, 163, 184), (203, 213, 225))),
    3: ("Trời âm u, Nhiều mây", "ÂM U", "☁️", (100, 116, 139), ((100, 116, 139), (71, 85, 105))),
    45: ("Sương mù bao phủ", "SƯƠNG MÙ", "🌫️", (148, 163, 184), ((148, 163, 184), (100, 116, 139))),
    48: ("Sương muối bám đọng", "SƯƠNG MUỐI", "❄️", (203, 213, 225), ((203, 213, 225), (148, 163, 184))),
    51: ("Mưa phùn hạt nhỏ", "MƯA PHÙN", "🌦️", (56, 189, 248), ((56, 189, 248), (14, 165, 233))),
    53: ("Mưa phùn vừa", "MƯA PHÙN", "🌦️", (14, 165, 233), ((14, 165, 233), (2, 132, 199))),
    55: ("Mưa phùn hạt nặng", "MƯA PHÙN", "🌧️", (2, 132, 199), ((2, 132, 199), (3, 105, 161))),
    61: ("Mưa rào nhẹ", "MƯA NHẸ", "🌧️", (56, 189, 248), ((56, 189, 248), (59, 130, 246))),
    63: ("Mưa rào vừa", "MƯA VỪA", "🌧️", (59, 130, 246), ((59, 130, 246), (37, 99, 235))),
    65: ("Mưa to diện rộng", "MƯA TO", "🌧️", (37, 99, 235), ((37, 99, 235), (29, 78, 216))),
    71: ("Tuyết rơi nhẹ", "TUYẾT RƠI", "🌨️", (224, 242, 254), ((224, 242, 254), (186, 230, 253))),
    73: ("Tuyết rơi vừa", "TUYẾT RƠI", "❄️", (186, 230, 253), ((186, 230, 253), (125, 211, 252))),
    75: ("Tuyết rơi dày đặc", "BÃO TUYẾT", "❄️", (125, 211, 252), ((125, 211, 252), (56, 189, 248))),
    80: ("Mưa rào thoáng qua", "MƯA RÀO", "🌦️", (56, 189, 248), ((56, 189, 248), (37, 99, 235))),
    81: ("Mưa rào vừa", "MƯA RÀO", "🌧️", (59, 130, 246), ((59, 130, 246), (37, 99, 235))),
    82: ("Mưa rào xối xả", "MƯA LỚN", "⛈️", (37, 99, 235), ((37, 99, 235), (147, 51, 234))),
    95: ("Dông sét, Mưa rào mạnh", "DÔNG SÉT", "⛈️", (239, 68, 68), ((239, 68, 68), (168, 85, 247))),
    96: ("Dông bão kèm mưa đá", "MƯA ĐÁ", "⛈️", (239, 68, 68), ((239, 68, 68), (220, 38, 38))),
    99: ("Bão sấm sét dữ dội", "BÃO DÔNG", "⚡", (220, 38, 38), ((220, 38, 38), (153, 27, 27))),
}


class WeatherModule(commands.Cog, name="Weather"):
    """Module tra cứu thông tin thời tiết toàn cầu dạng Liquid Glass siêu đẹp."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "."

    # ── API GEOCODING & WEATHER FORECAST ────────────────────────────────────
    def _fetch_weather_data(self, query: str) -> Optional[Dict[str, Any]]:
        """Lấy dữ liệu tọa độ & thời tiết realtime từ Open-Meteo."""
        try:
            # 1. Geocoding
            q_enc = urllib.parse.quote(query.strip())
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={q_enc}&count=1&language=vi&format=json"
            res = self.session.get(geo_url, timeout=6)
            if res.status_code != 200:
                return None
            geo_data = res.json()
            results = geo_data.get("results")
            if not results:
                # Thử tìm lại bằng query tiếng Anh/không dấu nếu có
                geo_url_en = f"https://geocoding-api.open-meteo.com/v1/search?name={q_enc}&count=1&language=en&format=json"
                res_en = self.session.get(geo_url_en, timeout=6)
                if res_en.status_code == 200:
                    results = res_en.json().get("results")

            if not results:
                return None

            loc = results[0]
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            name = loc.get("name")
            country = loc.get("country", "")
            admin1 = loc.get("admin1", "")

            loc_display = name
            if admin1 and admin1 != name:
                loc_display += f", {admin1}"
            if country:
                loc_display += f", {country}"

            # 2. Weather Forecast API
            w_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,surface_pressure,wind_speed_10m"
                f"&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max"
                f"&timezone=auto"
            )
            w_res = self.session.get(w_url, timeout=6)
            if w_res.status_code != 200:
                return None
            w_data = w_res.json()

            current = w_data.get("current", {})
            daily = w_data.get("daily", {})

            # Format sunrise / sunset
            sunrises = daily.get("sunrise", [])
            sunsets = daily.get("sunset", [])
            sr_str = sunrises[0].split("T")[-1] if sunrises else "--:--"
            ss_str = sunsets[0].split("T")[-1] if sunsets else "--:--"

            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            uv_list = daily.get("uv_index_max", [])

            max_t = max_temps[0] if max_temps else current.get("temperature_2m", 0)
            min_t = min_temps[0] if min_temps else current.get("temperature_2m", 0)
            uv = uv_list[0] if uv_list else 0.0

            w_code = current.get("weather_code", 0)
            w_info = WMO_WEATHER_MAP.get(w_code, ("Thời tiết bình thường", "BÌNH THƯỜNG", "⛅", (148, 163, 184), ((148, 163, 184), (203, 213, 225))))

            return {
                "location": loc_display,
                "lat": lat,
                "lon": lon,
                "timezone": w_data.get("timezone", "Auto"),
                "time": current.get("time", ""),
                "temp": current.get("temperature_2m", 0.0),
                "feels_like": current.get("apparent_temperature", 0.0),
                "humidity": current.get("relative_humidity_2m", 0),
                "wind_speed": current.get("wind_speed_10m", 0.0),
                "pressure": current.get("surface_pressure", 1013.0),
                "precip": current.get("precipitation", 0.0),
                "weather_code": w_code,
                "desc": w_info[0],
                "badge": w_info[1],
                "icon": w_info[2],
                "color": w_info[3],
                "gradient": w_info[4],
                "max_temp": max_t,
                "min_temp": min_t,
                "uv": uv,
                "sunrise": sr_str,
                "sunset": ss_str,
            }
        except Exception:
            return None

    # ── RENDER LIQUID GLASS WEATHER CARD ────────────────────────────────────
    def _render_weather_card(self, d: Dict[str, Any]) -> io.BytesIO:
        if G is None:
            raise RuntimeError("Thư viện Liquid Glass không khả dụng.")

        LW, LH = 980, 520
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)
        pfx = self._pfx()

        lat_dir = "N" if d["lat"] >= 0 else "S"
        lon_dir = "E" if d["lon"] >= 0 else "W"
        coord_str = f"{abs(d['lat']):.2f}°{lat_dir}, {abs(d['lon']):.2f}°{lon_dir}"

        cv.header(
            pad, pad, LW - pad, head_h,
            f"THỜI TIẾT - {d['location'].upper()}",
            f"Tọa độ: {coord_str}   •   Khu vực: {d['timezone']}   •   Prefix {pfx}",
            tag="WEATHER RADAR",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, "LIVE RADAR", cv.font("b", 12), G.G_GREEN, h=24, align="r")

        top = pad + head_h + gap
        box1_h = 150
        cv.glass((pad, top, LW - pad, top + box1_h), 18, blur=24, tint=(14, 22, 36, 100))
        cv.grad((pad + 4, top + 14, pad + 8, top + box1_h - 14), 2, d["color"],
                tuple(max(0, int(v * 0.5)) for v in d["color"]))

        # Left Info
        cv.text(pad + 24, top + 36, d["desc"], cv.font("b", 22), G.C_TEXT, vcenter=True)
        cv.text(
            pad + 24, top + 68,
            f"Cảm giác như: {d['feels_like']:.1f}°C   •   Lượng mưa: {d['precip']} mm   •   Áp suất: {d['pressure']:.0f} hPa",
            cv.font("r", 13), G.C_MUTED, vcenter=True
        )
        pill_txt = f"{d['icon']} {d['badge']}"
        cv.pill(pad + 24, top + 104, pill_txt, cv.font("b", 12), d["gradient"], h=26, padx=14)

        # Right Main Temp
        temp_str = f"{d['temp']:.1f}°C"
        cv.text(LW - pad - 28, top + 52, temp_str, cv.font("b", 42), G.C_GOLD, align="r", vcenter=True)
        cv.text(
            LW - pad - 28, top + 102,
            f"Thấp nhất: {d['min_temp']:.1f}°C  |  Cao nhất: {d['max_temp']:.1f}°C",
            cv.font("r", 13), G.C_DIM, align="r", vcenter=True
        )

        # 4 Stat Capsules
        top2 = top + box1_h + gap
        bottom = LH - pad - 34

        # UV Rating
        uv_val = d["uv"]
        uv_str = f"{uv_val:.1f}"
        if uv_val < 3:
            uv_tag = f"{uv_str} (Thấp)"
            uv_col = (16, 185, 129)
        elif uv_val < 6:
            uv_tag = f"{uv_str} (Trung bình)"
            uv_col = (251, 191, 36)
        elif uv_val < 8:
            uv_tag = f"{uv_str} (Cao)"
            uv_col = (245, 158, 11)
        else:
            uv_tag = f"{uv_str} (Rất cao)"
            uv_col = (239, 68, 68)

        capsules = [
            ("Độ Ẩm Không Khí", f"{d['humidity']}%", (16, 185, 129)),
            ("Tốc Độ Gió", f"{d['wind_speed']:.1f} km/h", (56, 189, 248)),
            ("Chỉ Số Tia UV", uv_tag, uv_col),
            ("Mặt Trời Mọc / Lặn", f"{d['sunrise']} / {d['sunset']}", G.C_TEXT),
        ]
        cap_w = (LW - 2 * pad - 3 * gap) / 4

        for i, (lbl, val, col) in enumerate(capsules):
            cx1 = pad + i * (cap_w + gap)
            cx2 = cx1 + cap_w
            cv.glass((cx1, top2, cx2, bottom), 14, blur=16, tint=(16, 22, 38, 85))
            cv.text((cx1 + cx2) / 2, top2 + 24, lbl, cv.font("r", 12), G.C_MUTED, align="c", vcenter=True)
            cv.text((cx1 + cx2) / 2, top2 + 56, cv.fit(val, cv.font("b", 16), cap_w - 20), cv.font("b", 16), col, align="c", vcenter=True)

        # Footer
        cv.text(
            pad + 10, LH - pad - 12,
            "Dữ liệu khí tượng Open-Meteo High-Resolution Model   •   Tra cứu tự động không cần API Key",
            cv.font("r", 11), G.C_DIM, vcenter=True
        )

        return cv.finalize()

    # ── LỆNH CHÍNH (PREFIX)THOITIET / WEATHER / WT ─────────────────────────
    @menu_entry("AI & TIỆN ÍCH", "thoitiet", "Tra cuu thoi tiet toan cau Realtime",
                badge="LIVE", icon_sym="⛅", icon_color=(14, 165, 233), order=4)
    @alias_declare("thoitiet", ["weather", "wt"])
    @commands.group(
        name="thoitiet",
        aliases=["weather", "wt"],
        invoke_without_command=True,
        help="Tra cuu thoi tiet realtime tai bat ky tinh thanh, quoc gia nao."
    )
    async def cmd_weather(self, ctx: commands.Context, *, location: Optional[str] = None):
        """Lệnh tra cứu thời tiết: (prefix)thoitiet <địa điểm>"""
        pfx = self._pfx()

        if not location:
            # Xuất Help Card Liquid Glass
            card_buf = await async_help_card("thoitiet", pfx)
            if card_buf:
                card_file = discord.File(card_buf, filename="thoitiet_guide.png")
                await autorep(
                    ctx.message,
                    content="⛅ **HƯỚNG DẪN TRA CỨU THỜI TIẾT TOÀN CẦU**",
                    file=card_file,
                    auto_delete_delay=60
                )
            else:
                msg = await autorep(
                    ctx.message,
                    f"⛅ **HƯỚNG DẪN TRA CỨU THỜI TIẾT**\n"
                    f"👉 Cú pháp: `{pfx}thoitiet <địa điểm>` (Ví dụ: `{pfx}thoitiet Hà Nội`, `{pfx}weather Tokyo`, `{pfx}wt Sài Gòn`)\n"
                    f"👉 Dữ liệu cập nhật realtime: Nhiệt độ, độ ẩm, tốc độ gió, chỉ số UV, bình minh & hoàng hôn."
                )
                autodelet(msg, delay=30)
            return

        waiting = await autorep(ctx.message, f"⏳ Đang định vị và lấy dữ liệu thời tiết tại **{location}**...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, self._fetch_weather_data, location)

        if not data:
            msg = await autorep(
                ctx.message,
                f"❌ Không tìm thấy thông tin địa điểm hoặc không thể lấy dữ liệu thời tiết cho: **{location}**.\n"
                f"💡 Hãy thử nhập tên thành phố rõ ràng hơn (VD: `Hà Nội`, `Hồ Chí Minh`, `Đà Nẵng`, `Tokyo`, `Paris`)."
            )
            autodelet(msg, delay=20)
            return

        # Render Liquid Glass Weather Card
        try:
            buf = await loop.run_in_executor(None, self._render_weather_card, data)
            file = discord.File(buf, filename=f"weather_{urllib.parse.quote(location)[:15]}.png")
            caption = (
                f"⛅ **THỜI TIẾT HIỆN TẠI TẠI {data['location'].upper()}**\n"
                f"🌡️ Nhiệt độ: **{data['temp']:.1f}°C** (Cảm giác: **{data['feels_like']:.1f}°C**)   |   {data['icon']} **{data['desc']}**\n"
                f"💧 Độ ẩm: **{data['humidity']}%**   |   💨 Gió: **{data['wind_speed']:.1f} km/h**   |   ☀️ UV: **{data['uv']:.1f}**"
            )
            sent = await autorep(ctx.message, content=caption, file=file, auto_delete_delay=60)
            autodelet(sent, delay=60)
        except Exception as e:
            # Fallback text nếu lỗi render
            msg = await autorep(
                ctx.message,
                f"⛅ **THỜI TIẾT {data['location']}**\n"
                f"• Nhiệt độ: **{data['temp']}°C** (Cảm giác: {data['feels_like']}°C)\n"
                f"• Tình trạng: **{data['desc']}** {data['icon']}\n"
                f"• Độ ẩm: **{data['humidity']}%** | Gió: **{data['wind_speed']} km/h**\n"
                f"• Dao động ngày: **{data['min_temp']}°C - {data['max_temp']}°C**"
            )
            autodelet(msg, delay=60)


async def setup(bot: commands.Bot):
    await bot.add_cog(WeatherModule(bot))
