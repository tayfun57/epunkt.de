from pathlib import Path
from bs4 import BeautifulSoup

path = Path('content/Wollseifen_-_das_tote_Dorf/Der_Bau_der_Urfttalsperre/der_bau_der_urfttalsperre.md')
text = path.read_text(encoding='utf-8')

parts = text.split('---\n', 2)
if len(parts) < 3:
    raise SystemExit('unexpected frontmatter format')

fmeta = '---\n'.join(parts[:2]) + '---\n\n'
content = parts[2]

marker = 'Die Urfttalsperre war einmal Europas grösster Stausee'
idx = content.find(marker)
if idx == -1:
    raise SystemExit('marker not found')

keep_start = content.rfind('<p', 0, idx)
if keep_start == -1:
    keep_start = idx

content = content[keep_start:]

soup = BeautifulSoup(content, 'html.parser')

for a in soup.find_all('a'):
    href = a.get('href', '')
    if 'web.archive.org' in href or href.startswith('/web/20160412123409') or 'eifelfoto.com' in href or 'guestbook' in href or 'schnelle-online.info' in href:
        a.unwrap()

for tbl in soup.find_all('table'):
    has_text = tbl.get_text(strip=True)
    has_img = bool(tbl.find('img'))
    if not has_img and not has_text:
        tbl.decompose()

for tag in soup(['script', 'form', 'iframe', 'style']):
    tag.decompose()

for img in soup.find_all('img'):
    src = img.get('src','')
    if src.startswith('/web/20160412123409/http://www.eifelpunkt.de/'):
        img['src'] = '/' + src.split('/http://www.eifelpunkt.de/', 1)[1]

clean_html = str(soup).strip()
new_text = fmeta + clean_html + '\n'
dst = Path('content/Wollseifen_-_das_tote_Dorf/Der_Bau_der_Urfttalsperre/index.md')
dst.write_text(new_text, encoding='utf-8')
print('Bereinigung abgeschlossen', dst)
