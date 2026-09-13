# DIPRE Studio (Discord Rich Presence & Automation Suite)

DIPRE Studio là nền tảng quản lý và tùy biến Discord Rich Presence (RPC), tự động hóa Discord Quest, đồng bộ Lyric trạng thái và quản lý tài khoản Discord tập trung với giao diện Web Cyber-Dark sang trọng.

---

## Cấu Trúc Dự Án & Chức Năng Từng File

```text
DiscordRPG/
├── main.py
├── requirements.txt
├── .env / .env.example
├── supabase_schema.sql
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── logger.py
│   ├── registry.py
│   ├── security.py
│   └── supabase_client.py
├── modules/
│   ├── account/
│   │   ├── discord_effects.py
│   │   ├── discord_effects_data.json
│   │   ├── routes.py
│   │   └── services.py
│   ├── auth/
│   │   ├── helpers.py
│   │   └── routes.py
│   ├── captcha/
│   │   ├── generators.py
│   │   └── routes.py
│   ├── lyrics/
│   │   ├── routes.py
│   │   └── worker.py
│   ├── quest/
│   │   ├── helpers.py
│   │   ├── routes.py
│   │   └── runner.py
│   ├── rpc/
│   │   ├── helpers.py
│   │   ├── routes.py
│   │   └── worker.py
│   ├── template/
│   │   └── routes.py
│   └── voice/
│       └── routes.py
├── static/
│   ├── css/
│   │   ├── style.css
│   │   └── theme_hub.css
│   ├── js/
│   │   ├── app.js
│   │   └── theme_hub.js
│   ├── img/
│   └── uploads/
└── templates/
    ├── index.html
    ├── login.html
    └── oauth_mock.html
```

---

### 1. Thư mục gốc (Root)
- **`main.py`**: Điểm khởi chạy chính của ứng dụng Flask. Nơi khởi tạo cấu hình, đăng ký toàn bộ Blueprints, quản lý session và start server.
- **`requirements.txt`**: Danh sách thư viện Python cần thiết (`Flask`, `requests`, `supabase`, `cryptography`, `pillow`, v.v.).
- **`.env`**: File biến môi trường chứa cấu hình bí mật như `FLASK_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, Turnstile Secret Key.
- **`.env.example`**: Mẫu biến môi trường mẫu cho người dùng mới cấu hình.
- **`supabase_schema.sql`**: Script DDL thiết lập cấu trúc bảng database trên Supabase (`profiles`, `discord_accounts`, `rpc_templates`, `user_configs`).
- **`discord_rpg.db` / `app.db`**: File cơ sở dữ liệu SQLite cục bộ (chế độ local fallback).

---

### 2. Thư mục `core/` (Hệ thống cốt lõi)
- **`core/config.py`**: Định nghĩa cấu hình tập trung (load biến môi trường, đường dẫn tĩnh, thiết lập bảo mật).
- **`core/database.py`**: Quản lý kết nối SQLite, khởi tạo schema cục bộ khi không dùng cloud database.
- **`core/supabase_client.py`**: Khởi tạo kết nối Supabase Client và cung cấp các hàm thao tác đồng bộ dữ liệu tài khoản, cấu hình và templates lên đám mây.
- **`core/security.py`**: Mã hóa/giải mã AES token Discord, băm mật khẩu người dùng (`bcrypt`/`pbkdf2`), kiểm tra tính hợp lệ của token.
- **`core/logger.py`**: Hệ thống logging chuẩn hóa, ghi log các sự kiện RPC, Quest và lỗi hệ thống theo màu sắc và timestamp.
- **`core/registry.py`**: Registry quản lý vòng đời của các worker thread chạy nền (RPC Worker, Auto Quest Worker, Lyric Worker) theo từng User ID.

---

### 3. Thư mục `modules/` (Các phân hệ tính năng)

#### `modules/account/` (Quản lý tài khoản Discord)
- **`routes.py`**: API endpoints thêm token, sửa, xóa, lấy danh sách tài khoản Discord, chuyển đổi tài khoản active, nhận HypeSquad House.
- **`services.py`**: Tương tác trực tiếp với Discord API v9/v10 để lấy thông tin hồ sơ, avatar, banner, Nitro badge, và danh sách Nitro profile effects.
- **`discord_effects.py`**: Logic phân tích và xử lý hiệu ứng hồ sơ Nitro (Profile Effect / Avatar Decoration).
- **`discord_effects_data.json`**: Dữ liệu mẫu chứa thông số asset và animation các hiệu ứng Nitro chính thức của Discord.

#### `modules/auth/` (Xác thực người dùng)
- **`routes.py`**: Các tuyến xử lý đăng ký, đăng nhập tài khoản hệ thống, xác thực Turnstile CAPTCHA và đăng xuất.
- **`helpers.py`**: Middleware kiểm tra đăng nhập (`login_required`), session validator và helper xác minh Cloudflare Turnstile token.

#### `modules/captcha/` (Bảo mật Captcha)
- **`generators.py`**: Tạo ảnh CAPTCHA toán học/ký tự ngẫu nhiên cho chế độ offline/local.
- **`routes.py`**: Tuyến cung cấp ảnh captcha và kiểm tra chuỗi nhập từ người dùng.

#### `modules/lyrics/` (Đồng bộ Lời bài hát vào Status)
- **`routes.py`**: API tìm kiếm bài hát, tải metadata/lời bài hát từ ZingMP3, Spotify hoặc LRCLIB.
- **`worker.py`**: Luồng chạy nền đồng bộ từng câu lời bài hát theo thời gian thực (realtime) vào Custom Status của tài khoản Discord.

#### `modules/quest/` (Tự động cày nhiệm vụ Discord Quest)
- **`routes.py`**: Tuyến lấy danh sách nhiệm vụ đang mở trên Discord, bắt đầu chạy auto quest, dừng tiến trình và lấy báo cáo.
- **`runner.py`**: Engine cày nhiệm vụ tự động: hỗ trợ chế độ cày liên tục không chờ, tự động dừng khi hết nhiệm vụ, lưu kết quả tổng kết phục vụ thông báo qua đêm.
- **`helpers.py`**: Hàm giả lập heartbeat ứng dụng, video xem stream và tương tác Discord Gateway để hoàn thành nhiệm vụ hợp lệ.

#### `modules/rpc/` (Discord Rich Presence Engine)
- **`routes.py`**: Tuyến khởi động, cập nhật, tạm dừng Rich Presence, upload ảnh/GIF asset bot, lưu cấu hình RPC cá nhân.
- **`worker.py`**: Worker kết nối Discord Gateway / IPC, duy trì trạng thái hiện diện (hoạt động, nút bấm, thời gian, ảnh lớn, ảnh nhỏ).
- **`helpers.py`**: Chuẩn hóa payload Rich Presence, kiểm tra URL hình ảnh và định dạng timestamp.

#### `modules/template/` (Diễn đàn & Mẫu Custom Theme RPC)
- **`routes.py`**: API diễn đàn cộng đồng: tạo template RPC mới, duyệt danh sách mẫu chia sẻ công khai, lấy chi tiết template hoặc áp dụng ngay vào tài khoản.

#### `modules/voice/` (Treo phòng thoại AFK)
- **`routes.py`**: API cho phép tài khoản tham gia và treo voice channel 24/7 (mute/deaf ảo) trên Discord.

---

### 4. Thư mục `static/` (Tài nguyên giao diện)
- **`css/style.css`**: Hệ thống style giao diện chính: bảng màu Cyber-Dark (Đen - Trắng - Xanh biển), layout responsive, hiệu ứng kính mờ (Glassmorphism), mô phỏng thẻ Discord 1:1.
- **`css/theme_hub.css`**: Style riêng cho Trung tâm Giao diện (Theme Hub), Diễn đàn cộng đồng, bộ chọn Bot con và trình xem trước RPC.
- **`js/app.js`**: Logic điều khiển Dashboard: quản lý token realtime, kích hoạt RPC, điều khiển nhạc lyrics, cày Auto Quest, hiển thị popup thông báo tổng kết qua đêm.
- **`js/theme_hub.js`**: Logic xử lý 3 tab diễn đàn (Khám phá, Mẫu của bạn, Tạo mẫu), xem trước Live Preview RPC, chọn Preset GIF và chia sẻ mẫu lên cộng đồng.
- **`uploads/`**: Thư mục lưu trữ hình ảnh hoặc GIF bot do người dùng tải lên từ giao diện.

---

### 5. Thư mục `templates/` (Giao diện HTML)
- **`index.html`**: Trang quản trị chính (Dashboard Command Center, Theme Hub, Lyrics, Quests, Quản lý Token).
- **`login.html`**: Trang Landing & Cổng Đăng nhập/Đăng ký bảo mật với Cloudflare Turnstile, hiển thị thẻ Discord động thực tế.
- **`oauth_mock.html`**: Giao diện mô phỏng luồng ủy quyền Discord / Google OAuth.

---

## Hướng Dẫn Cài Đặt & Khởi Chạy

1. **Cài đặt môi trường:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Cấu hình file `.env`:**
   Tạo bản sao từ `.env.example` và điền thông tin Supabase hoặc cấu hình cục bộ:
   ```env
   PORT=5000
   FLASK_SECRET_KEY=your_secret_key_here
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your_supabase_anon_or_service_key
   ```

3. **Chạy ứng dụng:**
   ```bash
   python main.py
   ```
   Truy cập vào trình duyệt tại địa chỉ: `http://localhost:5000`
