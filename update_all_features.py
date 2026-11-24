import os

index_path = os.path.abspath('Dipre/templates/index.html')
with open(index_path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update Abyss Banner class in tab-home
if 'dashboard-hero-banner abyss-banner-active' not in text:
    text = text.replace(
        '<div class="dashboard-hero-banner">',
        '<div class="dashboard-hero-banner abyss-banner-active">',
        1
    )
    print('Added abyss-banner-active class to tab-home')

# 2. Add IDE Showcase cutout banner in tab-rpc
ide_banner_html = '''<section class="tab-panel" id="tab-rpc">
        <!-- THEME RPC USER SHOWCASE BANNER -->
        <div class="rpc-custom-art-banner" style="width:100%; height:135px; border-radius:12px; margin-bottom:1.5rem; border:1px solid var(--border); overflow:hidden; position:relative; display:flex; align-items:center; justify-content:space-between; padding:0 1.5rem; background: linear-gradient(90deg, rgba(7, 9, 14, 0.95) 0%, rgba(14, 19, 31, 0.8) 50%, rgba(2, 132, 199, 0.2) 100%), url('{{ url_for(\\'static\\', filename=\\'img/mockups/theme_rpc_showcase_cards.png\\') }}') no-repeat right center / contain;">
          <div>
            <div style="font-family:'Outfit',sans-serif; font-size:1.4rem; font-weight:800; color:#FFFFFF; letter-spacing:-0.01em;">INTELLIJ &amp; IDE RICH PRESENCE MATRIX</div>
            <div style="font-size:0.82rem; color:#BAE6FD; font-weight:600;">Tuỳ biến hiển thị đang code, làm game, nghe nhạc hoặc ứng dụng thời gian thực</div>
          </div>
          <div style="background:rgba(2, 132, 199, 0.3); border:1px solid #38BDF8; padding:5px 12px; border-radius:999px; font-size:0.72rem; font-weight:700; color:#FFFFFF;">
            LIVE PREVIEW READY
          </div>
        </div>'''

if 'rpc-custom-art-banner' not in text:
    text = text.replace('<section class="tab-panel" id="tab-rpc">', ide_banner_html, 1)
    print('Injected IDE banner into tab-rpc')

# 3. Add Nitro Banner in tab-script-coming
nitro_banner_html = '''<!-- NITRO SNIPER OFFICIAL BANNER -->
        <div class="nitro-custom-banner" style="width:100%; height:140px; border-radius:12px; margin-bottom:1.25rem; border:1px solid var(--border); overflow:hidden; position:relative; display:flex; align-items:center; justify-content:space-between; padding:0 2rem; background: linear-gradient(90deg, rgba(7, 9, 14, 0.92) 0%, rgba(14, 19, 31, 0.75) 45%, rgba(88, 101, 242, 0.25) 100%), url('{{ url_for(\\'static\\', filename=\\'img/mockups/discord_nitro_official_banner.jpg\\') }}') no-repeat right center / cover;">
          <div>
            <div style="font-family:'Outfit',sans-serif; font-size:1.45rem; font-weight:800; color:#FFFFFF;">DISCORD NITRO SNIPER &amp; GIVEAWAY</div>
            <div style="font-size:0.82rem; color:#BAE6FD; font-weight:600;">Tự động bắt và claim gift discord.gift/ siêu tốc 0.05s toàn bộ Server &amp; DM</div>
          </div>
          <div style="background:rgba(88, 101, 242, 0.35); border:1px solid #5865F2; padding:6px 14px; border-radius:999px; font-size:0.72rem; font-weight:700; color:#FFFFFF;">
            RADAR 0.05s ACTIVE
          </div>
        </div>
        <div class="settings-section mb-3">'''

idx_tab_sniper = text.find('id="tab-script-coming"')
if idx_tab_sniper != -1 and 'nitro-custom-banner' not in text:
    old_target = '<div class="settings-section mb-3">'
    target_idx = text.find(old_target, idx_tab_sniper)
    if target_idx != -1 and target_idx - idx_tab_sniper < 300:
        text = text[:target_idx] + nitro_banner_html + text[target_idx + len(old_target):]
        print('Injected Nitro banner into tab-script-coming')

with open(index_path, 'w', encoding='utf-8') as f:
    f.write(text)

# 4. Add abyss-banner-active styling to master_design.css
css_path = os.path.abspath('Dipre/static/css/master_design.css')
with open(css_path, 'r', encoding='utf-8') as f:
    css_text = f.read()

abyss_css = '''
/* ABYSS SUNLIGHT HERO BANNER */
.dashboard-hero-banner.abyss-banner-active {
  background: linear-gradient(135deg, rgba(7, 9, 14, 0.88) 0%, rgba(14, 19, 31, 0.75) 100%), url('/static/img/mockups/abyss_ocean_sunlight.png') no-repeat center center / cover !important;
  border: 1px solid rgba(56, 189, 248, 0.35) !important;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7), 0 0 30px rgba(2, 132, 199, 0.2) !important;
  position: relative;
}
.dashboard-hero-banner.abyss-banner-active::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: radial-gradient(circle at 75% 20%, rgba(56, 189, 248, 0.25) 0%, transparent 60%);
  pointer-events: none;
}
'''

if 'abyss-banner-active' not in css_text:
    css_text += abyss_css
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(css_text)
    print('Added abyss-banner-active styling to master_design.css')

print('All updates completed successfully!')
