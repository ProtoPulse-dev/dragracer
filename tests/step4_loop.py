"""
Step 4: continuously redraw the READY screen in a loop, like drag_race.py.
Tests whether repeated redraw in autostart causes corruption.
"""
import machine
import time

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
WHITE = 0xFFFF
GREEN = 0x07E0
RED = 0xF800
GRAY = 0x8410
DARK_GRAY = 0x4208

last_update = 0
frames = 0
t0 = time.ticks_ms()

while time.ticks_diff(time.ticks_ms(), t0) < 5000:
    now = time.ticks_ms()
    if time.ticks_diff(now, last_update) >= 200:
        last_update = now
        disp.fill(BLACK)
        disp.fill_rect(0, 0, 4, 8, GREEN)
        text8("READY", 8, 0, GREEN)
        text8("S8", 142, 0, GRAY)
        disp.hline(0, 9, 160, DARK_GRAY)
        digits24x40.draw_number_trimmed(disp, "  0.0", 0, 14, WHITE)
        text8("km/h", 132, 45, GRAY)
        text8("T0.0", 0, 70, DARK_GRAY)
        disp.show()
        frames += 1

print("loop redraw done, frames:", frames)
