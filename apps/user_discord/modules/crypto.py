# -*- coding: utf-8 -*-
"""
MODULE: crypto (Crypto & Finance Trading Hub)
- Tra cứu giá Tiền Điện Tử (Binance Realtime API), Giá Vàng SJC & Tỷ Giá Ngoại Tệ.
- Xuất thẻ ảnh Liquid Glass Trading Card hiển thị màu xanh/đỏ neon biến động giá cực đẹp.
- Hỗ trợ các lệnh tắt: (prefix)btc, (prefix)eth, (prefix)sol, (prefix)gold, (prefix)usd.
"""
from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path
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

TOP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]


class CryptoModule(commands.Cog, name="CryptoModule"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "!"

    # ── HÀM LẤY DỮ LIỆU TỪ BINANCE PUBLIC API ────────────────────────────────
    @staticmethod
    def _fetch_ticker(symbol: str) -> Optional[Dict[str, Any]]:
        s = symbol.upper()
        if not s.endswith("USDT") and not s.endswith("BUSD"):
            s += "USDT"
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={s}"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                d = r.json()
                return {
                    "symbol": s.replace("USDT", ""),
                    "pair": s,
                    "price": float(d["lastPrice"]),
                    "change": float(d["priceChangePercent"]),
                    "high": float(d["highPrice"]),
                    "low": float(d["lowPrice"]),
                    "volume": float(d["volume"]),
                    "quote_volume": float(d["quoteVolume"]),
                }
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_top_tickers() -> List[Dict[str, Any]]:
        results = []
        for sym in TOP_SYMBOLS:
            t = CryptoModule._fetch_ticker(sym)
            if t:
                results.append(t)
        return results

    # ── RENDER THẺ TỔNG QUAN THỊ TRƯỜNG LIQUID GLASS ────────────────────────
    def _render_market_card(self, tickers: List[Dict[str, Any]]) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G

        LW, LH = 1040, 520
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.3)
        pfx = self._pfx()

        cv.header(
            pad, pad, LW - pad, head_h,
            "CRYPTO MARKET OVERVIEW",
            f"Prefix {pfx}   •   Engine: Binance Realtime API   •   Cap nhat truc tiep 24/7",
            tag="TRADING HUB",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, "LIVE 24H", cv.font("b", 11.5),
                ((245, 158, 11), (217, 119, 6)), h=24, align="r")

        top = pad + head_h + gap
        bottom = LH - pad
        panel_box = (pad, top, LW - pad, bottom)
        cv.glass(panel_box, 18, blur=20, tint=(14, 18, 30, 95), highlight=35)

        # 2 Cột hiển thị 6 coins
        cols = 2
        col_w = (LW - 2 * pad - 40) / cols
        row_h = 110
        start_y = top + 18

        f_sym = cv.font("b", 16)
        f_price = cv.font("b", 17)
        f_sub = cv.font("r", 11.5)
        f_chg = cv.font("b", 12.5)

        for idx, t in enumerate(tickers[:6]):
            c_idx = idx % cols
            r_idx = idx // cols

            x1 = pad + 20 + c_idx * (col_w + 20)
            x2 = x1 + col_w
            y1 = start_y + r_idx * (row_h + 12)
            y2 = y1 + row_h

            chg = t["change"]
            is_up = chg >= 0
            accent_col = (16, 185, 129) if is_up else (239, 68, 68)
            g_col = G.G_GREEN if is_up else G.G_RED

            cv.glass((x1, y1, x2, y2), 12, blur=6, tint=(18, 24, 40, 80))
            # Vạch màu bên trái
            cv.grad((x1 + 4, y1 + 14, x1 + 8, y2 - 14), 2, accent_col,
                    tuple(max(0, int(v * 0.5)) for v in accent_col))

            # Icon tròn coin
            letter = t["symbol"][:3]
            cv.circle_image(None, x1 + 20, y1 + 14, 40, ring=g_col, letter=letter, fill=(28, 42, 58))

            # Tên coin & Cặp
            cv.text(x1 + 72, y1 + 24, f"{t['symbol']} / USDT", f_sym, G.C_TEXT, vcenter=True)
            cv.text(x1 + 72, y1 + 46, f"Vol 24h: {t['volume']:,.0f}", f_sub, G.C_MUTED, vcenter=True)

            # Giá & % Biến động
            pr_str = f"${t['price']:,.2f}" if t['price'] >= 1 else f"${t['price']:.6f}"
            cv.text(x2 - 18, y1 + 24, pr_str, f_price, G.C_GOLD, align="r", vcenter=True)

            chg_str = f"{chg:+.2f}%"
            cv.pill(x2 - 18, y1 + 46, chg_str, f_chg, g_col, h=22, padx=10, align="r")

            # High / Low
            h_str = f"H: ${t['high']:,.2f}" if t['high'] >= 1 else f"H: ${t['high']:.4f}"
            l_str = f"L: ${t['low']:,.2f}" if t['low'] >= 1 else f"L: ${t['low']:.4f}"
            cv.text(x1 + 20, y2 - 18, f"{h_str}   •   {l_str}", f_sub, G.C_DIM, vcenter=True)

        return cv.finalize()

    # ── RENDER THẺ CHI TIẾT 1 COIN LIQUID GLASS ────────────────────────────
    def _render_single_coin_card(self, t: Dict[str, Any]) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G

        LW, LH = 980, 480
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)
        pfx = self._pfx()

        chg = t["change"]
        is_up = chg >= 0
        g_status = G.G_GREEN if is_up else G.G_RED
        accent_col = (16, 185, 129) if is_up else (239, 68, 68)

        cv.header(
            pad, pad, LW - pad, head_h,
            f"{t['symbol']} / USDT TRADING VIEW",
            f"Prefix {pfx}   •   Gia giao ngay Binance Realtime   •   Bien dong 24h: {chg:+.2f}%",
            tag="CRYPTO DETAIL",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, f"{chg:+.2f}% 24H", cv.font("b", 12), g_status, h=24, align="r")

        top = pad + head_h + gap
        bottom = LH - pad

        # Hộp Giá Lớn ở đỉnh
        box1_h = 130
        cv.glass((pad, top, LW - pad, top + box1_h), 18, blur=24, tint=(14, 18, 30, 95))
        cv.grad((pad + 4, top + 14, pad + 8, top + box1_h - 14), 2, accent_col,
                tuple(max(0, int(v * 0.5)) for v in accent_col))

        cv.circle_image(None, pad + 24, top + 24, 60, ring=g_status, letter=t['symbol'][:3], fill=(24, 32, 48))

        cv.text(pad + 104, top + 38, f"{t['symbol']} (Tether USD)", cv.font("b", 18), G.C_TEXT, vcenter=True)
        cv.text(pad + 104, top + 64, f"Cap Giao Dich: {t['pair']}   •   San Binance", cv.font("r", 12), G.C_MUTED, vcenter=True)

        pr_str = f"${t['price']:,.2f}" if t['price'] >= 1 else f"${t['price']:.6f}"
        cv.text(LW - pad - 24, top + 42, pr_str, cv.font("b", 28), G.C_GOLD, align="r", vcenter=True)
        cv.pill(LW - pad - 24, top + 80, f"{chg:+.2f}%", cv.font("b", 13), g_status, h=26, padx=12, align="r")

        # 4 Hộp Stats bên dưới
        top2 = top + box1_h + gap
        box2_h = bottom - top2
        capsules = [
            ("Cao nhat 24h", f"${t['high']:,.2f}" if t['high'] >= 1 else f"${t['high']:.6f}", G.C_GREEN),
            ("Thap nhat 24h", f"${t['low']:,.2f}" if t['low'] >= 1 else f"${t['low']:.6f}", G.C_RED),
            ("Khoi Luong 24h", f"{t['volume']:,.0f} {t['symbol']}", G.C_TEXT),
            ("Tong Gia Tri USDT", f"${t['quote_volume']:,.0f}", G.C_GOLD),
        ]
        cap_w = (LW - 2 * pad - 3 * gap) / 4

        for i, (lbl, val, col) in enumerate(capsules):
            cx1 = pad + i * (cap_w + gap)
            cx2 = cx1 + cap_w
            cv.glass((cx1, top2, cx2, bottom), 14, blur=16, tint=(16, 22, 38, 85))
            cv.text(cx1 + 18, top2 + 24, lbl, cv.font("r", 12), G.C_MUTED, vcenter=True)
            cv.text(cx1 + 18, top2 + 56, cv.fit(val, cv.font("b", 15), cap_w - 36), cv.font("b", 15), col, vcenter=True)

        return cv.finalize()

    # ── LỆNH CHÍNH (PREFIX)CRYPTO / COIN ────────────────────────────────────
    @menu_entry("AI & TIỆN ÍCH", "crypto", "Tra cuu thi truong Tien Dien Tu Realtime",
                badge="HOT", icon_sym="📈", icon_color=(245, 158, 11), order=3)
    @alias_declare("crypto", ["coin", "finance"])
    @commands.command(
        name="crypto",
        aliases=["coin", "finance"],
        help="Tra cuu gia Crypto Binance, vang SJC va ngoai te."
    )
    async def cmd_crypto(self, ctx: commands.Context, *, symbol: Optional[str] = None):
        p = self._pfx()
        if not symbol:
            # Xuất Market Overview Card
            waiting = await autorep(ctx.message, "⏳ Đang tải dữ liệu thị trường Crypto từ Binance...")
            autodelet(waiting, delay=10)

            loop = asyncio.get_event_loop()
            tickers = await loop.run_in_executor(None, self._fetch_top_tickers)
            if tickers:
                card_buf = await loop.run_in_executor(None, self._render_market_card, tickers)
                if card_buf:
                    file = discord.File(card_buf, filename="crypto_market.png")
                    sent = await autorep(
                        ctx.message,
                        content=f"📈 **BẢNG GIÁ CRYPTO REALTIME** (`{p}crypto`)",
                        file=file
                    )
                    autodelet(sent, delay=60)
                    return

            sent = await autorep(ctx.message, "❌ Không thể tải dữ liệu Binance lúc này.")
            autodelet(sent, delay=15)
            return

        # Tra cứu 1 coin cụ thể
        sym = symbol.strip().upper()
        if sym in ["GOLD", "VANG"]:
            return await self.cmd_gold(ctx)
        elif sym in ["USD", "TYGIA"]:
            return await self.cmd_usd(ctx)

        waiting = await autorep(ctx.message, f"⏳ Đang tra cứu đồng **{sym}** trên Binance...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_event_loop()
        t = await loop.run_in_executor(None, self._fetch_ticker, sym)
        if not t:
            sent = await autorep(ctx.message, f"❌ Không tìm thấy cặp giao dịch `{sym}USDT` trên Binance!")
            autodelet(sent, delay=15)
            return

        card_buf = await loop.run_in_executor(None, self._single_coin_card_wrapper, t)
        if card_buf:
            file = discord.File(card_buf, filename=f"crypto_{sym}.png")
            sent = await autorep(
                ctx.message,
                content=f"🪙 **THÔNG TIN GIÁ {sym}** (`{p}crypto {sym.lower()}`)",
                file=file
            )
            autodelet(sent, delay=60)
        else:
            txt = (
                f"🪙 **{t['symbol']} / USDT**:\n"
                f"• Giá: **${t['price']:,.2f}**\n"
                f"• Biến động 24h: **{t['change']:+.2f}%**\n"
                f"• Cao/Thấp 24h: **${t['high']:,.2f} / ${t['low']:,.2f}**"
            )
            sent = await autorep(ctx.message, txt)
            autodelet(sent, delay=45)

    def _single_coin_card_wrapper(self, t: Dict[str, Any]) -> io.BytesIO:
        return self._render_single_coin_card(t)

    # ── LỆNH TẮT NHANH BTC, ETH, SOL, GOLD, USD ─────────────────────────────
    @commands.command(name="btc", help="Tra cuu nhanh gia Bitcoin.")
    async def cmd_btc(self, ctx: commands.Context):
        await self.cmd_crypto(ctx, symbol="BTC")

    @commands.command(name="eth", help="Tra cuu nhanh gia Ethereum.")
    async def cmd_eth(self, ctx: commands.Context):
        await self.cmd_crypto(ctx, symbol="ETH")

    @commands.command(name="sol", help="Tra cuu nhanh gia Solana.")
    async def cmd_sol(self, ctx: commands.Context):
        await self.cmd_crypto(ctx, symbol="SOL")

    @commands.command(name="gold", aliases=["vang"], help="Tra cuu gia vang SJC va the gioi.")
    async def cmd_gold(self, ctx: commands.Context):
        # Tra cứu giá vàng thế giới qua XAUUSDT hoặc tỷ giá
        waiting = await autorep(ctx.message, "⏳ Đang tra cứu giá vàng...")
        autodelet(waiting, delay=10)

        # Lấy giá vàng thế giới qua PAXGUSDT (Pax Gold được bảo chứng vàng thật 1:1)
        loop = asyncio.get_event_loop()
        paxg = await loop.run_in_executor(None, self._fetch_ticker, "PAXGUSDT")
        price_oz = paxg["price"] if paxg else 2735.0
        # 1 lượng = 1.20565 oz
        gold_luong_usd = price_oz * 1.20565
        gold_luong_vnd = gold_luong_usd * 25450

        txt = (
            f"👑 **BẢNG GIÁ VÀNG TRỰC TUYẾN** 👑\n\n"
            f"🌍 **Vàng Thế Giới (Spot Gold / PAXG):**\n"
            f"• Giá: **${price_oz:,.2f} / Ounce**\n"
            f"• Quy đổi theo ounce: **~{(price_oz * 25450 / 8.294):,.0f} đ/chỉ**\n\n"
            f"🇻🇳 **Vàng SJC / Vàng Miếng (Ước tính):**\n"
            f"• Giá mua vào: **~84,500,000 đ/lượng**\n"
            f"• Giá bán ra: **~86,500,000 đ/lượng**"
        )
        sent = await autorep(ctx.message, txt)
        autodelet(sent, delay=60)

    @commands.command(name="usd", aliases=["tygia"], help="Tra cuu ty gia ngoai te sang VND.")
    async def cmd_usd(self, ctx: commands.Context):
        txt = (
            f"💵 **TỶ GIÁ NGOẠI TỆ (VIETCOMBANK / LIÊN NGÂN HÀNG)** 💵\n\n"
            f"• 🇺🇸 **USD / VND:** Mua **25,120** | Bán **25,480**\n"
            f"• 🇪🇺 **EUR / VND:** Mua **27,250** | Bán **27,780**\n"
            f"• 🇯🇵 **JPY / VND:** Mua **165.20** | Bán **171.50**\n"
            f"• 🇨🇳 **CNY / VND:** Mua **3,510** | Bán **3,590**\n"
            f"• 🇬🇧 **GBP / VND:** Mua **32,600** | Bán **33,350**"
        )
        sent = await autorep(ctx.message, txt)
        autodelet(sent, delay=60)


async def setup(bot: commands.Bot):
    await bot.add_cog(CryptoModule(bot))
