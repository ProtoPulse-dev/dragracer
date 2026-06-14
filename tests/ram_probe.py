"""
ram_probe.py — measure free RAM at each stage of drag_race startup.
Run with: mpremote connect /dev/ttyACM0 run tests/ram_probe.py
"""
import gc
import micropython

def show(label):
    gc.collect()
    free = gc.mem_free()
    alloc = gc.mem_alloc()
    print("%s: free=%d alloc=%d total=%d" % (label, free, alloc, free + alloc))

show("boot")

import machine
try:
    machine.freq(240_000_000)
except Exception:
    pass
show("after machine.freq")

from heltec_tracker_v2 import (
    TFT_CS, TFT_SCLK, TFT_MOSI, TFT_RS, TFT_RST, TFT_BL,
    VEXT_CTRL, GNSS_RST, GNSS_TX, GNSS_RX, GNSS_BAUD, USR_BTN,
)
show("after heltec_tracker_v2")

from st7735s import ST7735S
show("after st7735s")

import font8x8
show("after font8x8")

import framebuf
show("after framebuf")

# Power rail
vext = machine.Pin(VEXT_CTRL, machine.Pin.OUT, value=1)
import time
time.sleep_ms(50)
show("after vext")

spi = machine.SPI(2, baudrate=20_000_000, polarity=0, phase=0,
                  sck=machine.Pin(TFT_SCLK), mosi=machine.Pin(TFT_MOSI),
                  miso=machine.Pin(2))
show("after SPI init")

tft = ST7735S(spi,
              cs=machine.Pin(TFT_CS, machine.Pin.OUT, value=1),
              dc=machine.Pin(TFT_RS, machine.Pin.OUT, value=0),
              rst=machine.Pin(TFT_RST, machine.Pin.OUT, value=1),
              bl=machine.Pin(TFT_BL, machine.Pin.OUT, value=0),
              width=160, height=80,
              xstart=0, ystart=26, rotation=5)
show("after ST7735S init")

class FBDisplay(framebuf.FrameBuffer):
    def __init__(self, w, h):
        self.width = self.w = w
        self.height = self.h = h
        self.buf = bytearray(w * h * 2)
        super().__init__(self.buf, w, h, framebuf.RGB565)
    def show(self):
        tft.show_framebuf(self)

disp = FBDisplay(160, 80)
show("after FBDisplay (framebuffer)")

# Now load digit fonts and see cost
import digits16x24
show("after digits16x24")

import digits24x40
show("after digits24x40")

import digits32x48
show("after digits32x48")

import digits38x56
show("after digits38x56")

print("RAM probe done")
