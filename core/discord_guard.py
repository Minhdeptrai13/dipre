import random
import threading
import time
import hashlib
from typing import Dict, Any, Tuple

from core.logger import log_event


class DiscordAntiBanGuard:
    """
    Lớp bảo vệ tài khoản Discord (Anti-Ban & Smart Rate-Limit Circuit Breaker):
    - Giới hạn tốc độ request theo từng Token (Sliding Window + Min Spacing).
    - Tự động chèn độ trễ ngẫu nhiên giống người thật (Humanized Jitter).
    - Tự động ngắt mạch (Circuit Breaker) khi gặp HTTP 429 (Retry-After), 401, 403 hoặc yêu cầu Captcha/Verify.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.enabled: bool = True
        self._state: Dict[str, Dict[str, Any]] = {}
        self.max_writes_per_min: int = 16
        self.min_spacing_sec: float = 0.4

    @staticmethod
    def _tok_key(token: str) -> str:
        t = (token or '').strip()
        if not t:
            return 'empty'
        return hashlib.sha256(t.encode('utf-8')).hexdigest()[:16]

    def _get_bucket(self, key: str) -> Dict[str, Any]:
        if key not in self._state:
            self._state[key] = {
                'timestamps': [],
                'last_call': 0.0,
                'cooldown_until': 0.0,
                'consecutive_429': 0,
                'blocked_count': 0,
                'flagged_reason': '',
            }
        return self._state[key]

    def set_enabled(self, enabled: bool) -> bool:
        with self._lock:
            self.enabled = bool(enabled)
        log_event(
            f"🛡️ [Anti-Ban Shield] Đã {'BẬT' if self.enabled else 'TẮT'} lớp bảo vệ Rate-Limit tài khoản.",
            'success' if self.enabled else 'warning'
        )
        return self.enabled

    def can_call(self, token: str, action: str = 'write') -> Tuple[bool, str, float]:
        """
        Kiểm tra xem token có được phép gọi Discord API lúc này không.
        Trả về (allowed, reason, wait_seconds).
        """
        now = time.time()
        key = self._tok_key(token)
        with self._lock:
            b = self._get_bucket(key)

            # Luôn chặn nếu đang trong thời gian phạt 429 / khóa bảo vệ
            if now < b['cooldown_until']:
                remain = round(b['cooldown_until'] - now, 1)
                b['blocked_count'] += 1
                reason = b['flagged_reason'] or f'Đang nghỉ bảo vệ Rate-Limit (còn {remain}s)'
                return False, reason, remain

            if not self.enabled:
                b['last_call'] = now
                return True, '', 0.0

            # Lọc cửa sổ 60s
            b['timestamps'] = [ts for ts in b['timestamps'] if now - ts < 60.0]

            limit = self.max_writes_per_min if action in ('write', 'redeem', 'ack', 'react') else 30
            if len(b['timestamps']) >= limit:
                oldest = b['timestamps'][0]
                wait = max(1.0, round(60.0 - (now - oldest), 1))
                b['blocked_count'] += 1
                return False, f'Anti-Ban: Chạm ngưỡng an toàn {limit} req/phút (chờ {wait}s)', wait

            elapsed = now - b['last_call']
            if elapsed < self.min_spacing_sec:
                wait = round(self.min_spacing_sec - elapsed, 2)
                return False, f'Anti-Ban: Giãn cách tối thiểu ({wait}s)', wait

            b['last_call'] = now
            b['timestamps'].append(now)
            return True, '', 0.0

    def wait_if_needed(self, token: str, action: str = 'write') -> Tuple[bool, str]:
        """Tự động sleep giãn cách nếu an toàn, hoặc trả False nếu đang bị Circuit Breaker khóa."""
        allowed, reason, wait_s = self.can_call(token, action=action)
        if allowed:
            if self.enabled:
                time.sleep(random.uniform(0.18, 0.65))
            return True, ''
        if wait_s <= 2.5 and 'Chạm ngưỡng' not in reason and 'nghỉ bảo vệ' not in reason:
            time.sleep(wait_s + random.uniform(0.1, 0.35))
            allowed2, reason2, _ = self.can_call(token, action=action)
            return allowed2, reason2
        return False, reason

    def record_response(self, token: str, status_code: int, headers=None, body_text: str = '') -> None:
        """Ghi nhận phản hồi từ Discord API và tự động bật Circuit Breaker nếu có dấu hiệu nguy hiểm."""
        now = time.time()
        key = self._tok_key(token)
        low_body = (body_text or '').lower()

        with self._lock:
            b = self._get_bucket(key)

            if status_code == 429:
                retry_after = 15.0
                try:
                    if headers and headers.get('Retry-After'):
                        retry_after = float(headers.get('Retry-After'))
                except Exception:
                    pass
                b['consecutive_429'] += 1
                backoff = min(300.0, retry_after + random.uniform(2.5, 6.0) * b['consecutive_429'])
                b['cooldown_until'] = max(b['cooldown_until'], now + backoff)
                b['flagged_reason'] = f'Discord Rate Limit 429 — tự động tạm nghỉ {int(backoff)}s để chống khóa acc'
                log_event(f'🛡️ [Anti-Ban 429] {b["flagged_reason"]}', 'warning')
                return

            if status_code in (401, 403) or any(k in low_body for k in ('captcha', 'verify', 'unauthorized', 'account_disabled')):
                pause = 180.0
                b['cooldown_until'] = max(b['cooldown_until'], now + pause)
                b['flagged_reason'] = f'Discord trả HTTP {status_code} (nghi vấn bảo mật/Captcha) — tạm ngắt 180s bảo vệ acc'
                log_event(f'🚨 [Anti-Ban Circuit Breaker] {b["flagged_reason"]}', 'error')
                return

            if 200 <= status_code < 300:
                b['consecutive_429'] = 0
                if now >= b['cooldown_until']:
                    b['flagged_reason'] = ''

    def get_status(self, token: str = '') -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            if token:
                b = self._get_bucket(self._tok_key(token))
                remain = max(0, int(b['cooldown_until'] - now))
                reqs_1m = len([ts for ts in b['timestamps'] if now - ts < 60.0])
                return {
                    'enabled': self.enabled,
                    'is_cooling_down': remain > 0,
                    'cooldown_remaining': remain,
                    'requests_1m': reqs_1m,
                    'max_writes_per_min': self.max_writes_per_min,
                    'blocked_count': b['blocked_count'],
                    'flagged_reason': b['flagged_reason'],
                }
            max_remain = 0
            total_blocked = 0
            total_reqs = 0
            last_flag = ''
            for b in self._state.values():
                rem = max(0, int(b['cooldown_until'] - now))
                if rem > max_remain:
                    max_remain = rem
                    last_flag = b['flagged_reason']
                total_blocked += b['blocked_count']
                total_reqs += len([ts for ts in b['timestamps'] if now - ts < 60.0])
            return {
                'enabled': self.enabled,
                'is_cooling_down': max_remain > 0,
                'cooldown_remaining': max_remain,
                'requests_1m': total_reqs,
                'max_writes_per_min': self.max_writes_per_min,
                'blocked_count': total_blocked,
                'flagged_reason': last_flag,
            }


discord_guard = DiscordAntiBanGuard()
