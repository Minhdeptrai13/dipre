import os
import json

EFFECTS_FILE = os.path.join(os.path.dirname(__file__), 'discord_effects_data.json')
_EFFECTS_CACHE = None

def load_effects():
    global _EFFECTS_CACHE
    if _EFFECTS_CACHE is not None:
        return _EFFECTS_CACHE
    if os.path.exists(EFFECTS_FILE):
        try:
            with open(EFFECTS_FILE, 'r', encoding='utf-8') as f:
                _EFFECTS_CACHE = json.load(f)
                return _EFFECTS_CACHE
        except Exception:
            pass
    _EFFECTS_CACHE = {}
    return _EFFECTS_CACHE

def resolve_profile_effect(effect_id: str) -> dict:
    """Chuyển đổi SKU ID / Effect ID của Discord thành URL APNG động thực tế 1:1"""
    if not effect_id:
        return None
        
    eff_id_str = str(effect_id).strip()
    effects = load_effects()
    
    if eff_id_str in effects:
        item = effects[eff_id_str]
        return {
            'id': eff_id_str,
            'title': item.get('title', 'Discord Profile Effect'),
            'intro': item.get('intro') or item.get('loop'),
            'loop': item.get('loop') or item.get('intro'),
            'reduced': item.get('reduced')
        }
        
    for k, v in effects.items():
        if eff_id_str.lower() in v.get('title', '').lower():
            return {
                'id': k,
                'title': v.get('title'),
                'intro': v.get('intro') or v.get('loop'),
                'loop': v.get('loop') or v.get('intro'),
                'reduced': v.get('reduced')
            }
            
    if eff_id_str.startswith('http'):
        return {
            'id': 'custom',
            'title': 'Custom Effect',
            'intro': eff_id_str,
            'loop': eff_id_str,
            'reduced': eff_id_str
        }

    return None
