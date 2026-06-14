"""
On-device font / layout smoke test.

This script is meant to be run with `mpremote run` while drag_race.py is
NOT the active main.py.  It initialises the display and draws a sequence of
screens so you can verify that a font module and a layout work on real
hardware without risking a broken main.py.

Usage:
    mpremote connect /dev/ttyACM0 run tests/font_test.py

Press Ctrl-C to stop the test loop.
"""
import machine
import time
import sys

sys.path.insert(0, '/src')

from heltec_tracker_v2 import (
    TFT_CS, TFT_SCLK, TFT_MOSI, TFT_RS, TFT_RST, TFT_BL,
    VEXT_CTRL, GNSS_RST, GNSS_RX, GNSS_TX, GNSS_BAUD, USR_BTN,
)
from st7735s import ST7735S
import font8x8

# Optional: try to import digit font modules if they exist.
try:
    import digits24x40
except ImportError:
    digits24x40 = None
try:
    import digits32x48
except ImportError:
    digits32x48 = None
try:
    import digits38x56
except ImportError:
    digits38x56 = None

# Bump CPU to 240 MHz for fast SPI frame blits
try:
    machine.freq(240_000_000)
except Exception:
    pass

# Power rail + backlight
vext = machine.Pin(VEXT_CTRL, machine.Pin.OUT, value=1)
time.sleep_ms(50)
spi = machine.SPI(2, baudrate=20_000_000, polarity=0, phase=0,
                  sck=machine.Pin(TFT_SCLK), mosi=machine.Pin(TFT_MOSI),
                  miso=machine.Pin(2))
tft = ST7735S(spi,
              cs=machine.Pin(TFT_CS, machine.Pin.OUT, value=1),
              dc=machine.Pin(TFT_RS, machine.Pin.OUT, value=0),
              rst=machine.Pin(TFT_RST, machine.Pin.OUT, value=1),
              bl=machine.Pin(TFT_BL, machine.Pin.OUT, value=0),  # active low: on
              width=160, height=80,
              xstart=0, ystart=26, rotation=5)

import framebuf

class FBDisplay(framebuf.FrameBuffer):
    def __init__(self, w, h):
        self.width = self.w = w
        self.height = self.h = h
        self.buf = bytearray(w * h * 2)
        super().__init__(self.buf, w, h, framebuf.RGB565)
    def show(self):
        tft.show_framebuf(self)

disp = FBDisplay(160, 80)

# 8x8 helpers (same as drag_race.py)
_char_buf = bytearray(8)
_char_fb  = framebuf.FrameBuffer(_char_buf, 8, 8, framebuf.MONO_HLSB)

def text8(s, x, y, color, bg=None):
    for i, ch in enumerate(s):
        cx = x + i * 8
        if 0 <= cx < disp.w and 0 <= y < disp.h:
            if bg is not None:
                disp.fill_rect(cx, y, 8, 8, bg)
            font8x8.draw_char(disp, ch, cx, y, color)

BLACK = 0x0000
WHITE = 0xFFFF
RED   = 0xF800
GREEN = 0x07E0
GRAY  = 0x8410

# ----- test screens ---------------------------------------------------------

def test_8x8_scaled():
    disp.fill(BLACK)
    text8("READY", 0, 0, GREEN)
    text8("SAT 8", 100, 0, GRAY)
    disp.hline(0, 10, 160, GRAY)
    # scale-3 digits using 8x8
    def big_text(s, x, y, color, scale):
        for i, ch in enumerate(s):
            _char_fb.fill(0)
            _char_fb.text(ch, 0, 0, 1)
            for cy in range(8):
                for cx in range(8):
                    if _char_fb.pixel(cx, cy):
                        disp.fill_rect(x + i*8*scale + cx*scale, y + cy*scale, scale, scale, color)
    big_text("  0.0", 20, 18, WHITE, 3)
    text8("km/h", 132, 34, GRAY)
    text8("T 0.0", 0, 70, GRAY)
    disp.show()
    return True

def test_digit_module(mod, label):
    if mod is None:
        return False
    disp.fill(BLACK)
    text8(label, 0, 0, WHITE)
    disp.hline(0, 10, 160, GRAY)
    # draw all digits 0-9 across the screen
    try:
        mod.draw_number(disp, "0123456789", 0, 16, WHITE)
    except Exception as e:
        text8("ERR: " + str(e)[:16], 0, 30, RED)
        disp.show()
        time.sleep_ms(500)
        return False
    text8("0123456789", 0, 60, GRAY)
    disp.show()
    return True

def test_layout_ready(mod):
    disp.fill(BLACK)
    text8("READY", 8, 0, GREEN)
    text8("S8", 142, 0, GRAY)
    disp.hline(0, 9, 160, GRAY)
    try:
        mod.draw_number_trimmed(disp, "  0.0", 0, 14, WHITE)
    except Exception as e:
        text8("ERR:" + str(e)[:16], 0, 30, RED)
        disp.show()
        time.sleep_ms(500)
        return False
    text8("km/h", 132, 50, GRAY)
    text8("T0.0", 0, 70, GRAY)
    disp.show()
    return True

def test_layout_run(mod):
    disp.fill(BLACK)
    text8("RUN", 8, 0, RED)
    text8("S12", 138, 0, GRAY)
    disp.hline(0, 9, 160, GRAY)
    try:
        mod.draw_number_trimmed(disp, "3.85", 0, 14, RED)
    except Exception as e:
        text8("ERR:" + str(e)[:16], 0, 30, WHITE)
        disp.show()
        time.sleep_ms(500)
        return False
    text8("s", 132, 52, GRAY)
    text8("97.3 kmh", 80, 70, WHITE)
    # progress bar 60..120
    pct = (97.3 - 60) / 60
    fill_w = int(160 * max(0.0, min(1.0, pct)))
    if fill_w > 0:
        disp.fill_rect(0, 63, fill_w, 3, RED)
    disp.show()
    return True

# ----- run sequence ---------------------------------------------------------
screens = [
    ("8x8 scaled", test_8x8_scaled),
]
for mod, name in ((digits24x40, "24x40"), (digits32x48, "32x48"), (digits38x56, "38x56")):
    if mod is not None:
        screens.append((name + " digits", lambda m=mod: test_digit_module(m, name + " 0-9")))
        screens.append((name + " ready", lambda m=mod: test_layout_ready(m)))
        screens.append((name + " run", lambda m=mod: test_layout_run(m)))

print("Font test starting; showing each screen for 2 seconds...")
for name, fn in screens:
    print("screen:", name)
    try:
        ok = fn()
    except Exception as e:
        disp.fill(BLACK)
        text8("CRASH " + name[:10], 0, 0, RED)
        text8(str(e)[:20], 0, 16, WHITE)
        disp.show()
        print("  CRASH:", e)
        time.sleep_ms(2000)
    else:
        if not ok:
            text8(name + " FAIL", 0, 72, RED)
            disp.show()
            print("  FAIL")
        else:
            print("  OK")
        time.sleep_ms(2000)

disp.fill(BLACK)
text8("TEST DONE", 40, 36, GREEN)
disp.show()
print("Font test done.")
