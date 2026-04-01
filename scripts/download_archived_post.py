
import os
import re
import time
import requests
from bs4 import BeautifulSoup

# The URL of the page from web.archive.org
archive_url = "https://web.archive.org/web/20160412123409/http://www.eifelpunkt.de/Wollseifen_-_das_tote_Dorf/Der_Bau_der_Urfttalsperre/der_bau_der_urfttalsperre.html"
archive_base = "https://web.archive.org"

# Directory where the new file will be saved
output_dir = "content/Wollseifen_-_das_tote_Dorf/Der_Bau_der_Urfttalsperre"
static_dir = "static"
os.makedirs(output_dir, exist_ok=True)


def download_images_and_update_html():
    # Use web_fetch to get the raw html
    response = requests.get(archive_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Update image tags
    for img_tag in soup.find_all('img'):
        src = img_tag.get('src')
        if not src or 'clearpixel.gif' in src or 'tinc?key=' in src:
            if src and 'clearpixel.gif' in src:
                img_tag.decompose() # remove clearpixel images
            continue

        if 'web.archive.org' in src or src.startswith('/web/'):
            original_img_url_match = re.search(r'http://www.eifelpunkt.de/(.*)', src)
            if not original_img_url_match:
                print(f"Could not extract original image path from {src}")
                continue
                
            original_img_path = original_img_url_match.group(1)
            print(f"Found image: {original_img_path}")
            
            local_img_path = os.path.join(static_dir, original_img_path)

            if not os.path.exists(local_img_path):
                download_url = src
                if src.startswith('/web/'):
                    download_url = f"{archive_base}{src}"

                os.makedirs(os.path.dirname(local_img_path), exist_ok=True)
                
                try:
                    response = requests.get(download_url, stream=True)
                    response.raise_for_status()
                    with open(local_img_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print(f"Downloaded {download_url} to {local_img_path}")
                    time.sleep(1)
                except requests.exceptions.RequestException as e:
                    print(f"Error downloading {download_url}: {e}")
            else:
                print(f"Image already exists: {local_img_path}")

            img_tag['src'] = f"/{original_img_path}"

    # Update anchor tags
    for a_tag in soup.find_all('a'):
        href = a_tag.get('href')
        if href and 'web.archive.org' in href:
            original_href_match = re.search(r'http://www.eifelpunkt.de/(.*)', href)
            if original_href_match:
                original_href = original_href_match.group(1)
                a_tag['href'] = f"/{original_href}"
        
        # remove javascript events
        a_tag.attrs.pop('onmouseover', None)
        a_tag.attrs.pop('onmouseout', None)


    # Remove the web archive header by finding the body tag
    body_content = soup.find('body')
    
    # Remove all script tags
    for script in body_content.find_all('script'):
        script.decompose()

    return str(body_content)


# Download images and update HTML
final_html = download_images_and_update_html()

# Save the final HTML file
output_filepath = os.path.join(output_dir, "der_bau_der_urfttalsperre.html")
with open(output_filepath, "w", encoding="utf-8") as f:
    f.write(final_html)

print(f"Successfully created {output_filepath}")
