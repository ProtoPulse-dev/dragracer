"""
Generate a minimalist 160x80 UI design for the drag-race timer.
Creates:
  - docs/design_drive.png   (READY / idle)
  - docs/design_run.png     (RUN with progress bar)
  - docs/design_info.png    (best + recent runs)
  - docs/digit_font.png     (16x24 digit sheet 0-9)
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

W, H = 160, 80
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 128)
RED = (255, 64, 64)
BLUE = (64, 160, 255)
GRAY = (120, 120, 120)
DARK_GRAY = (60, 60, 60)

def new():
    img = Image.new('RGB', (W, H), BLACK)
    return img, ImageDraw.Draw(img)

def save(img, name):
    path = Path(__file__).parent / name
    img.save(path)
    print('wrote', path)

def digit_font():
    """Create a 16x24 monospace digit sheet."""
    img = Image.new('RGB', (160, 24), BLACK)
    draw = ImageDraw.Draw(img)
    # Try to find a bold mono font
    font = None
    for size in [26, 24, 22, 20]:
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf', size)
            break
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()
    for i in range(10):
        ch = str(i)
        bbox = draw.textbbox((0, 0), ch, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = i * 16 + (16 - tw) // 2 - bbox[0]
        y = (24 - th) // 2 - bbox[1]
        draw.text((x, y), ch, fill=WHITE, font=font)
    return img

def draw_digit(draw, d, x, y, color, w=16, h=24):
    # Use digit_font image for quick rendering
    font = digit_font_image
    sx = d * 16
    for dy in range(h):
        for dx in range(w):
            px = font.getpixel((sx + dx, dy))
            if px != (0, 0, 0):
                draw.point((x + dx, y + dy), fill=color)

def draw_big_number(draw, value, x_right, y, color, decimals=1, w=16, h=24):
    txt = ("%5.1f" % value) if decimals == 1 else ("%5.2f" % value)
    total_w = len(txt) * w
    x = x_right - total_w
    for i, ch in enumerate(txt):
        if ch == '.':
            # small dot in bottom-right area of the previous digit's space
            draw.rectangle([x + i * w + 11, y + h - 5, x + i * w + 14, y + h - 2], fill=color)
        elif ch == ' ':
            pass
        else:
            draw_digit(draw, int(ch), x + i * w, y, color, w, h)

# Pre-render digit font sheet
digit_font_image = digit_font()
save(digit_font_image, 'digit_font.png')

# ---- Drive / READY screen --------------------------------------------------
img, draw = new()
# Top status bar
draw.rectangle([0, 0, 4, 8], fill=GREEN)  # status dot
draw.text((10, 0), "READY", fill=GREEN, font=ImageFont.load_default())
draw.text((100, 0), "SAT 8", fill=GRAY, font=ImageFont.load_default())
draw.line([0, 12, W, 12], fill=DARK_GRAY, width=1)
# Big speed
draw_big_number(draw, 0.0, 155, 18, WHITE)
# km/h aligned under right side
draw.text((132, 45), "km/h", fill=GRAY, font=ImageFont.load_default())
# Small timer label
draw.text((0, 62), "timer", fill=DARK_GRAY, font=ImageFont.load_default())
draw.text((132, 62), "0.0", fill=GRAY, font=ImageFont.load_default())
save(img, 'design_drive.png')

# ---- RUN screen ------------------------------------------------------------
img, draw = new()
# Top status bar
draw.rectangle([0, 0, 4, 8], fill=RED)
draw.text((10, 0), "RUN", fill=RED, font=ImageFont.load_default())
draw.text((100, 0), "SAT 12", fill=GRAY, font=ImageFont.load_default())
draw.line([0, 12, W, 12], fill=DARK_GRAY, width=1)
# Big timer
draw_big_number(draw, 3.85, 155, 16, RED, decimals=2)
draw.text((132, 42), "sec", fill=GRAY, font=ImageFont.load_default())
# Speed
draw.text((0, 62), "97.3 km/h", fill=WHITE, font=ImageFont.load_default())
# Progress bar: 60-120 km/h
pct = (97.3 - 60) / 60
bar_w = int(pct * 60)
draw.rectangle([90, 62, 90 + bar_w, 69], fill=RED)
draw.rectangle([90 + bar_w, 62, 150, 69], outline=DARK_GRAY)
save(img, 'design_run.png')

# ---- INFO screen -----------------------------------------------------------
img, draw = new()
# Header
draw.text((0, 0), "INFO", fill=WHITE, font=ImageFont.load_default())
draw.text((60, 0), "SAT 12", fill=GRAY, font=ImageFont.load_default())
draw.text((118, 0), "BEST", fill=GRAY, font=ImageFont.load_default())
draw.line([0, 12, W, 12], fill=DARK_GRAY, width=1)
# Best run (big)
draw.text((4, 16), "BEST", fill=GRAY, font=ImageFont.load_default())
draw_big_number(draw, 7.23, 78, 24, GREEN, decimals=2)
draw.text((84, 50), "s", fill=GRAY, font=ImageFont.load_default())
# Vertical divider
draw.line([80, 12, 80, 80], fill=DARK_GRAY, width=1)
# Recent runs
draw.text((84, 16), "LAST", fill=GRAY, font=ImageFont.load_default())
recent = [8.45, 7.89, 9.12]
for i, run in enumerate(recent):
    draw.text((84, 30 + i * 14), "%d." % (i + 1), fill=GRAY, font=ImageFont.load_default())
    draw.text((100, 30 + i * 14), "%.2f s" % run, fill=WHITE, font=ImageFont.load_default())
save(img, 'design_info.png')
