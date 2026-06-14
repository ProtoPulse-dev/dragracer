"""
Step 3: add the RUN screen with progress bar.
"""
import machine
import time
import sys

from heltec_tracker_v2 import (
    TFT_CS, TFT_SCLK, TFT_MOSI, TFT_RS, TFT_RST, TFT_BL,
    VEXT_CTRL,
)
from st7735s import ST7735S
import font8x8
import digits24x40
import framebuf

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

def text8(s, x, y, color, bg=None):
    for i, ch in enumerate(s):
        cx = x + i * 8
        if 0 <= cx < disp.w and 0 <= y < disp.h:
            if bg is not None:
                disp.fill_rect(cx, y, 8, 8, bg)
            font8x8.draw_char(disp, ch, cx, y, color)

BLACK = 0x0000
RED = 0xF800
GREEN = 0x07E0
GRAY = 0x8410
DARK_GRAY = 0x4208
WHITE = 0xFFFF

def _draw_progress_bar(x, y, w, h, pct, fill_color, bg_color=DARK_GRAY):
    fill_w = max(0, min(w, int(w * max(0.0, min(1.0, pct)))))
    if fill_w > 0:
        disp.fill_rect(x, y, fill_w, h, fill_color)
    if fill_w < w:
        disp.fill_rect(x + fill_w, y, w - fill_w, h, bg_color)

# RUN screen
disp.fill(BLACK)
disp.fill_rect(0, 0, 4, 8, RED)
text8("RUN", 8, 0, RED)
text8("S12", 138, 0, GRAY)
disp.hline(0, 9, 160, DARK_GRAY)
digits24x40.draw_number_trimmed(disp, "3.85", 0, 14, RED)
text8("s", 132, 52, GRAY)
text8("97.3 kmh", 80, 70, WHITE)
_draw_progress_bar(0, 63, 160, 3, (97.3 - 60) / 60, RED)
disp.show()
print("step3 ok")

while True:
    time.sleep_ms(500)
