import discord
from discord.ext import commands
import asyncio
from typing import Union

# Danh sách emoji phong phú để random react
EMOJI_POOL = [
    "🔥", "⚡", "🚀", "👑", "💎", "✨", "🎯", "🍀", "💫", "⚔️",
    "🛡️", "🔮", "💯", "🦾", "👾", "🐉", "🦅", "🦁", "🦈", "🪐",
    "⭐", "🌟", "🎉", "🏆", "🌀", "🧿", "🪄", "🖤", "🤍", "💥"
]

async def autorep(message: discord.Message, content: str = None, file: discord.File = None, files: list = None, embed: discord.Embed = None, auto_delete_delay: int = None, auto_react: bool = True) -> discord.Message:
    """
    Trả lời (reply) trực tiếp vào tin nhắn lệnh của người dùng,
    đồng thời tự động thả reaction ngẫu nhiên (nếu auto_react=True),
    và tự động xóa tin nhắn sau auto_delete_delay giây (nếu được chỉ định).
    """
    kwargs = {}
    if content is not None:
        kwargs["content"] = content
    if file is not None:
        kwargs["file"] = file
    if files is not None:
        kwargs["files"] = files
    if embed is not None:
        kwargs["embed"] = embed

    # 1. Tha icon NGAY (background, khong cho) + reply song song.
    if auto_react:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(autoreact(message))
        except RuntimeError:
            pass

    # 2. Reply tin nhan
    try:
        sent_msg = await message.reply(**kwargs, mention_author=False)
    except Exception:
        # Neu khong reply duoc (tin nhan goc bi xoa hoac thieu quyen), gui thang vao channel
        sent_msg = await message.channel.send(**kwargs)

    # 3. Nếu có cài đặt auto_delete_delay thì hẹn giờ tự động xóa tin nhắn bot
    if auto_delete_delay and auto_delete_delay > 0:
        autodelet(sent_msg, delay=auto_delete_delay)

    return sent_msg


async def autoreact(message: discord.Message) -> bool:
    """Thả reaction ngẫu nhiên vào tin nhắn lệnh (chỉ thực hiện khi có phản hồi/rep)."""
    import random
    emojis = EMOJI_POOL.copy()
    if message.guild:
        custom_emojis = [e for e in message.guild.emojis if e.available]
        if custom_emojis:
            emojis.extend(custom_emojis)

    choice = random.choice(emojis)
    try:
        await asyncio.sleep(0.8)
        await message.add_reaction(choice)
        return True
    except Exception:
        return False


def autodelet(message: discord.Message, delay: int = 30):
    """
    Tự động xóa tin nhắn của bot sau delay giây (mặc định 30s).
    Chạy background non-blocking, an toàn tuyệt đối.
    """
    if not message:
        return

    async def _cleanup():
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        except Exception:
            pass

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_cleanup())
    except RuntimeError:
        pass


class AutoReplyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(AutoReplyCog(bot))
