from PIL import Image, ImageDraw, ImageFont
import os

w, h = 1920, 1080
img = Image.new("RGB", (w, h), (10, 10, 18))
draw = ImageDraw.Draw(img)

# Subtle radial gradient
for i in range(h):
    r = int(10 + 15 * (1 - abs(i - h / 2) / (h / 2)))
    g = int(10 + 12 * (1 - abs(i - h / 2) / (h / 2)))
    b = int(18 + 20 * (1 - abs(i - h / 2) / (h / 2)))
    for x in range(w):
        cx, cy = w // 2, h // 2
        dist = ((x - cx) ** 2 + (i - cy) ** 2) ** 0.5
        max_dist = (cx**2 + cy**2) ** 0.5
        factor = max(0, 1 - dist / max_dist)
        draw.point(
            (x, i),
            fill=(int(r + 30 * factor), int(g + 25 * factor), int(b + 40 * factor)),
        )

# Font
font_path = None
for fp in [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/c/Windows/Fonts/arialbd.ttf",
    "/c/Windows/Fonts/segoeuib.ttf",
    "/c/Windows/Fonts/consola.ttf",
    "/c/Windows/Fonts/calibrib.ttf",
]:
    if os.path.exists(fp):
        font_path = fp
        break

title_font = ImageFont.truetype(font_path, 52) if font_path else ImageFont.load_default()
sub_font = ImageFont.truetype(font_path, 36) if font_path else ImageFont.load_default()

lines = [
    ("What if I told you", (180, 170, 220)),
    ("the most unshakeable portfolio on Earth...", (210, 210, 225)),
    ("doesn’t believe in anything?", (210, 210, 225)),
]

y_start = h // 2 - 120
for i, (text, c) in enumerate(lines):
    bbox = draw.textbbox((0, 0), text, font=title_font)
    tw = bbox[2] - bbox[0]
    x = (w - tw) // 2
    y = y_start + i * 80
    draw.text((x + 2, y + 2), text, font=title_font, fill=(30, 30, 50))
    draw.text((x, y), text, font=title_font, fill=c)

sig = "- unattributed"
bbox = draw.textbbox((0, 0), sig, font=sub_font)
sw = bbox[2] - bbox[0]
draw.text((w - sw - 60, h - 60), sig, font=sub_font, fill=(100, 100, 130))

out_path = os.path.join(os.path.dirname(__file__), "quote_image.png")
img.save(out_path)
print(f"Image saved to {out_path}")
