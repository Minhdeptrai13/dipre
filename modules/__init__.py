"""
Package chứa toàn bộ các Modules Chức Năng của DiscordRPG.
Khi import package này, tất cả các SubModules sẽ tự động đăng ký vào Core Registry.
"""
from core.registry import registry

registry.register_category('account', 'Account & Tokens Manager', 'Quản lý tài khoản mạng xã hội và đa token Discord chuẩn 1:1')
registry.register_category('rpc', 'Discord Rich Presence', 'Tùy biến trạng thái hoạt động Rich Presence Discord siêu cấp')
registry.register_category('status', 'Discord Status & Lyric', 'Tùy chỉnh Custom Status và đồng bộ Lyric Karaoke từng câu hát')
registry.register_category('voice', 'Discord Voice 24/7 & Audio', 'Treo voice phòng đàm thoại 24/7 và tiện ích âm thanh')
registry.register_category('script', 'Automation Scripts', 'Tự động hóa nhiệm vụ Quests và các script Discord tiện ích')
registry.register_category('userbot', 'UserBot Assistant Engine', 'Hệ thống Discord UserBot tự động hóa toàn diện với hơn 30+ module cogs')
registry.register_category('ai', 'Ask DIPRE', 'Trợ lý AI đa bậc DIPRE Flash & DIPRE Pro với RAG nội bộ và Rate-Safe Guard')

import modules.auth
import modules.account
import modules.captcha
import modules.rpc
import modules.quest
import modules.sniper
import modules.lyrics
import modules.voice
import modules.template
import modules.userbot
import modules.ai

__all__ = ['registry']
