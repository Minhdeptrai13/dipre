"""
Package chứa toàn bộ các Modules Chức Năng của DiscordRPG.
Khi import package này, tất cả các SubModules sẽ tự động đăng ký vào Core Registry.
"""
from core.registry import registry

# Nạp các Mục Lớn vào Registry
registry.register_category('account', 'Account & Tokens Manager', 'Quản lý tài khoản mạng xã hội và đa token Discord chuẩn 1:1')
registry.register_category('rpc', 'Discord Rich Presence', 'Tùy biến trạng thái hoạt động Rich Presence Discord siêu cấp')
registry.register_category('status', 'Discord Status & Lyric', 'Tùy chỉnh Custom Status và đồng bộ Lyric Karaoke từng câu hát')
registry.register_category('voice', 'Discord Voice 24/7 & Audio', 'Treo voice phòng đàm thoại 24/7 và tiện ích âm thanh')
registry.register_category('script', 'Automation Scripts', 'Tự động hóa nhiệm vụ Quests và các script Discord tiện ích')

# Import các routes/modules để kích hoạt khai báo submodule vào các mục lớn
import modules.auth
import modules.account
import modules.captcha
import modules.rpc
import modules.quest
import modules.lyrics
import modules.voice

__all__ = ['registry']
