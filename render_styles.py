import os
from playwright.sync_api import sync_playwright

html_file = os.path.abspath('Dipre/styles_showcase.html')
out_dir = os.path.abspath('Dipre/static/img/mockups')
os.makedirs(out_dir, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 900})
    page.goto('file:///' + html_file.replace('\\', '/'))
    page.wait_for_timeout(1500)
    
    # 1. Full comparison screenshot
    page.screenshot(path=os.path.join(out_dir, 'ui_styles_full_comparison.jpg'), full_page=True, quality=90, type='jpeg')
    
    # 2. Individual style screenshots
    styles = [
        ('style-1', 'ui_style_1_aceternity_matrix.jpg'),
        ('style-2', 'ui_style_2_discord_dualdock.jpg'),
        ('style-3', 'ui_style_3_linear_minimalist.jpg')
    ]
    for sid, filename in styles:
        elem = page.query_selector(f'#{sid}')
        if elem:
            elem.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            elem.screenshot(path=os.path.join(out_dir, filename), quality=92, type='jpeg')
            print(f'Captured {filename}')
    browser.close()
print('All styles captured successfully!')
