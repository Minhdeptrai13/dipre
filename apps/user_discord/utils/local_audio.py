import subprocess
import os
import sys
import logging

logger = logging.getLogger("LocalAudioPlayer")

class LocalAudioPlayer:
    _instance = None

    def __init__(self):
        self._proc = None
        self._current_title = ""

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def play(self, audio_source: str, title: str = "Audio") -> bool:
        """Phát âm thanh stream hoặc file trực tiếp qua FFplay ngầm (Bypass DAVE E2EE 100%)."""
        self.stop()

        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel", "quiet",
            audio_source
        ]

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            self._current_title = title
            return True
        except Exception as e:
            logger.error(f"[LOCAL AUDIO ERR] {e}")
            self._proc = None
            return False

    def stop(self) -> bool:
        """Dừng phát âm thanh ngay lập tức."""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.kill()
            except Exception:
                pass
            self._proc = None
            self._current_title = ""
            return True
        return False

    def is_playing(self) -> bool:
        if self._proc:
            return self._proc.poll() is None
        return False

    def get_title(self) -> str:
        return self._current_title


async def setup(bot):
    """Extension loader hook cho main.py"""
    pass
