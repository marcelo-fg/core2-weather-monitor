import os
import urllib.request
import ssl
from PIL import Image, ImageDraw

ssl._create_default_https_context = ssl._create_unverified_context

bg_color = (0, 0, 0) # 0x000000 (Pure Black)
size = (20, 20)
output_dir = "middleware/static/icons"

os.makedirs(output_dir, exist_ok=True)

icons = {
    "clear": "2600",
    "partly": "1f324",
    "clouds": "2601",
    "rain": "1f327",
    "storm": "26c8",
    "snow": "2744",
}

for name, code in icons.items():
    print(f"Processing {name}...")
    url = f"https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/{code}.png"
    tmp_png = f"/tmp/{name}.png"
    out_jpg = f"{output_dir}/{name}.jpg"
    
    try:
        urllib.request.urlretrieve(url, tmp_png)
    except Exception:
        url = f"https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/{code}-fe0f.png"
        urllib.request.urlretrieve(url, tmp_png)
        
    # Open PNG, resize, composite over BG, save as JPG
    img = Image.open(tmp_png).convert("RGBA")
    img = img.resize(size, Image.LANCZOS)
    
    bg = Image.new("RGB", size, bg_color)
    bg.paste(img, (0, 0), img) # use img as mask for alpha channel
    bg.save(out_jpg, "JPEG", quality=90)

print("All icons generated!")

