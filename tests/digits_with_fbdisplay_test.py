"""
Test digit fonts with the exact FBDisplay class used by drag_race.py.
Run with: mpremote connect /dev/ttyACM0 run tests/digits_with_fbdisplay_test.py
"""
import machine
import time
import sys

sys.path.insert(0, '/')

from heltec_tracker_v2 import (
    TFT_CS, TFT_SCLK, TFT_MOSI, TFT_RS, TFT_RST, TFT_BL,
    VEXT_CTRL,
)
from st7735s import ST7735S
import font8x8
import framebuf

try:
    import digits38x56
except ImportError as e:
    print("cannot import digits38x56:", e)
    digits38x56 = None

try:
    machine.freq(240_000_000)
except Exception:
    pass

vext = machine.Pin(VEXT_CTRL, machine.Pin.OUT, value=1)
time.sleep_ms(50)
spi = machine.SPI(2, baudrate=20_000_000, polarity=0, phase=0,
                  sck=machine.Pin(TFT_SCLK), mosi=machine.Pin(TFT_MOSI),
                  miso=machine.Pin(2))
tft = ST7735S(spi,
              cs=machine.Pin(TFT_CS, machine.Pin.OUT, value=1),
              dc=machine.Pin(TFT_RS, machine.Pin.OUT, value=0),
              rst=machine.Pin(TFT_RST, machine.Pin.OUT, value=1),
              bl=machine.Pin(TFT_BL, machine.Pin.OUT, value=0),
              width=160, height=80,
              xstart=0, ystart=26, rotation=5)

class FBDisplay(framebuf.FrameBuffer):
    def __init__(self, w, h):
        self.width = self.w = w
        self.height = self.h = h
        self.buf = bytearray(w * h * 2)
        super().__init__(self.buf, w, h, framebuf.RGB565)
    def show(self):
        tft.show_framebuf(self)

disp = FBDisplay(160, 80)
WHITE = 0xFFFF
BLACK = 0x0000
RED = 0xF800
GRAY = 0x8410

def text8(s, x, y, color, bg=None):
    for i, ch in enumerate(s):
        cx = x + i * 8
        if cx < disp.w and y < disp.h:
            if bg is not None:
                disp.fill_rect(cx, y, 8, 8, bg)
            font8x8.draw_char(disp, ch, cx, y, color)

if digits38x56 is None:
    text8("NO FONT", 0, 36, RED)
    disp.show()
else:
    print("drawing 38x56 digit test...")
    disp.fill(BLACK)
    text8("38x56 TEST", 0, 0, WHITE)
    try:
        digits38x56.draw_number_trimmed(disp, "  0.0", 0, 14, WHITE)
    except Exception as e:
        text8("ERR1:" + str(e)[:16], 0, 30, RED)
        print("err1:", e)
    disp.show()
    time.sleep_ms(1500)

    disp.fill(BLACK)
    text8("RUN", 0, 0, RED)
    try:
        digits38x56.draw_number_trimmed(disp, "3.85", 0, 14, RED)
    except Exception as e:
        text8("ERR2:" + str(e)[:16], 0, 30, WHITE)
        print("err2:", e)
    disp.show()
    time.sleep_ms(1500)

    disp.fill(BLACK)
    text8("DONE", 0, 36, WHITE)
    disp.show()

print("test done")
