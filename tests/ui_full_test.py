"""
Full UI integration test: initialises the same hardware as drag_race.py and
runs the proposed new update_tft() for a few seconds without taking over
main.py.  Safe to run with `mpremote run`.
"""
import machine
import time
import sys

sys.path.insert(0, '/')

from heltec_tracker_v2 import (
    TFT_CS, TFT_SCLK, TFT_MOSI, TFT_RS, TFT_RST, TFT_BL,
    VEXT_CTRL, GNSS_RST, GNSS_TX, GNSS_RX, GNSS_BAUD, USR_BTN,
)
from st7735s import ST7735S
import font8x8
import digits38x56
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

gnss_rst = machine.Pin(GNSS_RST, machine.Pin.OUT, value=1)
gnss_rst.value(0); time.sleep_ms(100); gnss_rst.value(1)
time.sleep_ms(300)

# We do not open UART to keep the test focused on display UI.

btn_prg = machine.Pin(USR_BTN, machine.Pin.IN, machine.Pin.PULL_UP)

class FBDisplay(framebuf.FrameBuffer):
    def __init__(self, w, h):
        self.width = self.w = w
        self.height = self.h = h
        self.buf = bytearray(w * h * 2)
        super().__init__(self.buf, w, h, framebuf.RGB565)
    def show(self):
        tft.show_framebuf(self)

disp = FBDisplay(160, 80)

_char_buf = bytearray(8)
_char_fb  = framebuf.FrameBuffer(_char_buf, 8, 8, framebuf.MONO_HLSB)

def text8(s, x, y, color, bg=None):
    for i, ch in enumerate(s):
        cx = x + i * 8
        if 0 <= cx < disp.w and 0 <= y < disp.h:
            if bg is not None:
                disp.fill_rect(cx, y, 8, 8, bg)
            font8x8.draw_char(disp, ch, cx, y, color)

# Palette
BLACK = 0x0000
WHITE = 0xFFFF
GREEN = 0x07E0
RED = 0xF800
BLUE = 0x001F
GRAY = 0x8410
DARK_GRAY = 0x4208

def draw_big_text(s, x, y, color, scale=1):
    for i, ch in enumerate(s):
        _char_fb.fill(0)
        _char_fb.text(ch, 0, 0, 1)
        for cy in range(8):
            for cx in range(8):
                if _char_fb.pixel(cx, cy):
                    disp.fill_rect(x + i*8*scale + cx*scale,
                                   y + cy*scale, scale, scale, color)

def draw_big_text_right(s, x_end, y, color, scale=1):
    glyph_w = 8 * scale
    x = x_end - glyph_w * len(s) + 1
    draw_big_text(s, x, y, color, scale)

# ---- proposed new UI (matches drag_race.py structure) ----------------------
state = "WAI"
current_speed = 0.0
current_timer = 0.0
satellites = 8
current_screen = 0
best_time = 7.23
recent_runs = [8.45, 7.89, 9.12]
_CFG = {"start": 60.0, "end": 120.0, "reset": 55.0}
flash_until_ms = -1

def _draw_progress_bar(x, y, w, h, pct, fill_color, bg_color=DARK_GRAY):
    fill_w = max(0, min(w, int(w * max(0.0, min(1.0, pct)))))
    if fill_w > 0:
        disp.fill_rect(x, y, fill_w, h, fill_color)
    if fill_w < w:
        disp.fill_rect(x + fill_w, y, w - fill_w, h, bg_color)

def _draw_status_dot(x, y, color):
    disp.fill_rect(x, y, 4, 8, color)

def update_tft():
    if time.ticks_diff(time.ticks_ms(), flash_until_ms) < 0:
        disp.fill(flash_color)
        disp.show()
        return
    disp.fill(BLACK)
    if current_screen == 0:
        if state == "WAI":
            state_lbl, dot_color = "READY", GREEN
        elif state == "RUN":
            state_lbl, dot_color = "RUN", RED
        else:
            state_lbl, dot_color = "COOL", BLUE
        _draw_status_dot(0, 0, dot_color)
        text8(state_lbl, 8, 0, dot_color, BLACK)
        text8("S%d" % min(satellites, 99), 142, 0, GRAY, BLACK)
        disp.hline(0, 9, 160, DARK_GRAY)
        if state == "RUN":
            timer_str = "%5.2f" % current_timer
            digits38x56.draw_number_trimmed(disp, timer_str, 0, 10, RED)
            text8("s", 134, 54, GRAY, BLACK)
            text8("%5.1f kmh" % current_speed, 78, 72, WHITE, BLACK)
            span = max(1.0, _CFG["end"] - _CFG["start"])
            pct = (current_speed - _CFG["start"]) / span
            _draw_progress_bar(0, 65, 160, 4, pct, RED)
        else:
            speed_str = "%5.1f" % current_speed
            digits38x56.draw_number_trimmed(disp, speed_str, 0, 10, WHITE)
            text8("kmh", 130, 50, GRAY, BLACK)
            timer_str = "%5.1f" % current_timer
            text8("T" + timer_str, 0, 72, DARK_GRAY, BLACK)
    else:
        # Info screen (original)
        text8("INFO", 0, 2, BLUE, BLACK)
        text8("SAT %2d" % min(satellites, 99), 60, 2, GRAY, BLACK)
        text8("BEST", 120, 2, GRAY, BLACK)
        disp.hline(0, 12, 160, GRAY)
        text8("BEST RUN", 4, 16, GRAY, BLACK)
        best_str = "%.2fs" % best_time if best_time > 0 else "--.-s"
        draw_big_text_right(best_str, 76, 22, GREEN, scale=2)
        text8("HUIDIG", 4, 46, GRAY, BLACK)
        text8("%5.1f km/h" % current_speed, 4, 56, WHITE, BLACK)
        disp.vline(80, 12, 68, GRAY)
        text8("LAATSTE", 84, 16, GRAY, BLACK)
        if not recent_runs:
            text8("Geen data", 84, 26, GRAY, BLACK)
        else:
            y_pos = 26
            for i, run in enumerate(recent_runs[:3]):
                rank_str = "%d." % (i + 1)
                text8(rank_str, 84, y_pos, GRAY, BLACK)
                val_str = "%.2fs" % run
                draw_big_text_right(val_str, 156, y_pos, WHITE, scale=1)
                y_pos += 14
    disp.show()

# ---- run a sequence of frames ----------------------------------------------
print("showing READY screen")
update_tft()
time.sleep_ms(2000)

print("showing RUN screen")
state = "RUN"
current_speed = 97.3
current_timer = 3.85
update_tft()
time.sleep_ms(2000)

print("showing INFO screen")
current_screen = 1
state = "COO"
current_speed = 0.0
update_tft()
time.sleep_ms(2000)

disp.fill(BLACK)
text8("UI TEST OK", 32, 36, GREEN)
disp.show()
print("UI test done")
