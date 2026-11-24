import os
from playwright.sync_api import sync_playwright

html_file = os.path.abspath('Dipre/oceanic_showcase.html')
with open(html_file, 'r', encoding='utf-8') as f:
    text = f.read()

comments_and_ids = [
    ('<!-- TAB 1: DASHBOARD COMMAND CENTER -->', 'sec-dashboard'),
    ("<!-- TAB 2: THEME RPC HUB (WITH USER'S INTELLIJ & PYCHARM CARD CUTOUT) -->", 'sec-theme-rpc'),
    ('<!-- TAB 3: LYRIC STATUS KARAOKE -->', 'sec-lyric-karaoke'),
    ('<!-- TAB 4: NITRO SNIPER & GIVEAWAY (WITH OFFICIAL DISCORD NITRO BANNER) -->', 'sec-nitro-sniper'),
    ('<!-- TAB 5: VOICE 24/7 & SOUNDBOARD -->', 'sec-afk-voice'),
    ('<!-- TAB 6: MULTI-TOKENS & USERBOT -->', 'sec-multi-tokens')
]

for comment, sec_id in comments_and_ids:
    idx = text.find(comment)
    if idx != -1:
        div_idx = text.find('<div class="section-block">', idx)
        if div_idx != -1 and div_idx - idx < 120:
            text = text[:div_idx] + f'<div id="{sec_id}" class="section-block">' + text[div_idx + len('<div class="section-block">'):]
            print(f'Assigned id="{sec_id}"')
        else:
            print(f'Already assigned or not found for {sec_id}')

with open(html_file, 'w', encoding='utf-8') as f:
    f.write(text)

print('Capturing screenshots now...')
out_dir = os.path.abspath('Dipre/static/img/mockups')
os.makedirs(out_dir, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 900})
    page.goto('file:///' + html_file.replace('\\', '/'))
    page.wait_for_timeout(2000)
    
    sections = [
        ('sec-dashboard', 'oceanic_sec_dashboard.jpg'),
        ('sec-theme-rpc', 'oceanic_sec_theme_rpc.jpg'),
        ('sec-lyric-karaoke', 'oceanic_sec_lyric_karaoke.jpg'),
        ('sec-nitro-sniper', 'oceanic_sec_nitro_sniper.jpg'),
        ('sec-afk-voice', 'oceanic_sec_afk_voice.jpg'),
        ('sec-multi-tokens', 'oceanic_sec_multi_tokens.jpg')
    ]
    
    for sec_id, filename in sections:
        elem = page.query_selector(f'#{sec_id}')
        if elem:
            elem.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            target_path = os.path.join(out_dir, filename)
            elem.screenshot(path=target_path, quality=92, type='jpeg')
            print(f'Captured {filename}: {os.path.getsize(target_path)} bytes')
        else:
            print(f'Failed to locate #{sec_id}')
    browser.close()
