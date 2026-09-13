import requests

def fetch_discord_profile(token: str, target_user_id: str = None):
    """Lấy toàn bộ thông tin profile Discord chính chủ 100%: Avatar, Avatar Decoration APNG, Banner, Badges, Username, Profile Effect"""
    token = token.strip().strip('"').strip("'")
    auth_header = token if token.startswith('Bot ') else token
    headers = {
        'Authorization': auth_header,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    
    # Nếu có target_user_id, lấy thông tin của user đó qua profile endpoint
    target_id = str(target_user_id).strip() if target_user_id else None
    
    # Lấy thông tin cơ bản
    if target_id and target_id != '@me':
        url_user = f'https://discord.com/api/v9/users/{target_id}'
    else:
        url_user = 'https://discord.com/api/v9/users/@me'
        
    res = requests.get(url_user, headers=headers, timeout=8)
    if res.status_code != 200:
        return None
    data = res.json()
    d_id = str(data.get('id', ''))
    username = data.get('global_name') or data.get('username') or 'Discord User'
    avatar_hash = data.get('avatar')
    
    if avatar_hash:
        ext = 'gif' if avatar_hash.startswith('a_') else 'png'
        avatar_url = f"https://cdn.discordapp.com/avatars/{d_id}/{avatar_hash}.{ext}?size=256"
    else:
        avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
    
    decor_data = data.get('avatar_decoration_data')
    decor_url = ''
    if decor_data and decor_data.get('asset'):
        asset_id = decor_data['asset']
        decor_url = f"https://cdn.discordapp.com/avatar-decoration-presets/{asset_id}.png?size=256&passthrough=true"

    banner_hash = data.get('banner')
    banner_url = ''
    if banner_hash:
        b_ext = 'gif' if banner_hash.startswith('a_') else 'png'
        banner_url = f"https://cdn.discordapp.com/banners/{d_id}/{banner_hash}.{b_ext}?size=600"

    badges = []
    flags = data.get('flags', 0) or data.get('public_flags', 0)
    if flags & (1 << 6):
        badges.append({'name': 'HypeSquad Bravery', 'icon': 'https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/svg/1f7e3.svg'})
    if flags & (1 << 7):
        badges.append({'name': 'HypeSquad Brilliance', 'icon': 'https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/svg/1f7e0.svg'})
    if flags & (1 << 8):
        badges.append({'name': 'HypeSquad Balance', 'icon': 'https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/svg/1f7e2.svg'})
    if flags & (1 << 22):
        badges.append({'name': 'Active Developer', 'icon': 'https://cdn.discordapp.com/badge-icons/6bdc42827b30f498e4a0713f64455d80.png?size=64'})

    profile_effect = ''
    bio = data.get('bio', '')
    custom_status = {}
    
    try:
        p_res = requests.get(f'https://discord.com/api/v9/users/{d_id}/profile?with_mutual_guilds=false', headers=headers, timeout=6)
        if p_res.status_code == 200:
            p_data = p_res.json()
            u_prof = p_data.get('user_profile', {})
            pfx = u_prof.get('profile_effect') or p_data.get('profile_effect')
            if pfx and isinstance(pfx, dict) and pfx.get('id'):
                profile_effect = str(pfx['id'])
            elif pfx:
                profile_effect = str(pfx)
                
            if u_prof.get('bio'):
                bio = u_prof.get('bio')
                
            if not decor_url and u_prof.get('avatar_decoration_data'):
                u_asset = u_prof['avatar_decoration_data'].get('asset')
                if u_asset:
                    decor_url = f"https://cdn.discordapp.com/avatar-decoration-presets/{u_asset}.png?size=256&passthrough=true"
                    
            for b in p_data.get('badges', []):
                b_icon = b.get('icon')
                if b_icon:
                    badges.append({
                        'id': b.get('id'),
                        'name': b.get('description', 'Badge'),
                        'icon': f"https://cdn.discordapp.com/badge-icons/{b_icon}.png?size=64"
                    })
    except Exception:
        pass

    return {
        'id': d_id,
        'username': username,
        'tag': data.get('username', ''),
        'avatar': avatar_url,
        'decoration': decor_url,
        'banner': banner_url,
        'badges': badges,
        'profile_effect': profile_effect,
        'bio': bio
    }
