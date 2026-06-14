"""
main.py — Heltec Wireless Tracker V2 (ESP32-S3FN8, custom no-PSRAM firmware).

On boot this script:
  1. Drives GPIO3 (Vext_Ctrl) high to power the on-board 3.3V rail
     (TFT + GNSS + LoRa front-end share this rail).
  2. Initialises the on-board ST7789 TFT in portrait (80x160).
  3. Pulses GPIO35 (GNSS_RST) low then high to reset the UC6580.
  4. Opens UART2 on (tx=34, rx=33) at 115200 to read NMEA.
  5. Shows a splash with board name, then a live GNSS page with
     fix status, satellite count, latitude/longitude, speed, and
     time-of-day from $GNGGA / $GNRMC.
  6. Blinks the backlight at 1 Hz as a heartbeat.

Press Ctrl-C on the USB-CDC REPL to stop.
"""
import sys, time
import machine
from machine import Pin, SPI, UART

# Bump CPU to 240 MHz for fast SPI frame blits
try:
    machine.freq(240_000_000)
except Exception:
    pass

from heltec_tracker_v2 import (
    TFT_CS, TFT_SCLK, TFT_MOSI, TFT_RS, TFT_RST, TFT_BL,
    VEXT_CTRL, GNSS_RST, GNSS_TX, GNSS_RX, GNSS_BAUD, BOARD_NAME,
)
from st7735s import ST7735S
import font8x8

WHITE  = 0xFFFF
BLACK  = 0x0000
CYAN   = 0x07FF
YELLOW = 0xFFE0
GREEN  = 0x07E0
RED    = 0xF800
GREY   = 0x4208

# ---- 1) Power up the on-board 3.3V rail -----------------------------------
vext = Pin(VEXT_CTRL, Pin.OUT, value=1)
time.sleep_ms(50)

# ---- 2) ST7789 80x160 portrait ---------------------------------------------
spi = SPI(2, baudrate=20_000_000, polarity=0, phase=0,
          sck=Pin(TFT_SCLK), mosi=Pin(TFT_MOSI), miso=Pin(2))
tft = ST7735S(spi,
              cs=Pin(TFT_CS, Pin.OUT, value=1),
              dc=Pin(TFT_RS, Pin.OUT, value=0),
              rst=Pin(TFT_RST, Pin.OUT, value=1),
              bl=Pin(TFT_BL, Pin.OUT, value=1),
              width=80, height=160,
              xstart=26, ystart=0, rotation=0)
backlight = Pin(TFT_BL, Pin.OUT, value=0)  # active low: 0 = ON

# ---- 3) Reset the UC6580 --------------------------------------------------
gnss_rst = Pin(GNSS_RST, Pin.OUT, value=1)
gnss_rst.value(0); time.sleep_ms(100); gnss_rst.value(1)
time.sleep_ms(300)

# ---- 4) UART2 to the GNSS -------------------------------------------------
gnss = UART(2, baudrate=GNSS_BAUD, tx=GNSS_RX, rx=GNSS_TX,
            bits=8, parity=None, stop=1, timeout=100, rxbuf=2048)
time.sleep_ms(200)  # let first NMEA sentences arrive

# ---- 5) Splash -------------------------------------------------------------
W, H = 80, 160
def center_x(s, scale=1):
    return (W - len(s) * 8 * scale) // 2

tft.fill(BLACK)
tft.text8x8(center_x("HELTEC"), 20, "HELTEC", YELLOW, BLACK)
tft.text8x8(center_x("TRACKER"), 35, "TRACKER", YELLOW, BLACK)
tft.text8x8(center_x("V2"), 50, "V2", YELLOW, BLACK)
tft.text8x8(center_x("uPy"), 75, "uPy", CYAN, BLACK)
tft.text8x8(center_x(sys.version.split()[2][:5]), 90, sys.version.split()[2][:5], CYAN, BLACK)
tft.text8x8(center_x("GPS"), 115, "GPS", GREEN, BLACK)
tft.text8x8(center_x("READY"), 130, "READY", GREEN, BLACK)
time.sleep_ms(1200)


# ---- minimal NMEA parser ---------------------------------------------------
# Tracks: fix (0/1/2), sats, lat, lng, speed (kts), time (hhmmss)
state = {
    "fix": 0, "sats": 0,
    "lat": 0.0, "lng": 0.0,
    "spd": 0.0, "time": "", "date": "",
}

def _deg(v):
    # NMEA lat/lng: DDMM.MMMM  or  DDDMM.MMMM
    deg = int(v // 100)
    minutes = v - deg * 100
    sign = 1 if (deg >= 0) else -1
    return sign * (abs(deg) + minutes / 60.0)

def _spd_knots(s):
    try:
        return float(s)
    except Exception:
        return 0.0

def parse(line):
    s = line.decode("ascii", "ignore").strip()
    if not s.startswith("$"):
        return
    body = s.lstrip("$").split("*")[0]
    parts = body.split(",")
    typ = parts[0]
    try:
        if typ == "GNGGA" or typ == "GPGGA":
            state["time"] = parts[1]
            if parts[2] != "":
                state["lat"] = _deg(float(parts[2])) * (1 if parts[3] == "N" else -1)
            if parts[4] != "":
                state["lng"] = _deg(float(parts[4])) * (1 if parts[5] == "E" else -1)
            state["fix"] = int(parts[6] or 0)
            state["sats"] = int(parts[7] or 0)
        elif typ == "GNRMC" or typ == "GPRMC":
            state["time"] = parts[1]
            state["date"] = parts[9]
            if parts[3] != "":
                state["lat"] = _deg(float(parts[3])) * (1 if parts[4] == "N" else -1)
            if parts[5] != "":
                state["lng"] = _deg(float(parts[5])) * (1 if parts[6] == "E" else -1)
            state["spd"] = _spd_knots(parts[7] or 0)
    except Exception:
        pass

# background GNSS reader is too complex to do in cooperative main loop;
# we just drain the buffer in render loop. NMEA at 1Hz with ~10 sentences
# per fix is ~6-8 kB/s — well within 2kB buffer for a 1s render cadence.
def drain():
    got = 0
    while gnss.any():
        chunk = gnss.read(256)
        if not chunk:
            break
        for line in chunk.split(b"\n"):
            parse(line)
            got += 1
    return got

def fmt_lat(lat):
    if lat == 0.0:
        return "0.0000"
    hemi = "N" if lat >= 0 else "S"
    return "{:>9.4f}{}".format(abs(lat), hemi)

def fmt_lng(lng):
    if lng == 0.0:
        return "0.0000"
    hemi = "E" if lng >= 0 else "W"
    return "{:>9.4f}{}".format(abs(lng), hemi)

# ---- 6) Live page + heartbeat --------------------------------------------
def render():
    tft.fill(BLACK)
    fix = state["fix"]
    fix_color = GREEN if fix >= 1 else RED
    fix_lbl = {0: "NO FIX", 1: "FIX  ", 2: "DGPS "}.get(fix, "?????")
    tft.text8x8(0,   0, "GNSS", WHITE, BLACK)
    tft.text8x8(0,  10, fix_lbl, fix_color, BLACK)
    tft.text8x8(0,  22, "SAT  {:>2d}".format(state["sats"]), CYAN, BLACK)
    tft.text8x8(0,  36, state["time"][:6] or "------", YELLOW, BLACK)
    tft.text8x8(0,  50, "LAT",  WHITE, BLACK)
    tft.text8x8(0,  60, fmt_lat(state["lat"]), GREEN if fix else GREY, BLACK)
    tft.text8x8(0,  74, "LNG",  WHITE, BLACK)
    tft.text8x8(0,  84, fmt_lng(state["lng"]), GREEN if fix else GREY, BLACK)
    tft.text8x8(0,  98, "SPD",  WHITE, BLACK)
    tft.text8x8(0, 108, "{:>5.1f} kt".format(state["spd"]), GREEN if fix else GREY, BLACK)
    tft.text8x8(0, 122, "DATE", WHITE, BLACK)
    tft.text8x8(0, 132, state["date"] or "------", YELLOW, BLACK)
    tft.text8x8(0, 148, BOARD_NAME[:10], CYAN, BLACK)

print(BOARD_NAME)
print("Vext on GPIO3, GNSS RST=GPIO{}, UART2(tx={}, rx={})@{}".format(
      GNSS_RST, GNSS_RX, GNSS_TX, GNSS_BAUD))
print("Backlight flashes at 1 Hz. Press Ctrl-C to stop.")

last_blink = time.ticks_ms()
led_on = True
backlight.value(0)
last_render = 0
while True:
    now = time.ticks_ms()
    if time.ticks_diff(now, last_blink) >= 500:
        last_blink = now
        led_on = not led_on
        backlight.value(0 if led_on else 1)
    if time.ticks_diff(now, last_render) >= 1000:
        last_render = now
        n = drain()
        render()
        print("[{}.{}] fix={} sats={} lat={:.5f} lng={:.5f} spd={:.1f}kt n={}".format(
              state["time"][:6], state["date"][:6], state["fix"], state["sats"],
              state["lat"], state["lng"], state["spd"], n))
