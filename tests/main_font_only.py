"""
Smallest possible main.py experiment: init hardware, draw one 24x40 digit,
stop.  Deploy as main.py to test whether the font module survives autostart.

Deploy:
    mpremote connect /dev/ttyACM0 fs cp tests/main_font_only.py :main.py
    mpremote connect /dev/ttyACM0 reset

Watch the display.  A correct screen shows a large "5" in the middle.
"""
import machine
import time

from heltec_tracker_v2 import (
    TFT_CS, TFT_SCLK, TFT_MOSI, TFT_RS, TFT_RST, TFT_BL,
    VEXT_CTRL,
)
from st7735s import ST7735S
import digits24x40
import framebuf
import font8x8

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

disp.fill(0x0000)
digits24x40.draw_digit(disp, 5, 61, 12, 0xFFFF)
disp.show()

while True:
    time.sleep_ms(1000)
