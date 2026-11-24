from core.registry import registry, SubModule
from modules.userbot.routes import userbot_bp
from modules.userbot.worker import userbot_worker

def init_userbot_submodule(app):
    """Tự động khởi động lại các bot đã được kích hoạt trước đó khi server Flask chạy"""
    userbot_worker.auto_start_saved_bots()

def cleanup_userbot_submodule():
    """Dọn dẹp và dừng an toàn tất cả các bot khi tắt server"""
    userbot_worker.shutdown_all()

userbot_submodule = SubModule(
    key='userbot_master',
    category_key='userbot',
    title="Discord UserBot Master",
    blueprint=userbot_bp,
    worker=userbot_worker,
    init_handler=init_userbot_submodule,
    cleanup_handler=cleanup_userbot_submodule
)

registry.register_module(userbot_submodule)

__all__ = ['userbot_bp', 'userbot_worker', 'userbot_submodule']
