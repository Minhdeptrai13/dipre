import discord
from discord.ext import commands
import asyncio
import os
import io
import time
import random
import threading
import requests
import json
import base64
import re
from datetime import datetime, timezone
from typing import Union, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from apps.shared.paths import SHARED_FONTS_DIR, SHARED_BACKGROUNDS_DIR
from apps.user_discord.core.bot_sys import require_permission
from apps.user_discord.core.alias import alias_declare
from apps.user_discord.utils.menu_catalog import menu_entry

_DISCORD_BUILD_NUMBER = None
_DISCORD_BUILD_NUMBER_TIME = 0

def fetch_latest_build_number() -> int:
    global _DISCORD_BUILD_NUMBER, _DISCORD_BUILD_NUMBER_TIME
    FALLBACK = 504649
    now = time.time()
    if _DISCORD_BUILD_NUMBER and (now - _DISCORD_BUILD_NUMBER_TIME) < 86400:
        return _DISCORD_BUILD_NUMBER
    try:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        r = requests.get("https://discord.com/app", headers={"User-Agent": ua}, timeout=6)
        if r.status_code == 200:
            scripts = re.findall(r'/assets/([a-f0-9]+)\.js', r.text)
            if not scripts:
                scripts_alt = re.findall(r'src="(/assets/[^"]+\.js)"', r.text)
                scripts = [s.split('/')[-1].replace('.js', '') for s in scripts_alt]
            for asset_hash in scripts[-5:]:
                try:
                    ar = requests.get(f"https://discord.com/assets/{asset_hash}.js", headers={"User-Agent": ua}, timeout=6)
                    m = re.search(r'buildNumber["\s:]+["\s]*(\d{5,7})', ar.text)
                    if m:
                        _DISCORD_BUILD_NUMBER = int(m.group(1))
                        _DISCORD_BUILD_NUMBER_TIME = now
                        return _DISCORD_BUILD_NUMBER
                except Exception:
                    continue
    except Exception:
        pass
    return _DISCORD_BUILD_NUMBER or FALLBACK

def make_super_properties(build_number: int = None) -> str:
    if not build_number:
        build_number = fetch_latest_build_number()
    obj = {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": "1.0.9175",
        "os_version": "10.0.26100",
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) discord/1.0.9175 Chrome/128.0.6613.186 Electron/32.2.7 Safari/537.36",
        "browser_version": "32.2.7",
        "client_build_number": build_number,
        "native_build_number": 59498,
        "client_event_source": None
    }
    return base64.b64encode(json.dumps(obj).encode()).decode()

def make_discord_headers(token: str) -> dict:
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) discord/1.0.9175 Chrome/128.0.6613.186 Electron/32.2.7 Safari/537.36",
        "X-Super-Properties": make_super_properties(),
        "X-Discord-Locale": "en-US",
        "X-Discord-Timezone": "Asia/Ho_Chi_Minh",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me"
    }

SUPPORTED_QUEST_TASKS = [
    "WATCH_VIDEO",
    "PLAY_ON_DESKTOP",
    "STREAM_ON_DESKTOP",
    "PLAY_ACTIVITY",
    "WATCH_VIDEO_ON_MOBILE",
]

def _quest_get(d, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d:
            return d[k]
    return None

def get_task_config(quest: dict) -> dict:
    cfg = quest.get("config", {})
    return _quest_get(cfg, "taskConfig", "task_config", "taskConfigV2", "task_config_v2") or {}

def get_quest_name(quest: dict) -> str:
    cfg = quest.get("config", {})
    msgs = cfg.get("messages", {})
    qname = (_quest_get(msgs, "questName", "quest_name") or "").strip()
    game = (_quest_get(msgs, "gameTitle", "game_title") or "").strip()
    app_name = (cfg.get("application", {}).get("name") or "").strip()

    if qname and qname.lower() != "discord":
        return qname
    if game and game.lower() != "discord":
        return game
    if app_name and app_name.lower() != "discord":
        return app_name
    return qname or game or app_name or f"Quest #{quest.get('id', '?')}"

def parse_discord_quest_item(q: dict) -> Optional[dict]:
    qid = str(q.get("id", ""))
    cfg = q.get("config", {})

    # 1. Kiểm tra hết hạn: nếu quest đã hết hạn (expires_at < now), bỏ qua quest ảo/hết hạn
    exp_str = cfg.get("expires_at")
    if exp_str:
        try:
            exp_dt = datetime.fromisoformat(exp_str)
            if exp_dt < datetime.now(timezone.utc):
                return None
        except Exception:
            pass

    tc = get_task_config(q)
    tasks = tc.get("tasks", {})
    task_type = "UNSUPPORTED"
    for t in SUPPORTED_QUEST_TASKS:
        if tasks.get(t) is not None:
            task_type = t
            break

    # Nếu không thuộc loại task hỗ trợ -> bỏ qua
    if task_type == "UNSUPPORTED":
        return None

    name = get_quest_name(q)
    target_seconds = tc.get("tasks", {}).get(task_type, {}).get("target", 0)
    us = _quest_get(q, "userStatus", "user_status") or {}
    prog = us.get("progress", {}) if isinstance(us, dict) else {}
    seconds_done = float(prog.get(task_type, {}).get("value", 0)) if isinstance(prog, dict) and task_type in prog else 0.0

    enrolled = bool(_quest_get(us, "enrolledAt", "enrolled_at"))
    completed = bool(_quest_get(us, "completedAt", "completed_at"))
    claimed = bool(_quest_get(us, "claimedAt", "claimed_at"))
    pct = min(100, int((seconds_done / target_seconds) * 100)) if target_seconds > 0 else (100 if completed else 0)

    # Reward name
    rewards_config = cfg.get("rewards_config", {}) or cfg.get("rewardsConfig", {})
    rewards_list = rewards_config.get("rewards", [])
    reward_name = "Phần Thưởng Discord"
    if rewards_list and isinstance(rewards_list[0], dict):
        r_item = rewards_list[0]
        r_msgs = r_item.get("messages", {})
        reward_name = r_msgs.get("name") or r_item.get("name") or r_item.get("description") or reward_name

    return {
        "id": qid,
        "name": name,
        "task_type": task_type,
        "target_seconds": int(target_seconds),
        "seconds_done": float(seconds_done),
        "progress_pct": pct,
        "enrolled": enrolled,
        "completed": completed,
        "claimed": claimed,
        "reward": reward_name,
        "expires_at": exp_str or "",
    }


class AutoQuestRunner:
    def __init__(self):
        self.is_auto_enabled = False
        self.status = "idle"
        self.current_quest_id = None
        self.current_quest_name = None
        self.task_type = "PLAY_ON_DESKTOP"
        self.progress_pct = 0
        self.target_seconds = 60
        self.elapsed_seconds = 0
        self.reward = ""
        self.loop_thread = None
        self.stop_flag = threading.Event()
        self.lock = threading.Lock()

    def get_status(self) -> dict:
        with self.lock:
            return {
                "is_auto": self.is_auto_enabled,
                "status": self.status,
                "quest_id": self.current_quest_id,
                "quest_name": self.current_quest_name,
                "task_type": self.task_type,
                "progress_pct": self.progress_pct,
                "elapsed_seconds": self.elapsed_seconds,
                "target_seconds": self.target_seconds,
                "reward": self.reward,
            }

    def start_auto(self, token: str):
        """Bật chế độ Auto Cày Quest liên tục."""
        self.stop()
        with self.lock:
            self.is_auto_enabled = True
            self.stop_flag.clear()
            self.status = "running"
            self.loop_thread = threading.Thread(target=self._auto_loop_worker, args=(token,), daemon=True)
            self.loop_thread.start()

    def stop(self):
        """Dừng hoàn toàn tiến trình auto cày."""
        with self.lock:
            self.is_auto_enabled = False
            self.stop_flag.set()
            if self.status == "running":
                self.status = "stopped"

    def enroll(self, token: str, quest_id: str) -> bool:
        headers = make_discord_headers(token)
        payload = {"location": 11, "is_targeted": False, "metadata_raw": None, "metadata_sealed": None}
        try:
            r = requests.post(f"https://discord.com/api/v9/quests/{quest_id}/enroll", headers=headers, json=payload, timeout=8)
            return r.status_code in (200, 201, 204)
        except Exception:
            return False

    def _fetch_quests(self, token: str) -> list:
        headers = make_discord_headers(token)
        try:
            r = requests.get("https://discord.com/api/v9/quests/@me", headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                raw = data.get("quests", []) if isinstance(data, dict) else data
                items = [parse_discord_quest_item(q) for q in raw]
                return [q for q in items if q is not None]
        except Exception:
            pass
        return []

    def _auto_loop_worker(self, token: str):
        """Worker chạy liên tục tự động cày tất cả quest còn dang dở."""
        while not self.stop_flag.is_set():
            quests = self._fetch_quests(token)
            uncompleted = [q for q in quests if not q["completed"] and q["task_type"] != "UNSUPPORTED"]

            if not uncompleted:
                with self.lock:
                    self.status = "idle"
                    self.current_quest_name = None
                    self.current_quest_id = None
                    self.progress_pct = 0
                # Nghỉ 5 phút kiểm tra lại nếu hết quest
                for _ in range(300):
                    if self.stop_flag.is_set():
                        return
                    time.sleep(1)
                continue

            for q in uncompleted:
                if self.stop_flag.is_set():
                    return

                with self.lock:
                    self.status = "running"
                    self.current_quest_id = q["id"]
                    self.current_quest_name = q["name"]
                    self.task_type = q["task_type"]
                    self.target_seconds = max(10, q["target_seconds"])
                    self.elapsed_seconds = int(q["seconds_done"])
                    self.progress_pct = q["progress_pct"]
                    self.reward = q.get("reward", "")

                self._process_single_quest(token, q)

                # Nghỉ 3 giây giữa các quest
                for _ in range(3):
                    if self.stop_flag.is_set():
                        return
                    time.sleep(1)

            # Nghỉ 60 giây sau khi duyệt xong một đợt
            for _ in range(60):
                if self.stop_flag.is_set():
                    return
                time.sleep(1)

    def _process_single_quest(self, token: str, q: dict):
        qid = q["id"]
        task_type = q["task_type"]
        target_seconds = max(10, q["target_seconds"])
        seconds_done = float(q["seconds_done"])
        headers = make_discord_headers(token)

        # Đảm bảo enroll trước khi cày
        self.enroll(token, qid)

        is_video = task_type in ("WATCH_VIDEO", "WATCH_VIDEO_ON_MOBILE")
        pid = random.randint(1000, 30000)
        stream_key = f"call:0:{pid}" if task_type != "PLAY_ACTIVITY" else "call:0:1"

        while not self.stop_flag.is_set() and seconds_done < target_seconds:
            if is_video:
                seconds_done = min(target_seconds, seconds_done + 7)
                try:
                    r = requests.post(f"https://discord.com/api/v9/quests/{qid}/video-progress", headers=headers, json={"timestamp": seconds_done}, timeout=6)
                    if r.status_code == 200 and r.json().get("completed_at"):
                        seconds_done = target_seconds
                except Exception:
                    pass
                time.sleep(1)
            else:
                seconds_done = min(target_seconds, seconds_done + 15)
                try:
                    r = requests.post(f"https://discord.com/api/v9/quests/{qid}/heartbeat", headers=headers, json={"stream_key": stream_key, "terminal": False}, timeout=8)
                    if r.status_code == 200:
                        body = r.json()
                        prog = body.get("progress", {})
                        if isinstance(prog, dict) and task_type in prog:
                            seconds_done = prog[task_type].get("value", seconds_done)
                        if body.get("completed_at"):
                            seconds_done = target_seconds
                except Exception:
                    pass
                for _ in range(15):
                    if self.stop_flag.is_set():
                        break
                    time.sleep(1)

            with self.lock:
                self.elapsed_seconds = int(seconds_done)
                self.progress_pct = min(100, int((seconds_done / target_seconds) * 100))

        # Hoàn tất
        try:
            if is_video:
                requests.post(f"https://discord.com/api/v9/quests/{qid}/video-progress", headers=headers, json={"timestamp": target_seconds}, timeout=5)
            else:
                requests.post(f"https://discord.com/api/v9/quests/{qid}/heartbeat", headers=headers, json={"stream_key": stream_key, "terminal": True}, timeout=6)
        except Exception:
            pass


class AutoQuestModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.runner = AutoQuestRunner()

    def get_token(self) -> str:
        return getattr(self.bot, "http", {}).token or ""

    def get_prefix(self) -> str:
        try:
            from apps.user_discord.utils.prefix import get_prefix
        except ImportError:
            from utils.prefix import get_prefix
        return get_prefix(self.bot)

    async def reply_text(self, message: discord.Message, text: str, delay: int = 30):
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            from utils.autorep import autorep
        return await autorep(message, content=text, auto_delete_delay=delay)

    def _is_high_admin(self, user_id: int) -> bool:
        """CAP "Admin cap cao" (admintris) - cap cao nhat trong 3 cap quyen.

        He thong chi co 3 cap:
            1. Admin cap cao (`admintris`) - gom ca chu tai khoan cua bot
            2. Admin (`admins`)
            3. Nguoi thuong (tat ca con lai)
        Lenh `quest` dung token cua bot -> chi cap 1 duoc phep.
        Uu tien ham `bot.is_mod` / `bot.check_permission` do bot_sys gan san.
        """
        checker = getattr(self.bot, "is_mod", None)
        if callable(checker):
            try:
                return bool(checker(user_id))
            except Exception:
                pass
        check = getattr(self.bot, "check_permission", None)
        if callable(check):
            try:
                allowed, _ = check(user_id, None, "mod")
                return bool(allowed)
            except Exception:
                return False
        return False

    async def _deny_high_admin(self, ctx) -> None:
        pfx = self.get_prefix()
        await self.reply_text(
            ctx.message,
            f"⛔ **TỪ CHỐI — CẦN QUYỀN ADMIN CẤP CAO**\n"
            f"• Lệnh `{pfx}quest` chỉ dành cho Admin cấp cao (`admintris`).\n"
            f"• Người gọi: {ctx.author} (`{ctx.author.id}`)\n"
            f"• Liên hệ Admin cấp cao để được thêm vào `admintris`.",
            delay=45,
        )

    async def render_quest_menu_gui(self, invoker: discord.User, st: dict, quests_count: int, uncompleted_count: int) -> discord.File:
        """Render giao diện Dashboard Liquid Glass cho Quest Menu."""
        w, h = 480, 800
        pfx = self.get_prefix()

        # 1. Background ngẫu nhiên với hiệu ứng Bokeh mờ nhanh siêu tốc
        valid_exts = ('.png', '.jpg', '.jpeg', '.jpe', '.webp', '.gif')
        bg_files = []
        if SHARED_BACKGROUNDS_DIR.exists():
            bg_files = [f for f in os.listdir(SHARED_BACKGROUNDS_DIR) if f.lower().endswith(valid_exts)]

        if bg_files:
            try:
                chosen_bg = SHARED_BACKGROUNDS_DIR / random.choice(bg_files)
                with Image.open(chosen_bg) as raw_bg:
                    if getattr(raw_bg, "is_animated", False):
                        raw_bg.seek(0)
                    base_img = raw_bg.convert("RGBA")
                base_img = ImageOps.fit(base_img, (w, h), method=Image.Resampling.BILINEAR)
                # Tối ưu siêu tốc độ: Thu nhỏ -> Blur(2) -> Phóng to (Bokeh mượt tức thì < 5ms)
                small_w, small_h = max(w // 6, 40), max(h // 6, 40)
                small_bg = base_img.resize((small_w, small_h), Image.Resampling.BILINEAR)
                small_bg = small_bg.filter(ImageFilter.GaussianBlur(radius=2))
                base_img = small_bg.resize((w, h), Image.Resampling.BICUBIC)
                dim_layer = Image.new("RGBA", (w, h), (10, 12, 16, 55))
                base_img = Image.alpha_composite(base_img, dim_layer)
            except Exception:
                base_img = Image.new("RGBA", (w, h), (16, 18, 24, 255))
        else:
            base_img = Image.new("RGBA", (w, h), (16, 18, 24, 255))

        # 2. Main Glass Card (Pha lê trong suốt siêu nét, không tối đục nhựa)
        card_x1, card_y1, card_x2, card_y2 = 20, 16, w - 20, h - 16
        cw, ch = card_x2 - card_x1, card_y2 - card_y1
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([(card_x1, card_y1 + 4), (card_x2, card_y2 + 4)], radius=24, fill=(0, 0, 0, 80))
        base_img = Image.alpha_composite(base_img, shadow)

        glass_card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gc_draw = ImageDraw.Draw(glass_card)
        gc_draw.rounded_rectangle([(card_x1, card_y1), (card_x2, card_y2)], radius=26, fill=(16, 20, 32, 60), outline=(255, 255, 255, 75), width=1)
        # Specular highlight
        g_raw = Image.linear_gradient("L").resize((cw, ch), Image.Resampling.BILINEAR)
        a_sheen = g_raw.point(lambda v: int(55 * ((255 - v) / 255.0) ** 2.2))
        hl = Image.new("RGBA", (cw, ch), (255, 255, 255, 0))
        hl.putalpha(a_sheen)
        glass_card.alpha_composite(hl, (card_x1, card_y1))
        base_img = Image.alpha_composite(base_img, glass_card)
        draw = ImageDraw.Draw(base_img)

        def load_f(p, s):
            try: return ImageFont.truetype(p, s)
            except Exception: return ImageFont.load_default()

        f_modak = str(SHARED_FONTS_DIR / "DFVN-Modak.ttf")
        f_bold = str(SHARED_FONTS_DIR / "BeVietnamPro-Bold.ttf")
        f_reg = str(SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf")
        f_title = load_f(f_modak, 20)
        f_sub = load_f(f_reg, 11)
        f_cat = load_f(f_bold, 10)
        f_cmd = load_f(f_bold, 13)
        f_desc = load_f(f_reg, 11)
        f_badge = load_f(f_bold, 9)
        f_stat = load_f(f_bold, 12)

        # macOS Window Dots
        dot_y = card_y1 + 20
        draw.ellipse([(card_x1 + 22, dot_y), (card_x1 + 32, dot_y + 10)], fill=(255, 95, 86))
        draw.ellipse([(card_x1 + 38, dot_y), (card_x1 + 48, dot_y + 10)], fill=(255, 189, 46))
        draw.ellipse([(card_x1 + 54, dot_y), (card_x1 + 64, dot_y + 10)], fill=(39, 201, 63))

        # Header
        draw.text((card_x1 + 22, card_y1 + 44), "🎯 DISCORD AUTO QUEST", fill=(255, 255, 255), font=f_title)
        draw.text((card_x2 - 86, card_y1 + 50), "v2.5 • AUTO", fill=(160, 170, 185), font=f_sub)

        # Status Banner (Hộp thông số kính trong suốt)
        bx1, by1, bx2, by2 = card_x1 + 14, card_y1 + 80, card_x2 - 14, card_y1 + 172
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=16, fill=(24, 28, 42, 110), outline=(255, 255, 255, 40), width=1)

        auto_on = st.get("is_auto", False)
        status_txt = "🟢 ĐANG AUTO CÀY LIÊN TỤC" if auto_on else "🔴 CHẾ ĐỘ AUTO: ĐANG TẮT"
        status_col = (52, 211, 153) if auto_on else (248, 113, 113)
        draw.text((bx1 + 14, by1 + 12), status_txt, fill=status_col, font=f_stat)

        if st.get("status") == "running" and st.get("quest_name"):
            prog = st.get("progress_pct", 0)
            q_display = st.get("quest_name", "")[:28]
            draw.text((bx1 + 14, by1 + 34), f"Nhiệm vụ: {q_display}", fill=(255, 255, 255), font=f_desc)
            draw.text((bx1 + 14, by1 + 52), f"Loại: {st.get('task_type')} | Quà: {st.get('reward', '')[:18]}", fill=(170, 180, 195), font=f_desc)
            # Progress bar
            pb_w = bx2 - bx1 - 28
            draw.rounded_rectangle([(bx1 + 14, by1 + 72), (bx1 + 14 + pb_w, by1 + 80)], radius=4, fill=(45, 48, 58))
            fill_w = int(pb_w * (prog / 100.0))
            if fill_w > 0:
                draw.rounded_rectangle([(bx1 + 14, by1 + 72), (bx1 + 14 + fill_w, by1 + 80)], radius=4, fill=(52, 211, 153))
            draw.text((bx1 + 14, by1 + 84), f"{prog}% ({st.get('elapsed_seconds',0)}s / {st.get('target_seconds',60)}s)", fill=(160, 170, 185), font=f_sub)
        else:
            draw.text((bx1 + 14, by1 + 40), f"Tổng nhiệm vụ khả dụng: {quests_count} Quest", fill=(255, 255, 255), font=f_desc)
            draw.text((bx1 + 14, by1 + 60), f"Còn cần cày: {uncompleted_count} Quest chưa hoàn thành", fill=(251, 191, 36), font=f_desc)

        # Lệnh điều khiển
        cur_y = card_y1 + 190
        draw.text((card_x1 + 22, cur_y), "BẢNG ĐIỀU KHIỂN & LỆNH CÀY", fill=(150, 160, 175), font=f_cat)
        cur_y += 22

        cmd_items = [
            {"cmd": f"{pfx}quest on", "desc": "Bật tự động cày tất cả nhiệm vụ Discord", "badge": "AUTO", "icon": "🟢"},
            {"cmd": f"{pfx}quest off", "desc": "Dừng chế độ auto cày nhiệm vụ ngay", "badge": "STOP", "icon": "🔴"},
            {"cmd": f"{pfx}quest list", "desc": "Xem danh sách các Quest thật & phần thưởng", "badge": "LIST", "icon": "📋"},
            {"cmd": f"{pfx}quest status", "desc": "Kiểm tra tiến độ % nhiệm vụ đang chạy", "badge": "CHECK", "icon": "📊"},
            {"cmd": f"{pfx}quest start <số>", "desc": "Cày thủ công 1 nhiệm vụ theo thứ tự", "badge": "RUN", "icon": "🚀"},
        ]

        for item in cmd_items:
            item_h = 48
            item_box = [(card_x1 + 14, cur_y), (card_x2 - 14, cur_y + item_h)]
            draw.rounded_rectangle(item_box, radius=14, fill=(28, 30, 38, 215), outline=(255, 255, 255, 18), width=1)
            draw.text((card_x1 + 26, cur_y + 14), item["icon"], fill=(255, 255, 255), font=f_cmd)
            draw.text((card_x1 + 54, cur_y + 8), item["cmd"], fill=(255, 255, 255), font=f_cmd)
            draw.text((card_x1 + 54, cur_y + 26), item["desc"], fill=(160, 170, 180), font=f_desc)

            if item["badge"]:
                b_color = (16, 185, 129) if item["badge"] == "AUTO" else ((239, 68, 68) if item["badge"] == "STOP" else (245, 158, 11))
                bw = 38
                bx = card_x2 - 28 - bw
                draw.rounded_rectangle([(bx, cur_y + 14), (bx + bw, cur_y + 32)], radius=8, fill=b_color)
                draw.text((bx + (bw - draw.textlength(item["badge"], font=f_badge)) // 2, cur_y + 16), item["badge"], fill=(255, 255, 255), font=f_badge)

            cur_y += item_h + 8

        # Footer
        prof_h = 54
        prof_y1 = card_y2 - prof_h - 16
        prof_y2 = prof_y1 + prof_h
        draw.rounded_rectangle([(card_x1 + 14, prof_y1), (card_x2 - 14, prof_y2)], radius=18, fill=(24, 26, 34, 220), outline=(255, 255, 255, 24), width=1)
        user_display = getattr(invoker, "display_name", str(invoker.name))[:16]
        draw.text((card_x1 + 28, prof_y1 + 10), user_display, fill=(255, 255, 255), font=f_stat)
        draw.text((card_x1 + 28, prof_y1 + 28), f"Prefix: [{pfx}] • AutoQuest Module", fill=(150, 160, 175), font=f_sub)

        out = io.BytesIO()
        base_img.save(out, format="PNG")
        out.seek(0)
        return discord.File(fp=out, filename="quest_menu.png")

    async def render_quest_list_gui(self, invoker: discord.User, quests: list) -> discord.File:
        """Render danh sách nhiệm vụ dạng Card hình ảnh sang trọng."""
        card_h = 60
        header_h = 130
        footer_h = 70
        shown_quests = quests[:8]
        total_h = header_h + len(shown_quests) * (card_h + 8) + footer_h
        w = 520
        h = max(550, total_h)
        pfx = self.get_prefix()

        valid_exts = ('.png', '.jpg', '.jpeg', '.jpe', '.webp', '.gif')
        bg_files = []
        if SHARED_BACKGROUNDS_DIR.exists():
            bg_files = [f for f in os.listdir(SHARED_BACKGROUNDS_DIR) if f.lower().endswith(valid_exts)]

        if bg_files:
            try:
                chosen_bg = SHARED_BACKGROUNDS_DIR / random.choice(bg_files)
                with Image.open(chosen_bg) as raw_bg:
                    if getattr(raw_bg, "is_animated", False):
                        raw_bg.seek(0)
                    base_img = raw_bg.convert("RGBA")
                base_img = ImageOps.fit(base_img, (w, h), method=Image.Resampling.BILINEAR)
                # Tối ưu siêu tốc độ: Thu nhỏ -> Blur(2) -> Phóng to (Bokeh mượt tức thì < 5ms)
                small_w, small_h = max(w // 6, 40), max(h // 6, 40)
                small_bg = base_img.resize((small_w, small_h), Image.Resampling.BILINEAR)
                small_bg = small_bg.filter(ImageFilter.GaussianBlur(radius=2))
                base_img = small_bg.resize((w, h), Image.Resampling.BICUBIC)
                dim_layer = Image.new("RGBA", (w, h), (10, 12, 16, 55))
                base_img = Image.alpha_composite(base_img, dim_layer)
            except Exception:
                base_img = Image.new("RGBA", (w, h), (16, 18, 24, 255))
        else:
            base_img = Image.new("RGBA", (w, h), (16, 18, 24, 255))

        card_x1, card_y1, card_x2, card_y2 = 20, 16, w - 20, h - 16
        cw, ch = card_x2 - card_x1, card_y2 - card_y1
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([(card_x1, card_y1 + 4), (card_x2, card_y2 + 4)], radius=24, fill=(0, 0, 0, 80))
        base_img = Image.alpha_composite(base_img, shadow)

        glass_card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gc_draw = ImageDraw.Draw(glass_card)
        gc_draw.rounded_rectangle([(card_x1, card_y1), (card_x2, card_y2)], radius=24, fill=(16, 20, 32, 60), outline=(255, 255, 255, 75), width=1)
        # Specular sheen
        g_raw = Image.linear_gradient("L").resize((cw, ch), Image.Resampling.BILINEAR)
        a_sheen = g_raw.point(lambda v: int(55 * ((255 - v) / 255.0) ** 2.2))
        hl = Image.new("RGBA", (cw, ch), (255, 255, 255, 0))
        hl.putalpha(a_sheen)
        glass_card.alpha_composite(hl, (card_x1, card_y1))
        base_img = Image.alpha_composite(base_img, glass_card)
        draw = ImageDraw.Draw(base_img)

        def load_f(p, s):
            try: return ImageFont.truetype(p, s)
            except Exception: return ImageFont.load_default()

        f_modak = str(SHARED_FONTS_DIR / "DFVN-Modak.ttf")
        f_bold = str(SHARED_FONTS_DIR / "BeVietnamPro-Bold.ttf")
        f_reg = str(SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf")
        f_title = load_f(f_modak, 18)
        f_sub = load_f(f_reg, 11)
        f_qname = load_f(f_bold, 12)
        f_desc = load_f(f_reg, 10)
        f_badge = load_f(f_bold, 9)

        # Header
        draw.text((card_x1 + 22, card_y1 + 22), "📋 DANH SÁCH QUEST DISCORD (THẬT)", fill=(255, 255, 255), font=f_title)
        draw.text((card_x1 + 22, card_y1 + 48), f"Tổng cộng: {len(quests)} nhiệm vụ hợp lệ • Không tính quest ảo/hết hạn", fill=(160, 170, 185), font=f_sub)

        cur_y = card_y1 + 78
        for idx, q in enumerate(shown_quests, start=1):
            box = [(card_x1 + 14, cur_y), (card_x2 - 14, cur_y + card_h)]
            draw.rounded_rectangle(box, radius=12, fill=(28, 30, 38, 215), outline=(255, 255, 255, 18), width=1)

            st_color = (52, 211, 153) if q["completed"] else ((251, 191, 36) if q["enrolled"] else (150, 155, 165))
            st_text = "XONG" if q["completed"] else (f"{q['progress_pct']}%" if q["enrolled"] else "CHƯA")

            draw.text((card_x1 + 24, cur_y + 12), f"#{idx}", fill=(251, 191, 36), font=f_qname)
            q_title = q["name"][:32]
            draw.text((card_x1 + 52, cur_y + 10), q_title, fill=(255, 255, 255), font=f_qname)
            draw.text((card_x1 + 52, cur_y + 32), f"{q['task_type']} • Quà: {q['reward'][:22]}", fill=(160, 170, 185), font=f_desc)

            # Badge status
            bw = 44
            bx = card_x2 - 24 - bw
            draw.rounded_rectangle([(bx, cur_y + 16), (bx + bw, cur_y + 34)], radius=6, fill=st_color)
            draw.text((bx + (bw - draw.textlength(st_text, font=f_badge)) // 2, cur_y + 18), st_text, fill=(255, 255, 255), font=f_badge)

            cur_y += card_h + 8

        # Footer
        draw.text((card_x1 + 22, card_y2 - 32), f"👉 Gõ '{pfx}quest on' để auto cày hết | '{pfx}quest start <số>' để cày lẻ", fill=(170, 180, 195), font=f_sub)

        out = io.BytesIO()
        base_img.save(out, format="PNG")
        out.seek(0)
        return discord.File(fp=out, filename="quest_list.png")

    @menu_entry("AUTOMATION & QUEST", "quest", "Menu ảnh Dashboard & auto cày Quest",
                badge="AUTO", icon_sym="⚡", icon_color=(251, 191, 36), order=1)
    @alias_declare("quest", main="quest", subs=["autoquest"])
    @commands.command(name="quest", aliases=["autoquest"])
    @require_permission("mod")
    async def cmd_quest(self, ctx, action: str = None, target: str = None):
        """Hệ thống tự động cày nhiệm vụ Discord Quest (CHỈ ADMIN CẤP CAO): (prefix)quest"""
        # Chặn thủ công: chỉ Admin cấp cao (admintris) được dùng, kể cả khi bot
        # đang OFF hay người gọi bị CAM -> kiểm tra lại trước khi xử lý token.
        if not self._is_high_admin(ctx.author.id):
            await self._deny_high_admin(ctx)
            return
        token = self.get_token()
        if not token:
            await self.reply_text(ctx.message, "❌ Không tìm thấy token của tài khoản selfbot hiện tại.", delay=30)
            return

        pfx = self.get_prefix()
        act = (action or "").lower().strip()

        # 1. Gõ trần '(prefix)quest' hoặc '(prefix)quest menu' -> Gửi Card Ảnh Menu sang trọng
        if not act or act in ["menu", "help", "hd"]:
            quests = self.runner._fetch_quests(token)
            uncompleted = [q for q in quests if not q["completed"]]
            file = await self.render_quest_menu_gui(ctx.author, self.runner.get_status(), len(quests), len(uncompleted))
            try:
                from apps.user_discord.utils.autorep import autorep
            except ImportError:
                from utils.autorep import autorep
            await autorep(ctx.message, file=file, auto_delete_delay=45)
            return

        # 2. (prefix)quest on: Bật chế độ tự động cày
        if act in ["on", "bat", "start_auto"]:
            self.runner.start_auto(token)
            msg = (
                "🟢 **ĐÃ BẬT CHẾ ĐỘ AUTO CÀY QUEST DISCORD!**\n"
                "Bot đang tự động quét và cày tuần tự các nhiệm vụ Discord chưa hoàn thành.\n"
                f"👉 Gõ `{pfx}quest status` để kiểm tra tiến trình đang chạy."
            )
            await self.reply_text(ctx.message, msg, delay=30)
            return

        # 3. (prefix)quest off: Tắt chế độ tự động cày
        if act in ["off", "tat", "stop"]:
            self.runner.stop()
            msg = "🔴 **ĐÃ TẮT CHẾ ĐỘ AUTO CÀY QUEST DISCORD.**\nTiến trình cày đã được dừng lại an toàn."
            await self.reply_text(ctx.message, msg, delay=30)
            return

        # 4. (prefix)quest status: Xem tiến trình đang cày
        if act in ["status", "st", "check"]:
            st = self.runner.get_status()
            auto_tag = "🟢 **ĐANG BẬT**" if st["is_auto"] else "🔴 **ĐANG TẮT**"
            
            lines = [
                "📊 **TRẠNG THÁI QUEST RUNNER**",
                "───────────────────────────────",
                f"• Chế độ Auto Cày: {auto_tag}",
            ]

            if st["status"] == "running" and st["quest_name"]:
                prog = st["progress_pct"]
                filled = int(prog / 10)
                bar = "🟩" * filled + "⬜" * (10 - filled)
                lines.extend([
                    f"• Đang cày: **{st['quest_name']}**",
                    f"• Loại nhiệm vụ: `{st['task_type']}`",
                    f"• Tiến độ: {bar} **{prog}%** ({st['elapsed_seconds']}s / {st['target_seconds']}s)",
                    f"• Phần thưởng: 🎁 **{st['reward']}**",
                ])
            elif st["is_auto"]:
                lines.append("• Tình trạng: ⏳ Đang quét tìm nhiệm vụ mới hoặc đã hoàn thành toàn bộ...")
            else:
                lines.extend([
                    "• Tình trạng: ⏸️ Đang nghỉ (Auto cày đang tắt)",
                    f"• Nhập `{pfx}quest on` để kích hoạt cày tự động!",
                ])

            lines.append("───────────────────────────────")
            await self.reply_text(ctx.message, "\n".join(lines), delay=30)
            return

        # 5. (prefix)quest list: Xem danh sách nhiệm vụ bằng Card Ảnh & danh sách thật
        if act in ["list", "ls", "ds"]:
            quests = self.runner._fetch_quests(token)
            if not quests:
                await self.reply_text(ctx.message, "⚠️ Hiện tài khoản không có Quest nào khả dụng trên Discord.", delay=30)
                return

            list_file = await self.render_quest_list_gui(ctx.author, quests)
            extra_lines = []
            if len(quests) > 8:
                extra_lines.append(f"📋 *Hiển thị 8/{len(quests)} nhiệm vụ đầu tiên trên Card ảnh.*")
                extra_lines.append(f"👉 Dùng `{pfx}quest start <1-{len(quests)}>` để cày nhiệm vụ tương ứng, hoặc `{pfx}quest on` để cày tất cả!")
            
            content_txt = "\n".join(extra_lines) if extra_lines else None
            try:
                from apps.user_discord.utils.autorep import autorep
            except ImportError:
                from utils.autorep import autorep
            await autorep(ctx.message, content=content_txt, file=list_file, auto_delete_delay=60)
            return

        # 6. (prefix)quest start <stt>: Cày lẻ 1 quest chỉ định
        if act in ["start", "run", "cay"]:
            quests = self.runner._fetch_quests(token)
            if not target or not target.isdigit():
                await self.reply_text(ctx.message, f"❌ Vui lòng nhập số thứ tự Quest: `{pfx}quest start <số>`", delay=30)
                return
            idx = int(target)
            if 1 <= idx <= len(quests):
                chosen = quests[idx - 1]
                if chosen["completed"]:
                    await self.reply_text(ctx.message, f"✅ Quest **{chosen['name']}** đã hoàn thành rồi, không cần cày!", delay=30)
                    return
                # Chạy quest này
                self.runner.stop()
                with self.runner.lock:
                    self.runner.is_auto_enabled = True
                    self.runner.stop_flag.clear()
                    self.runner.status = "running"
                    self.runner.current_quest_id = chosen["id"]
                    self.runner.current_quest_name = chosen["name"]
                    self.runner.task_type = chosen["task_type"]
                    self.runner.target_seconds = max(10, chosen["target_seconds"])
                    self.runner.elapsed_seconds = int(chosen["seconds_done"])
                    self.runner.progress_pct = chosen["progress_pct"]
                    self.runner.reward = chosen.get("reward", "")
                    self.runner.loop_thread = threading.Thread(target=self.runner._process_single_quest, args=(token, chosen), daemon=True)
                    self.runner.loop_thread.start()

                await self.reply_text(ctx.message, f"🚀 Bắt đầu cày Quest #{idx}: **{chosen['name']}** (~{chosen['target_seconds']}s)!\nGõ `{pfx}quest status` để kiểm tra tiến trình.", delay=30)
            else:
                await self.reply_text(ctx.message, "❌ Số thứ tự Quest không hợp lệ.", delay=30)
            return

        await self.reply_text(ctx.message, f"❌ Cú pháp không đúng. Gõ `{pfx}quest` để xem hướng dẫn đầy đủ.", delay=30)


async def setup(bot):
    await bot.add_cog(AutoQuestModule(bot))
