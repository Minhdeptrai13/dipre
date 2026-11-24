import os

index_file = os.path.abspath('templates/index.html')
with open(index_file, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace escaped quotes in Jinja tags:
text = text.replace(r"\'static\'", "'static'")
text = text.replace(r"\'img/mockups/abyss_ocean_sunlight.png\'", "'img/mockups/abyss_ocean_sunlight.png'")
text = text.replace(r"\'img/mockups/theme_rpc_showcase_cards.png\'", "'img/mockups/theme_rpc_showcase_cards.png'")
text = text.replace(r"\'img/mockups/discord_nitro_official_banner.jpg\'", "'img/mockups/discord_nitro_official_banner.jpg'")
text = text.replace(r"\'", "'")

with open(index_file, 'w', encoding='utf-8') as f:
    f.write(text)

print('Cleaned index.html successfully!')

from main import create_app
from flask import render_template
app = create_app()
with app.app_context():
    out = render_template('index.html', username='minhnvb', has_token=True, discord_username='minhnvb', discord_avatar='', user_bots=[], turnstile_site_key='')
    print('SUCCESS! Rendered index.html without any errors! Total bytes:', len(out))
