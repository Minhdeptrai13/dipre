import discord
from discord.ext import commands
import asyncio

def autodelet(message: discord.Message, delay: int = 30):
    """
    Tự động xóa tin nhắn bot sau một khoảng thời gian (mặc định 30 giây).
    Dễ dàng import ở bất kỳ đâu: from utils.autodelet import autodelet
    Ví dụ:
        msg = await autorep(message, file=img)
        autodelet(msg, delay=30)
    """
    if not message:
        return

    async def _runner():
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        except Exception:
            pass

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_runner())
    except RuntimeError:
        pass


class AutoDeleteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(AutoDeleteCog(bot))
