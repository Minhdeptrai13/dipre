"""
default_cards.py
----------------
Khai bao schema help-card cho cac module mac dinh:
  voice, afk, rpc, activity, del, youtube, soundcloud, tiktok,
  genesis, genesis_shard, read, bread, info, alias, alis

Module nay duoc tu dong nap boi card_registry._bootstrap().
Moi module rieng le (vi du: voice.py, alias.py) co the goi
register_card() rieng de OVERRIDE hoac THEM card moi.

Logo drawers duoc import tu media_card de khong duplicate code.
"""
from __future__ import annotations

try:
    from apps.user_discord.utils.card_registry import register_card, CardSchema
    from apps.user_discord.utils import media_card as MC
except ImportError:
    from utils.card_registry import register_card, CardSchema  # type: ignore
    from utils import media_card as MC  # type: ignore


# ────────────── VOICE ──────────────
register_card("voice", CardSchema(
    title="VOICE 24/7 & AUTO-KEEPER",
    sub="He thong ket noi Voice 24/7 sieu nhe & tu dong giu phong",
    accent=(74, 222, 128),
    logo_fn=MC.draw_voice_logo_hires,
    tip="Tiet kiem RAM toi da qua Gateway Opcode 4 - Tu dong ket noi lai khi rot mang.",
    items=[
        ("voice",                      "Hien thi bang huong dan dieu khien Voice nay",          "HELP"),
        ("voice join [id|link]",        "Tham gia phong voice & kich hoat che do treo 24/7",     "JOIN 24/7"),
        ("voice leave",                 "Roi khoi phong voice va tat che do treo 24/7",           "LEAVE"),
        ("voice status",                "Xem chi tiet thong so Uptime & tinh trang ket noi",     "STATUS"),
        ("voice deaf <on|off>",         "Bat/tat che do diec tai ao (Deafen) tiet kiem mang",    "DEAFEN"),
        ("voice mute <on|off>",         "Bat/tat che do tat mic ao (Mute) an toan",              "MUTE"),
        ("voice video <on|off>",        "Bat/tat trang thai phat camera ao (Video Stream)",      "VIDEO"),
        ("voice keeper <on|off>",       "Bat/tat tu dong vao lai khi bi kick hoac mat ket noi", "AUTO KEEPER"),
    ]
))

# ────────────── AFK ──────────────
register_card("afk", CardSchema(
    title="AFK & AUTO RESPONDER",
    sub="Tu dong phan hoi khi duoc Tag hoac Inbox rieng & Thong ke tin nhan",
    accent=(59, 130, 246),
    logo_fn=MC.draw_afk_logo_hires,
    tip="Khi ban nhan tin lai, bot se tu tat AFK va gui bang thong ke chi tiet ai da tag/inbox.",
    items=[
        ("afk [tin nhan phan hoi]", "Bat che do AFK voi tin nhan tu dong tra loi tuy chon",  "ENABLE"),
        ("afk off",                  "Chu dong tat che do AFK va xuat bang thong ke chi tiet", "DISABLE"),
        ("afk status",               "Xem trang thai AFK hien tai va so tin nhan da ghi nhan", "STATUS"),
        ("afk clear",                "Xoa nhat ky tin nhan ghi nhan ma khong tat AFK",         "CLEAR"),
    ]
))

# ────────────── RPC / ACTIVITY ──────────────
_RPC_SCHEMA = CardSchema(
    title="RICH PRESENCE CONTROL (RPC)",
    sub="Tuy bien trang thai Online & Hoat dong ao (Stream / Game / Nhac)",
    accent=(168, 85, 247),
    logo_fn=MC.draw_activity_logo_hires,
    tip="Trang thai va RPC duoc tu dong luu vinh vien theo UID va khoi phuc khi bot online.",
    items=[
        ("rpc status <online|idle|dnd|inv>",   "Doi trang thai hien thi (Online, Cho, Ban, An)",        "STATUS"),
        ("rpc play <ten game>",                  "Hien thi dang choi game (Dang choi <ten game>)",        "PLAYING"),
        ("rpc stream <ten stream> [link]",       "Hien thi phat truc tiep Twitch/YouTube (Huy hieu Tim)", "STREAMING"),
        ("rpc listen <ten bai hat/nhac>",        "Hien thi dang nghe nhac (Dang nghe <nhac>)",            "LISTENING"),
        ("rpc watch <ten phim/video>",           "Hien thi dang xem phim (Dang xem <ten>)",               "WATCHING"),
        ("rpc clear",                            "Xoa hoat dong ao, tro ve trang thai binh thuong",        "CLEAR"),
    ]
)
register_card("rpc",      _RPC_SCHEMA)
register_card("activity", _RPC_SCHEMA)

# ────────────── DELETE ──────────────
register_card("del", CardSchema(
    title="DELETE & PURGE SYSTEM",
    sub="He thong xoa tin nhan sieu toc (Reply / So luong / Toan bo)",
    accent=(239, 68, 68),
    logo_fn=MC.draw_trash_logo_hires,
    tip="Reply tin nhan bat ky + del de xoa ngay - Go del <so> de xoa N tin - del all de don sach.",
    items=[
        ("del",          "Hien thi bang huong dan xoa tin nhan do hoa nay",          "HELP"),
        ("del [reply]",  "Reply tin nhan bat ky + go del de xoa ngay tin nhan do",   "REPLY"),
        ("del <so>",     "Xoa N tin nhan gan nhat (tu dong chong Discord rate-limit)", "AMOUNT"),
        ("del all",      "Quet va don sach toan bo tin nhan ban than trong kenh / DM", "ALL"),
        ("del bot",      "Chi quet va xoa tin nhan do chinh selfbot gui trong kenh",   "SELF ONLY"),
    ]
))

# ────────────── YOUTUBE ──────────────
register_card("youtube", CardSchema(
    title="YOUTUBE COMMAND PANEL",
    sub="He thong phat nhac Voice & tai video YouTube HD",
    accent=(255, 45, 45),
    logo_fn=MC.draw_yt_logo_hires,
    tip="Meo: Khi hien bang danh sach 1-20, go them 'v' de phat Voice, 'f' de nhan File, hoac 'c' de huy bo.",
    items=[
        ("yt <tu khoa>",         "Tim kiem 20 video -> Bam so chon phat Voice hoac gui file", "SEARCH"),
        ("yt <link video>",       "Phat thang vao Voice Chat hoac tai video MP4 gui len",      "DIRECT"),
        ("yt <link/tu khoa> v",   "Ep buoc phat am thanh truc tiep vao phong Voice Chat",      "VOICE"),
        ("yt <link/tu khoa> f",   "Ep buoc tai file video MP4 (toi da 25MB) gui truc tiep",    "FILE MP4"),
        ("yt stop",               "Dung phat am thanh ngay lap tuc va roi khoi phong Voice",   "STOP"),
    ]
))

# ────────────── SOUNDCLOUD ──────────────
register_card("soundcloud", CardSchema(
    title="SOUNDCLOUD COMMAND PANEL",
    sub="He thong phat nhac Voice & tai track SoundCloud chat luong cao",
    accent=(255, 102, 0),
    logo_fn=MC.draw_sc_logo_hires,
    tip="Meo: Khi hien bang danh sach 1-20, go them 'v' de phat Voice, 'f' de nhan File, hoac 'c' de huy bo.",
    items=[
        ("scl <ten bai hat>",      "Tim kiem 20 track nhac -> Chon phat Voice hoac tai MP3", "SEARCH"),
        ("scl <link track>",        "Phat truc tiep vao Voice Chat hoac tai file MP3 gui len", "DIRECT"),
        ("scl <link/track> v",      "Ep buoc phat am thanh bai hat vao phong Voice Chat",      "VOICE"),
        ("scl <link/track> f",      "Ep buoc tai file nhac MP3 chat luong cao ve Discord",     "FILE MP3"),
        ("scl stop",                "Dung phat nhac SoundCloud ngay lap tuc va roi khoi Voice", "STOP"),
    ]
))

# ────────────── TIKTOK ──────────────
register_card("tiktok", CardSchema(
    title="TIKTOK COMMAND PANEL",
    sub="He thong tai video khong logo & phat nhac xu huong TikTok",
    accent=(0, 242, 234),
    logo_fn=MC.draw_tt_logo_hires,
    tip="Meo: Khi hien bang danh sach 1-20, go them 'v' de phat Voice, 'f' de nhan File, hoac 'c' de huy bo.",
    items=[
        ("tt <link tiktok>",       "Tai video TikTok khong logo (Watermark-free) hoac phat Voice", "NO WATERMARK"),
        ("tt <tu khoa>",            "Tim kiem 20 video thinh hanh theo chu de Hot Trend",           "TRENDING"),
        ("tt <link/trend> v",       "Phat am thanh/nhac nen cua video TikTok vao phong Voice",     "VOICE"),
        ("tt <link/trend> f",       "Ep buoc tai video goc khong logo MP4 gui len Discord",         "FILE MP4"),
        ("tt stop",                 "Dung phat am thanh TikTok va thoat khoi phong Voice",          "STOP"),
    ]
))

# ────────────── GENESIS (prime) ──────────────
register_card("genesis", CardSchema(
    title="GENESIS COMMAND PANEL",
    sub="Ha tang khai bao & quan ly bot chinh / phu (prime / shard)",
    accent=(139, 92, 246),
    logo_fn=MC.draw_genesis_logo_hires,
    tip="Duyet bot: Chi BOT CHINH (prime) moi unlock/start/remove - Doi prefix: Dung gene prefix.",
    items=[
        ("gene prefix [bot] <prefix_moi>",      "DOI PREFIX cho bot chinh hoac bot phu (chi Admin cap cao)",           "PREFIX"),
        ("gene create <token> <ten> <prefix>",   "Dang ky bot phu vao config.json (trang thai khoa, cho duyet)",       "CREATE"),
        ("gene qrlogin",                          "Quet QR bang Discord mobile de lay acc -> tao bot hoac nhan token",  "QRLOGIN"),
        ("gene unlock <@bot|id>",                 "Duyet & mo khoa bot phu -- BAT BUOC truoc khi start",               "UNLOCK"),
        ("gene start <@bot|id> <time>",           "KHOI DONG bot phu ngay + gan thoi gian (khong can restart)",        "START"),
        ("gene list",                             "Xem so dang anh: avatar / role / thoi gian / trang thai",           "LIST"),
        ("gene lock <@bot|id>",                   "Khoa bot phu lai (chan moi lenh, bot van online)",                   "LOCK"),
        ("gene stop <@bot|id>",                   "Tat han bot phu (shutdown tien trinh)",                              "STOP"),
        ("gene update <@bot|id> <token>",         "Cap nhat token moi cho bot (tu nap lai ngay)",                      "UPDATE"),
        ("gene reset [tag]",                      "RESET -- bo trong: ca he thong; co tag: rieng 1 bot",               "RESET"),
        ("gene reload <ten> [bot]",               "Nap lai extension cua bot chinh hoac bot phu",                      "RELOAD"),
        ("gene remove <@bot|id>",                 "Xoa vinh vien bot phu khoi config.json",                            "REMOVE"),
        ("gene",                                  "Xem lai bang huong dan genesis nay bat cu luc nao",                  "HELP"),
    ]
))

# ────────────── GENESIS SHARD ──────────────
register_card("genesis_shard", CardSchema(
    title="GENESIS -- BANG DIEU KHIEN BOT PHU",
    sub="Cac lenh cau hinh & dieu khien rieng cho Bot Phu (Shard)",
    accent=(168, 85, 247),
    logo_fn=MC.draw_genesis_logo_hires,
    tip="Cac lenh duyet cap cao (unlock, start, lock, stop, remove) bat buoc chay qua BOT CHINH.",
    items=[
        ("gene prefix <prefix_moi>",  "Doi prefix rieng cho bot phu nay (chi Admin cap cao cua bot)", "PREFIX"),
        ("gene info [bot]",            "Xem the anh thong tin bot (prefix, status, role, token, thoi han)", "INFO CARD"),
        ("gene reset",                 "Khoi dong lai (reset) bot phu nay de cap nhat cai dat",         "RESET"),
        ("gene update <token>",        "Cap nhat chuoi token dang nhap moi cho bot phu nay",            "UPDATE TOKEN"),
        ("gene qrlogin",               "Quet ma QR Discord dang nhap tai khoan lay token",              "QR LOGIN"),
        ("gene create",                "Dang ky them bot phu moi vao he thong (cho duyet)",             "CREATE BOT"),
        ("gene",                       "Xem lai bang huong dan danh rieng cho bot phu nay",             "HELP"),
    ]
))

# ────────────── READ / BREAD ──────────────
_READ_SCHEMA = CardSchema(
    title="READ & NOTIFICATION ACK SYSTEM",
    sub="Danh dau da doc & don sach cham do thong bao may chu, nhom & DM",
    accent=(52, 211, 153),
    logo_fn=MC.draw_read_logo_hires,
    tip="Go 'read' hoac 'bread' hien huong dan anh nay - Dung 'read list' xem luoi may chu dong.",
    items=[
        ("read",               "Hien thi bang huong dan danh dau da doc anh nay",          "GUIDE"),
        ("read all [force]",   "Danh dau da doc toan bo may chu (them 'force' de ep doc)", "READ ALL"),
        ("read list",          "Luoi anh Liquid Glass danh sach may chu kem so chon 1..N", "GRID LIST"),
        ("read <id|ten>",      "Danh dau da doc 1 may chu cu the theo ID hoac ten",        "TARGET"),
        ("read group",         "Danh dau da doc tat ca nhom chat rieng (Group DMs)",       "READ GROUPS"),
        ("read group list",    "Xem danh sach cac nhom chat rieng chua doc",               "GROUPS LIST"),
        ("read user",          "Danh dau da doc toan bo tin nhan rieng ca nhan (DMs)",     "READ DMS"),
        ("read user list",     "Xem danh sach nhung nguoi nhan tin rieng chua doc",        "USERS LIST"),
    ]
)
register_card("read",  _READ_SCHEMA)
register_card("bread", _READ_SCHEMA)

# ────────────── INFO ──────────────
register_card("info", CardSchema(
    title="INFORMATION SYSTEM PANEL",
    sub="Tra cuu ho so tai khoan Discord & thong tin may chu sac net",
    accent=(56, 189, 248),
    logo_fn=MC.draw_info_logo_hires,
    tip="Co the tag nhieu nguoi cung luc: info @user1 @user2 de xuat the anh cho tung nguoi.",
    items=[
        ("info",               "Hien thi bang huong dan tra cuu thong tin dang anh nay",  "HELP"),
        ("info user [@user|id]", "Tra cuu the thong tin tai khoan (ho tro tag nhieu nguoi)", "USER INFO"),
        ("info server",         "Xem the Liquid Glass chi tiet ve may chu hien tai",        "SERVER INFO"),
        ("userinfo [@user]",    "Lenh tat nhanh tra cuu thong tin nguoi dung",             "SHORTCUT"),
        ("serverinfo",          "Lenh tat nhanh tra cuu thong tin may chu",                "SHORTCUT"),
    ]
))

# ────────────── ALIAS / ALIS ──────────────
_ALIAS_SCHEMA = CardSchema(
    title="ALIAS & COMMAND SHORTCUTS",
    sub="He thong quan ly bi danh chinh & phu cho cac nhom lenh (Replace Mode)",
    accent=(236, 72, 153),
    logo_fn=MC.draw_alias_logo_hires,
    tip="Go dung ten lenh mac dinh khi reset -- Dung alis reset all de ve ban dau.",
    items=[
        ("alis set main <lenh> to <ten_moi>", "Doi bi danh chinh (vi du: alis set main menu to help)",            "SET MAIN"),
        ("alis set sub <lenh> to <phu...>",   "Doi danh sach bi danh phu (vi du: alis set sub menu to mn, hlp)", "SET SUBS"),
        ("alis reset main <lenh|all>",         "Khoi phuc rieng bi danh chinh ve mac dinh goc (hoac all)",        "RESET MAIN"),
        ("alis reset sub <lenh|all>",          "Khoi phuc rieng bi danh phu ve mac dinh goc (hoac all)",          "RESET SUBS"),
        ("alis reset [lenh|all]",              "Khoi phuc ca chinh & phu ve mac dinh ban dau cua he thong",       "RESET ALL"),
        ("alis list",                           "Xem danh sach song song Bang Mac Dinh & Bang Hien Tai",           "LIST"),
        ("alis",                               "Xem lai bang huong dan dieu khien bi danh dang anh nay",          "HELP"),
    ]
)
register_card("alias", _ALIAS_SCHEMA)
register_card("alis",  _ALIAS_SCHEMA)

# ────────────── AI CHATBOT ──────────────
_AI_SCHEMA = CardSchema(
    title="DIPRE AI SMART ASSISTANT",
    sub="Tro ly AI 3 bac (Flash / Standard / Pro) & Cau noi du lieu UserBot",
    accent=(31, 202, 173),  # Ngoc luc bao DIPRE
    logo_fn=MC.draw_dipre_crest_logo_hires,
    tip="Khi bat AI (ai on), chi can Tag @bot la AI tu rep! Ho tro tag <@user> & gui avatar.",
    items=[
        ("ai",                         "Mo bang huong dan su dung tro ly DIPRE AI nay",            "HELP"),
        ("ai <cau hoi>",               "Hoi dap truc tiep voi AI (co cau noi data & gui avatar)",  "ASK AI"),
        ("ai model [flash|std|pro]",   "Xem & doi bac model AI (Admin cap cao)",                   "CHANGE MODEL"),
        ("ai think [low|medium|high]", "Xem & doi cap do tu duy AI: Thap / Trung binh / Cao",      "THINK LEVEL"),
        ("ai clear",                   "Xoa sach tri nho lich su hoi thoai tai kenh nay",          "CLEAR MEMORY"),
        ("ai on",                      "Bat che do AI tu dong tra loi khi duoc Tag @bot tai server","ENABLE"),
        ("ai off",                     "Tat che do AI tu dong tra loi tai server nay",             "DISABLE"),
        ("ai status",                  "Kiem tra trang thai model, tu duy & cac server dang bat",  "STATUS"),
    ]
)
register_card("ai", _AI_SCHEMA)
register_card("chat", _AI_SCHEMA)
register_card("ask", _AI_SCHEMA)

# ────────────── MEDIA DOWNLOADER ──────────────
_DL_SCHEMA = CardSchema(
    title="UNIVERSAL MEDIA DOWNLOADER",
    sub="Tai video FB Reels, IG, X/Twitter, Threads, TikTok, Shorts sieu toc",
    accent=(56, 189, 248),  # Xanh cyan hien dai
    logo_fn=MC.draw_tt_logo_hires,
    tip="Ho tro ca link truc tiep va tim kiem theo tu khoa da nen tang!",
    items=[
        ("dl",                  "Mo bang huong dan tai video da nen tang nay",               "HELP"),
        ("dl <link|tu_khoa>",   "Tu dong nhan dien link hoac tim kiem video theo tu khoa",    "AUTO GET"),
        ("dl <nen_tang> <link|tu_khoa>", "Chi dinh nen tang (fb, ig, x, threads, tt, yt...)", "SPECIFY"),
        ("dl on",               "Bat che do tu dong tai video khi thay link trong server",   "ENABLE"),
        ("dl off",              "Tat che do tu dong tai video tai server nay",                "DISABLE"),
        ("dl status",           "Xem the Liquid Glass trang thai cac server bat tu dong",    "STATUS"),
    ]
)
register_card("dl", _DL_SCHEMA)
register_card("download", _DL_SCHEMA)

# ────────────── FACEBOOK DOWNLOADER ──────────────
_FB_SCHEMA = CardSchema(
    title="FACEBOOK MEDIA DOWNLOADER",
    sub="Tai video Facebook Reels, Watch, Post sieu toc khong logo",
    accent=(24, 119, 242),  # Xanh duong Facebook
    logo_fn=MC.draw_fb_logo_hires,
    tip="Ho tro dan link truc tiep (Reels, Watch, Anh) hoac tim kiem theo tu khoa.",
    items=[
        ("fb",                  "Mo bang huong dan tai media Facebook nay",                 "HELP"),
        ("fb <link|tu_khoa>",   "Tai video Reels, Watch, Anh FB hoac tim kiem theo tu khoa", "DOWNLOAD"),
    ]
)
register_card("fb", _FB_SCHEMA)
register_card("facebook", _FB_SCHEMA)

# ────────────── INSTAGRAM DOWNLOADER ──────────────
_IG_SCHEMA = CardSchema(
    title="INSTAGRAM MEDIA DOWNLOADER",
    sub="Tai video Instagram Reels, Post, TV chat luong cao goc",
    accent=(225, 48, 108),  # Tim hong Instagram
    logo_fn=MC.draw_ig_logo_hires,
    tip="Ho tro ca link truc tiep va tim kiem Reel theo tu khoa.",
    items=[
        ("ig",                  "Mo bang huong dan tai video Instagram nay",                "HELP"),
        ("ig <link|tu_khoa>",   "Tai video Instagram Reels hoac tim kiem theo tu khoa",     "DOWNLOAD"),
    ]
)
register_card("ig", _IG_SCHEMA)
register_card("insta", _IG_SCHEMA)
register_card("instagram", _IG_SCHEMA)

# ────────────── X (TWITTER) DOWNLOADER ──────────────
_X_SCHEMA = CardSchema(
    title="X (TWITTER) MEDIA DOWNLOADER",
    sub="Tai video va GIF tren mang xa hoi X (Twitter) sieu toc",
    accent=(29, 155, 240),  # Xanh X / Twitter
    logo_fn=MC.draw_x_logo_hires,
    tip="Ho tro ca link x.com va tim kiem video X theo tu khoa.",
    items=[
        ("x",                   "Mo bang huong dan tai video X / Twitter nay",               "HELP"),
        ("x <link|tu_khoa>",    "Tai video tu bai dang X hoac tim kiem theo tu khoa",       "DOWNLOAD"),
    ]
)
register_card("x", _X_SCHEMA)
register_card("twitter", _X_SCHEMA)

# ────────────── THREADS DOWNLOADER ──────────────
_THREADS_SCHEMA = CardSchema(
    title="THREADS MEDIA DOWNLOADER",
    sub="Tai video tren mang xa hoi Threads chat luong cao",
    accent=(10, 10, 10),    # Den toi gian Threads
    logo_fn=MC.draw_threads_logo_hires,
    tip="Ho tro ca link Threads va tim kiem theo tu khoa.",
    items=[
        ("threads",             "Mo bang huong dan tai video Threads nay",                  "HELP"),
        ("threads <link|tu_khoa>", "Tai video Threads hoac tim kiem theo tu khoa",           "DOWNLOAD"),
    ]
)
register_card("threads", _THREADS_SCHEMA)
register_card("th", _THREADS_SCHEMA)

# ────────────── TRANSLATE / DICH THUAT ──────────────
_TRANS_SCHEMA = CardSchema(
    title="UNIVERSAL TRANSLATION SYSTEM",
    sub="He thong dich thuat da ngon ngu thong minh & tu dong hoa Realtime",
    accent=(14, 165, 233),  # Sky blue cong nghe
    logo_fn=MC.draw_read_logo_hires,
    tip="Co the reply tin nhan bat ky roi go 'dich' de tu dong dich tin nhan do!",
    items=[
        ("dich",                "Mo bang huong dan dich thuat dang anh nay",                 "HELP"),
        ("dich <van_ban>",      "Dich van ban sang ngon ngu dang set (hoac reply tin nhan)", "TRANSLATE"),
        ("dich set <ma_ngon_ngu>", "Cai dat ngon ngu dich mac dinh (mac dinh: vi)",         "SET LANG"),
        ("dich list",           "Xem danh sach cac ma ngon ngu quoc te ho tro",              "LANG LIST"),
        ("dich on",             "Bat che do tu dong dich ngon ngu la tai server",             "ENABLE"),
        ("dich off",            "Tat che do tu dong dich tai server nay",                     "DISABLE"),
        ("dich status",         "Xem the Liquid Glass trang thai he thong dich",              "STATUS"),
    ]
)
register_card("dich", _TRANS_SCHEMA)
register_card("trans", _TRANS_SCHEMA)
register_card("dịch", _TRANS_SCHEMA)

# ────────────── CRYPTO & FINANCE ──────────────
_CRYPTO_SCHEMA = CardSchema(
    title="CRYPTO & FINANCE TRADING HUB",
    sub="Tra cuu thi truong Tien Dien Tu, Gia Vang SJC & Ty Gia Ngoai Te Realtime",
    accent=(245, 158, 11),  # Vang cam Binance / Crypto
    logo_fn=MC.draw_genesis_logo_hires,
    tip="Go 'btc', 'eth', 'sol', 'gold' de xem nhanh the Liquid Glass bien dong gia!",
    items=[
        ("crypto",              "Mo bang tong quan thi truong Top Coin Liquid Glass",       "OVERVIEW"),
        ("crypto <symbol>",     "Tra cuu chi tiet dong coin (btc, eth, sol, bnb, pepe...)", "LOOKUP"),
        ("btc / eth / sol",     "Lenh tat nhanh tra cuu the gia dong coin tuong ung",       "SHORTCUT"),
        ("gold / vang",         "Tra cuu gia vang SJC va vang the gioi moi nhat",           "GOLD"),
        ("usd / tygia",         "Tra cuu ty gia USD, EUR, JPY sang VND",                    "FOREX"),
    ]
)
register_card("crypto", _CRYPTO_SCHEMA)
register_card("coin", _CRYPTO_SCHEMA)
register_card("finance", _CRYPTO_SCHEMA)

# ────────────── WEATHER / THOI TIET ──────────────
_WEATHER_SCHEMA = CardSchema(
    title="GLOBAL WEATHER RADAR",
    sub="Tra cuu du lieu thoi tiet realtime tai moi tinh thanh, quoc gia toan cau",
    accent=(14, 165, 233),  # Xanh troi quang dang
    logo_fn=MC.draw_read_logo_hires,
    tip="Ho tro moi tinh thanh Viet Nam va the gioi khong can API key: thoitiet Ha Noi, weather Tokyo...",
    items=[
        ("thoitiet",            "Mo bang huong dan tra cuu thoi tiet Liquid Glass",          "HELP"),
        ("thoitiet <dia_diem>", "Tra cuu thoi tiet truc tiep (Nhiet do, UV, gio, do am...)", "FORECAST"),
        ("weather <location>",  "Tra cuu thoi tiet bang ten quoc te hoac tieng Anh",         "GLOBAL"),
        ("wt <dia_diem>",       "Lenh tat nhanh tra cuu the thoi tiet Liquid Glass",         "SHORTCUT"),
    ]
)
register_card("thoitiet", _WEATHER_SCHEMA)
register_card("weather", _WEATHER_SCHEMA)
register_card("wt", _WEATHER_SCHEMA)

# ────────────── AUDIO EXTRACTOR / TACH NHAC ──────────────
_EXTRACT_SCHEMA = CardSchema(
    title="AUDIO EXTRACTOR & MP3 CONVERTER",
    sub="Trich xuat am thanh chat luong cao 192kbps tu video clip bat ky",
    accent=(168, 85, 247),  # Tim cong nghe am thanh
    logo_fn=MC.draw_tt_logo_hires,
    tip="Reply tin nhan video bat ky hoac gui link TikTok/FB/IG/X/YT roi go 'tachnhac'!",
    items=[
        ("tachnhac",            "Mo bang huong dan tach am thanh dang anh Liquid Glass",     "HELP"),
        ("tachnhac [reply/file]", "Tach am thanh MP3 192kbps tu video reply hoac file kem",   "EXTRACT"),
        ("tachnhac <link>",     "Tach nhac tu link TikTok, Facebook, IG, X, Threads, YT",   "DOWNLOAD"),
        ("tachnhac <link> v",   "Tach am thanh va stream phat truc tiep vao phong Voice",   "STREAM VOICE"),
    ]
)
register_card("tachnhac", _EXTRACT_SCHEMA)
register_card("mp3", _EXTRACT_SCHEMA)
register_card("audio", _EXTRACT_SCHEMA)
register_card("extract", _EXTRACT_SCHEMA)
register_card("tachamthanh", _EXTRACT_SCHEMA)

# ────────────── GITHUB DEVELOPER & REPOSITORY ──────────────
_GITHUB_SCHEMA = CardSchema(
    title="GITHUB DEVELOPER & REPOSITORY HUB",
    sub="Tra cuu ho so lap trinh vien, kho ma nguon va phien ban release GitHub",
    accent=(99, 102, 241),  # Tim anh sang GitHub Developer
    logo_fn=MC.draw_genesis_logo_hires,
    tip="Co the go tat 'git <user/repo>' de xem ngay thong so repository!",
    items=[
        ("git",                 "Mo bang huong dan tra cuu GitHub Liquid Glass nay",         "HELP"),
        ("git user <username>", "Soi ho so Dev (Avatar, Repos, Followers, Bio, Cong ty)",   "DEV PROFILE"),
        ("git repo <user/repo>","Soi chi tiet kho ma nguon (Stars, Forks, Issues, Branch)",  "REPOSITORY"),
        ("git release <user/repo>", "Kiem tra phien ban phat hanh (Release) moi nhat va link tai", "RELEASE"),
    ]
)
register_card("github", _GITHUB_SCHEMA)
register_card("git", _GITHUB_SCHEMA)
register_card("gh", _GITHUB_SCHEMA)

# ────────────── IMAGE PROCESSING STUDIO (IMG) ──────────────
_IMG_SCHEMA = CardSchema(
    title="IMAGE PROCESSING STUDIO & UTILITIES",
    sub="Bo cong cu xu ly anh, tao ma QR Liquid Glass va trich xuat Avatar HD",
    accent=(236, 72, 153),  # Hong Neon Studio
    logo_fn=MC.draw_info_logo_hires,
    tip="Cac lenh resize, blur, gray, invert, circle deu ho tro reply anh, dinh kem hoac link!",
    items=[
        ("img",                 "Mo bang huong dan Liquid Glass Studio nay",                 "HELP"),
        ("img qr <link/chu>",   "Tao ma QR Liquid Glass HD quet tuc thi bang camera",       "QR CODE"),
        ("img avt [@user]",     "Trich xuat Avatar full HD 2048px cua nguoi dung",           "AVATAR HD"),
        ("img banner [@user]",  "Trich xuat Profile Banner hoac Server Banner chat luong cao", "BANNER HD"),
        ("img resize <WxH>",    "Doi kich thuoc anh theo pixel mong muon (VD: 800x600)",     "RESIZE"),
        ("img blur [1-30]",     "Lam mo anh nghe thuat bang Gaussian Blur",                  "BLUR"),
        ("img gray",            "Chuyen anh sang den trang nghe thuat (Grayscale)",          "GRAYSCALE"),
        ("img invert",          "Dao nguoc bang mau sac anh am ban (Negative)",              "INVERT"),
        ("img circle",          "Cat anh hinh tron trong suot bo vien neon",                 "CIRCLE CROP"),
        ("img info",            "Xem thong so ky thuat chi tiet cua anh (kich thuoc, format)", "IMAGE INFO"),
    ]
)
register_card("img", _IMG_SCHEMA)
register_card("image", _IMG_SCHEMA)
register_card("anh", _IMG_SCHEMA)

# ────────────── TEMP MAIL 10 PHUT (MAIL) ──────────────
_MAIL_SCHEMA = CardSchema(
    title="TEMP MAIL 10 MINUTES & OTP DETECTOR",
    sub="Hop thu ao dung mot lan nhan ma OTP va email xac thuc tu dong",
    accent=(16, 185, 129),  # Xanh la cong nghe bao mat
    logo_fn=MC.draw_genesis_logo_hires,
    tip="Dung 'mail gen' de tao email, sau do go 'mail inbox' de xem thu va ma OTP!",
    items=[
        ("mail",                "Mo bang huong dan Liquid Glass Hop Thu Ao nay",             "HELP"),
        ("mail gen",            "Tao ngay mot dia chi email ao 10 phut moi de nhan OTP",     "GEN EMAIL"),
        ("mail inbox",          "Kiem tra hop thu den va tu dong quet ma xac thuc OTP",      "INBOX"),
        ("mail read <id>",      "Doc toan bo noi dung chi tiet cua mot buc thu",             "READ"),
        ("mail current",        "Xem lai dia chi email ao dang hoat dong cua ban",           "STATUS"),
    ]
)
register_card("mail", _MAIL_SCHEMA)
register_card("tempmail", _MAIL_SCHEMA)
register_card("hopthu", _MAIL_SCHEMA)

# ────────────── SHORTLINK & UNSHORTEN (SHORT) ──────────────
_SHORT_SCHEMA = CardSchema(
    title="URL SHORTENER & UNSHORTEN RADAR",
    sub="Rut gon duong link sieu toc & giai ma link an chong IP logger",
    accent=(14, 165, 233),  # Xanh cong nghe link
    logo_fn=MC.draw_genesis_logo_hires,
    tip="Dung 'short <link>' de rut gon hoac 'unshort <link>' de soi dich den thuc su!",
    items=[
        ("short",               "Mo bang huong dan Rut Gon & Giai Ma Link nay",              "HELP"),
        ("short <link_dai>",    "Rut gon duong link dai thanh link ngan sieu toc",           "SHORTEN"),
        ("unshort <link_ngan>", "Giai ma dich den thuc su, phat hien IP logger / scam",      "UNSHORTEN"),
    ]
)
register_card("short", _SHORT_SCHEMA)
register_card("shortlink", _SHORT_SCHEMA)
register_card("rutgon", _SHORT_SCHEMA)
register_card("unshort", _SHORT_SCHEMA)
register_card("checklink", _SHORT_SCHEMA)
register_card("giaimalink", _SHORT_SCHEMA)

# ────────────── CLOUD LINUX VPS (VPS) ──────────────
_VPS_SCHEMA = CardSchema(
    title="CLOUD LINUX VPS & WEB PORTAL",
    sub="May ao Linux ca nhan mien phi ket noi qua Web Portal bo goc sieu dep",
    accent=(14, 165, 233),  # Cyan / Cyber Blue
    logo_fn=getattr(MC, "draw_vps_logo_hires", None),
    tip="Moi tai khoan tao toi da 1 VPS. Dung 'vps create' de tao & nhan link kem ma PIN!",
    items=[
        ("vps",                 "Mo bang huong dan anh Liquid Glass Cloud VPS nay",          "HELP"),
        ("vps create <ten>",    "Khoi tao may ao Linux Ubuntu ca nhan (ten tuy chon)",      "CREATE"),
        ("vps list",            "Lay lai Link Web Portal va xem lai Ma PIN bao mat",         "LIST / PIN"),
        ("vps delete",          "Huy may ao hien tai de giai phong hoac tao may moi",       "DESTROY"),
    ]
)
register_card("vps", _VPS_SCHEMA)
register_card("linux", _VPS_SCHEMA)
register_card("terminal", _VPS_SCHEMA)
register_card("shell", _VPS_SCHEMA)

# ────────────── WAR & VAR (WAR SPAM SO & POLL) ──────────────
_WAR_SCHEMA = CardSchema(
    title="WAR DISCORD & VAR ARENA",
    sub="Auto spam so chui & spam poll tag lien thanh trung phat ke pha hoai",
    accent=(239, 68, 68),  # Crimson Neon
    logo_fn=getattr(MC, "draw_war_logo_hires", None),
    tip="Gõ 'war off' hoac 'var stop' bat cu luc nao de dung ngay lap tuc!",
    items=[
        ("war",                             "Mo bang huong dan anh Liquid Glass War nay",         "HELP"),
        ("war reo @tag [delay] [so_luong]", "Spam tag nguoi do kem so chui doc lien thanh",       "REO WAR"),
        ("war poll @tag [delay] [so_luong]","Spam tao khao sat Poll tag nguoi do lien tuc",       "POLL WAR"),
        ("war off",                         "Dung toan bo cac tien trinh war dang chay tai kenh", "STOP ALL"),
    ]
)
register_card("war", _WAR_SCHEMA)
register_card("var", _WAR_SCHEMA)



