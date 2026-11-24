import os

index_file = os.path.abspath('Dipre/templates/index.html')
with open(index_file, 'r', encoding='utf-8') as f:
    text = f.read()

# Make sure the Abyss banner has high-specificity inline style with Jinja url_for:
old_tag = '<div class="dashboard-hero-banner abyss-banner-active">'
new_tag = '<div class="dashboard-hero-banner abyss-banner-active" style="background: linear-gradient(135deg, rgba(7, 9, 14, 0.85) 0%, rgba(14, 19, 31, 0.75) 100%), url(\'{{ url_for(\\\'static\\\', filename=\\\'img/mockups/abyss_ocean_sunlight.png\\\') }}\') no-repeat center center / cover !important; border: 1px solid rgba(56, 189, 248, 0.45) !important; box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7), 0 0 35px rgba(2, 132, 199, 0.3) !important;">'

if old_tag in text:
    text = text.replace(old_tag, new_tag, 1)
    print('Successfully applied inline Abyss Sunlight banner to Dashboard!')
else:
    print('old_tag not found, checking if already replaced')

with open(index_file, 'w', encoding='utf-8') as f:
    f.write(text)
