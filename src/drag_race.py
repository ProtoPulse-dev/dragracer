"""
drag_race.py — drag-race timer / speed-trap for Heltec Wireless Tracker V2.

Ported from `gemini-code-1781031318090.py` (ST7735 160x80, UART1, etc.)
to the actual hardware:
   * Univision N096-1608TBBIG09-C08 80x160 panel, driven by an ST7735S
     (NOT an ST7789 as the Heltec wiki implies). The ST7789 driver in
     `src/st7789.py` shares the SPI/MADCTL command set with the ST7735S
     and runs the full ST7735S init sequence (frame-rate, inversion,
     power, Vcom, and 16-step gamma) automatically on construction.
     Without that init the panel comes up with dull, washed-out colours.
   * Panel is used in **landscape 160x80** to match the simulator in
     `gemini-code-1781045946055.html`. The working combination is
     `width=160, height=80, xstart=0, ystart=27, rotation=5`; see the
     `PANEL_*` constants below for the full rationale.
   * GNSS on UART2 (tx=GPIO34, rx=GPIO33) at 115200 baud.
   * GNSS reset on GPIO35 (active LOW, pulsed at boot).
   * Active-low USER_SW on GPIO0 to switch screens / clear state.
   * Backlight on GPIO21 (active LOW).
   * Vext rail on GPIO3, must be HIGH to power the GNSS.

State machine:
   WAI  - waiting, speed < START_SPEED.
   RUN  - timing: clock started when speed crossed START_SPEED.
   COO  - cool-down, waiting for speed to drop below RESET_SPEED.
At the end of a RUN, the elapsed time (start -> end speed) is written to
`runs.csv` on the flash filesystem and is also shown on the INFO screen.

The original code uses PCAS02 to set the GNSS to 10 Hz. The UC6580
doesn't support PCAS - that command is for the AT6558R. For the UC6580
the equivalent is `$PAIR062*0B\r\n` to enable all NMEA messages at 1 Hz.
Sent on boot; harmless if the receiver doesn't understand it.
"""
import machine
import time
import network
import socket
import framebuf
import os

# Bump CPU to 240 MHz for fast SPI frame blits
try:
    machine.freq(240_000_000)
except Exception:
    pass

from heltec_tracker_v2 import (
    TFT_CS, TFT_SCLK, TFT_MOSI, TFT_RS, TFT_RST, TFT_BL,
    VEXT_CTRL, GNSS_RST, GNSS_TX, GNSS_RX, GNSS_BAUD, USR_BTN,
)
from st7735s import ST7735S
import font8x8

# ---- configuration ---------------------------------------------------------
WIFI_SSID = "GPS_TIMER_ESP32"
WIFI_PASS = "12345678"
# Defaults baked into the firmware. The web `/config?…` endpoint can
# override these at runtime by writing CONFIG_FILE on flash; the values
# are reloaded on every boot.
START_SPEED_DEF = 60.0   # km/h - start the timer when crossing this speed
END_SPEED_DEF   = 120.0  # km/h - stop the timer at this speed
RESET_SPEED_DEF = 55.0   # km/h - below this, go back to WAI
LOG_FILE    = "runs.csv"
CONFIG_FILE = "config.json"

# Active thresholds - mutable, read by the FSM each iteration. Loaded
# from CONFIG_FILE in the boot block below; defaults apply if no file.
_CFG = {"start": START_SPEED_DEF, "end": END_SPEED_DEF, "reset": RESET_SPEED_DEF}

# Drop a RUN to COO if no valid GNRMC speed arrives for this many ms.
GNSS_STALE_MS = 2000

# ---- screen-rotation and panel-correction constants -----------------------
# The N096-1608TBBIG09-C08 glass is 80x160 pixels physical. We use it in
# landscape 160x80 to match the simulator. The MADCTL rotation table in
# `st7789.py` is:
#     r=0  MY=0  MX=0  MV=0   BGR              portrait, no mirror
#     r=1  MY=0  MX=0  MV=1   BGR              landscape, horizontal mirror
#     r=2  MY=1  MX=1  MV=0   BGR              portrait, 180 deg
#     r=3  MY=0  MX=1  MV=1   BGR              landscape, both mirrors
#     r=4  MY=1  MX=1  MV=1   BGR              landscape, 180 deg
#     r=5  MY=1  MX=0  MV=1   BGR              landscape, vertical mirror only
# On this glass the framebuffer's (0,0) maps to the physical top-left of
# the panel only with `rotation=5` - USB-C on the left, antenna on the
# right. All other rotations either mirror the image (r=1, r=3) or rotate
# it 180 deg (r=4). r=0/r=2 are portrait and would waste 80x80 of the
# framebuffer. The combination is unique to this ST7735S glass; on a
# different panel you'd need a different `rotation`.
# Landscape (drag-race UI): the N096-1608TBBIG09-C08 panel has 27
# non-display cells in the source driver (cols 0..25 inactive + 1
# stuck-on col at 26). The gate driver has 162 outputs with 160
# active rows.
#
# In landscape (MV=1), the panel hardware swaps which axis CASET
# vs RASET address. The API convention is "xstart" = the source
# (column) offset and "ystart" = the gate (row) offset. The user
# passes the offsets in the same order regardless of rotation;
# the driver feeds them to CASET/RASET and the MV bit handles
# the axis swap in hardware.
#
#   xstart = 0   (no gate row offset in landscape)
#   ystart = 26  (skip 27 stuck source cols - this is the RASET
#                offset, which MV=1 maps to the source driver)
#   rotation = 5 (MV|MY|BGR, landscape, USB-C on the left)
#
# The framebuffer is 160x80 to match the simulator. The panel
# can display 80 active source cols and 160 active gate rows
# in landscape, so the framebuffer fits exactly with no
# off-screen content.
PANEL_WIDTH  = 160
PANEL_HEIGHT = 80
PANEL_XSTART = 0
PANEL_YSTART = 26
PANEL_ROTATION = 5

# Backlight is active-low on GPIO21: 0 = on, 1 = off.
BL_ACTIVE_HIGH = False
# VEXT_CTRL is active-high: 1 powers the rail.
VEXT_ACTIVE_HIGH = True

# ST7735S colour correction: the panel's colour response is not perfectly
# linear, and the "muted" gamma curve that `st7789.py` programs at init
# time tends to make blue/cyan look duller than the simulator (which
# targets a typical sRGB display). A flat multiplicative gain is useless
# for saturated colours (the channels are already at 0x1F/0x3F so they
# just clip), so we apply a small pre-gamma curve that lifts mid-tones
# plus a per-channel bias that targets the visible difference.
#
# Tuned against the on-device gamma tuner (`tests/gamma_tuner.py`) so the
# UI matches the colours the simulator in `gemini-code-1781045946055.html`
# shows on a typical sRGB panel. The exact numbers are not critical -
# what matters is that the corrections are *applied* in a way that
# actually changes saturated colours (a flat gain has no effect on
# RED/GREEN/BLUE/WHITE/YELLOW because all their channels are full-scale).
COLOR_BIAS_R = 0.00   # 0..1: lift the floor for the red channel
COLOR_BIAS_G = 0.00   # 0..1: lift the floor for the green channel
COLOR_BIAS_B = 0.18   # 0..1: lift the floor for the blue channel
COLOR_GAMMA  = 1.10   # > 1 lifts mid-tones (gentle sRGB pre-compensation)

def _lift(c, n, bias):
    """Lift a single channel by `bias` and apply a power-curve gamma.

    If the input is zero, the channel is left as zero so that the bias
    does not add a floor to black.
    """
    if c == 0:
        return 0
    v = c / float(n)
    v = v * (1.0 - bias) + bias
    v = v ** (1.0 / COLOR_GAMMA)
    return min(n, max(0, int(round(v * n))))

def color_correct(rgb565):
    """Apply the per-channel bias + gamma to an RGB565 colour."""
    r = (rgb565 >> 11) & 0x1F
    g = (rgb565 >> 5)  & 0x3F
    b =  rgb565        & 0x1F
    r = _lift(r, 0x1F, COLOR_BIAS_R)
    g = _lift(g, 0x3F, COLOR_BIAS_G)
    b = _lift(b, 0x1F, COLOR_BIAS_B)
    return (r << 11) | (g << 5) | b

# Reusable base palette. The pre-corrected values are what the framebuffer
# sees; the panel will then apply its own ST7735S gamma so the final
# perceived colour matches the simulator.
def _palette():
    base = {
        "BLACK":  0x0000,
        "WHITE":  0xFFFF,
        "GREEN":  0x07E0,
        "RED":    0xF800,
        "BLUE":   0x001F,
        "YELLOW": 0xFFE0,
        "GRAY":   0x8410,
        "CYAN":   0x07FF,
        "MAGENTA":0xF81F,
    }
    return {name: color_correct(rgb) for name, rgb in base.items()}

_pal = _palette()
BLACK   = _pal["BLACK"]
WHITE   = _pal["WHITE"]
GREEN   = _pal["GREEN"]
RED     = _pal["RED"]
BLUE    = _pal["BLUE"]
YELLOW  = _pal["YELLOW"]
GRAY    = _pal["GRAY"]
CYAN    = _pal["CYAN"]
MAGENTA = _pal["MAGENTA"]

# ---- 1) hardware init ------------------------------------------------------
vext = machine.Pin(VEXT_CTRL, machine.Pin.OUT,
                   value=1 if VEXT_ACTIVE_HIGH else 0)
time.sleep_ms(50)

spi = machine.SPI(2, baudrate=20_000_000, polarity=0, phase=0,
                  sck=machine.Pin(TFT_SCLK), mosi=machine.Pin(TFT_MOSI), miso=machine.Pin(2))
tft = ST7735S(spi,
              cs=machine.Pin(TFT_CS, machine.Pin.OUT, value=1),
              dc=machine.Pin(TFT_RS, machine.Pin.OUT, value=0),
              rst=machine.Pin(TFT_RST, machine.Pin.OUT, value=1),
              bl=None,
              width=PANEL_WIDTH, height=PANEL_HEIGHT,
              xstart=PANEL_XSTART, ystart=PANEL_YSTART,
              rotation=PANEL_ROTATION)

# Backlight: the ST7735S driver no longer manages this pin, so set it
# explicitly here.  Active-low: 0 = on.
backlight = machine.Pin(TFT_BL, machine.Pin.OUT, value=0)

# Reset the UC6580: hold nRESET LOW for 100ms, release
gnss_rst = machine.Pin(GNSS_RST, machine.Pin.OUT, value=1)
gnss_rst.value(0); time.sleep_ms(100); gnss_rst.value(1)
time.sleep_ms(300)

# UART2: ESP tx=34, ESP rx=33 (UC6580's RX_IN / TX_OUT)
gps_uart = machine.UART(2, baudrate=GNSS_BAUD, tx=GNSS_RX, rx=GNSS_TX,
                        bits=8, parity=None, stop=1, timeout=50, rxbuf=2048)
# Some GNSS messages (UC6580 responds to PAIR, AT6558 to PCAS) - try both
gps_uart.write(b'$PAIR062,1,1,1,1,1,1,0,0,0,0,0,0,0,0*3B\r\n')  # UC6580
gps_uart.write(b'$PCAS02,100*1E\r\n')  # AT6558-style (no-op on UC6580)
time.sleep_ms(100)

# USER button (active LOW)
btn_prg = machine.Pin(USR_BTN, machine.Pin.IN, machine.Pin.PULL_UP)

# ---- 2) framebuffer-backed ST7735-style draw API -------------------------
# (The original code used an ST7735 framebuffer; we keep the same surface
#  API but back it with the ST7789 panel.)
class FBDisplay(framebuf.FrameBuffer):
    def __init__(self, w, h):
        self.width = self.w = w
        self.height = self.h = h
        self.buf = bytearray(w * h * 2)
        super().__init__(self.buf, w, h, framebuf.RGB565)
    def show(self):
        tft.show_framebuf(self)

disp = FBDisplay(PANEL_WIDTH, PANEL_HEIGHT)

# 8x8 font buffer, used by `draw_big_text` to scale glyphs up
_char_buf = bytearray(8)
_char_fb  = framebuf.FrameBuffer(_char_buf, 8, 8, framebuf.MONO_HLSB)

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
    """Right-align a string of big text so its right edge sits at x_end.

    Glyphs are drawn left-to-right starting at the computed x. Useful
    for numeric readouts that need a fixed right edge so the value
    doesn't wobble as digits change.
    """
    glyph_w = 8 * scale
    x = x_end - glyph_w * len(s) + 1
    draw_big_text(s, x, y, color, scale)

# text uses the 8x8 font module we already have on the device
def text8(s, x, y, color, bg=None):
    for i, ch in enumerate(s):
        cx = x + i*8
        if 0 <= cx < disp.w and 0 <= y < disp.h:
            if bg is not None:
                disp.fill_rect(cx, y, 8, 8, bg)
            font8x8.draw_char(disp, ch, cx, y, color)

# ---- 3) NMEA parser --------------------------------------------------------
state = "WAI"   # WAI | RUN | COO
start_time_ms = 0
current_speed = 0.0
current_timer = 0.0
satellites    = 0
fix_quality   = 0  # 0=none, 1=fix, 2=DGPS

best_time   = 0.0
recent_runs = []
current_screen = 0  # 0 = "Rijden", 1 = "Info"
last_display_update = 0
last_web_handle = 0

# GNSS liveness: updated whenever parse_nmea() consumes a valid GNRMC
# speed sentence. Used by the dropout guard in the main FSM loop.
last_speed_ms = 0
# Most recent UTC fix time, formatted as YYYY-MM-DDTHH:MM:SSZ. Empty
# until a valid GNRMC arrives; written into runs.csv so each row is
# self-describing off the device.
last_fix_utc = ""
# Non-blocking button long-press flash. The 10 Hz redraw loop honours
# these instead of a time.sleep_ms() so NMEA is not dropped.
flash_until_ms = 0
flash_color     = BLACK

# Initialise log file (if absent, write the header) and seed best_time
# + recent_runs from the most recent rows so they survive a power cycle.
try:
    with open(LOG_FILE, "r") as f: pass
except OSError:
    with open(LOG_FILE, "w") as f:
        f.write("IsoUtc,RunTime_Sec,BestSoFar_Sec\n")

def _boot_load_state():
    """Read runs.csv tail, seed best_time + recent_runs from it.

    The CSV is append-only and the third column is BestSoFar_Sec at the
    moment the run completed, so the largest value in column 3 is the
    best run ever recorded, and the last 3 values in column 2 are the
    recent runs. Wrapped in OSError so a missing or half-written file
    is fine.
    """
    global best_time, recent_runs
    try:
        with open(LOG_FILE, "r") as f:
            rows = [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return
    # skip header
    rows = [r for r in rows if not r.startswith("IsoUtc")]
    times = []
    for r in rows:
        parts = r.split(",")
        if len(parts) < 2:
            continue
        try:
            times.append(float(parts[1]))
        except ValueError:
            pass
    if not times:
        return
    recent_runs = times[-3:][::-1]   # most-recent first
    # Best: BestSoFar_Sec is the cumulative best at the time of the
    # run, so the list is monotonic non-increasing and the last entry
    # is the global best. Fall back to the smallest time we parsed
    # if the column is missing on every row.
    bests = []
    for r in rows:
        parts = r.split(",")
        if len(parts) < 3:
            continue
        try:
            bests.append(float(parts[2]))
        except ValueError:
            pass
    best_time = bests[-1] if bests else min(times)

_boot_load_state()

# Load config.json if present, otherwise leave _CFG at defaults.
def _clamp_cfg(cfg):
    """Clamp thresholds to sane bounds. Returns the same dict (mutated)."""
    cfg["start"] = max(5.0,  min(200.0, float(cfg.get("start", START_SPEED_DEF))))
    cfg["end"]   = max(10.0, min(300.0, float(cfg.get("end",   END_SPEED_DEF))))
    cfg["reset"] = max(0.0,  min(cfg["start"] - 1.0, float(cfg.get("reset", RESET_SPEED_DEF))))
    return cfg

def _load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            data = f.read()
    except OSError:
        return _clamp_cfg(_CFG)
    # MicroPython's `json` is available; parse minimally by hand to
    # avoid the dependency.
    out = {"start": START_SPEED_DEF, "end": END_SPEED_DEF, "reset": RESET_SPEED_DEF}
    for key in ("start", "end", "reset"):
        i = data.find('"%s"' % key)
        if i < 0:
            continue
        j = data.find(":", i)
        k = data.find(",", j)
        if k < 0: k = data.find("}", j)
        try:
            out[key] = float(data[j+1:k].strip())
        except ValueError:
            pass
    return _clamp_cfg(out)

_CFG = _load_config()
print("config: start=%.0f end=%.0f reset=%.0f km/h" % (
    _CFG["start"], _CFG["end"], _CFG["reset"]))

def _save_config(cfg):
    """Persist the current thresholds to CONFIG_FILE on flash."""
    body = '{"start": %.1f, "end": %.1f, "reset": %.1f}\n' % (
        cfg["start"], cfg["end"], cfg["reset"])
    try:
        with open(CONFIG_FILE, "w") as f:
            f.write(body)
    except OSError as e:
        print("cfg err:", e)

def _format_utc(hhmmss, ddmmyy):
    """Build an ISO-8601 UTC string from GNRMC parts[1] and parts[9].

    NMEA date is DDMMYY (20YY); time is HHMMSS (UTC). Returns "" on any
    parse error so callers can fall back to "no-fix".
    """
    if not hhmmss or not ddmmyy or len(hhmmss) < 6 or len(ddmmyy) < 6:
        return ""
    try:
        hh = int(hhmmss[0:2]); mm = int(hhmmss[2:4]); ss = int(hhmmss[4:6])
        dd = int(ddmmyy[0:2]); mo = int(ddmmyy[2:4]); yy = int(ddmmyy[4:6]) + 2000
        return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (yy, mo, dd, hh, mm, ss)
    except ValueError:
        return ""

def parse_nmea(line):
    global current_speed, satellites, fix_quality, last_fix_utc, last_speed_ms
    try:
        s = line.decode("utf-8", "ignore").strip()
    except Exception:
        return
    if not s.startswith("$"):
        return
    body = s.lstrip("$").split("*")[0]
    parts = body.split(",")
    typ = parts[0]
    try:
        if typ in ("GNRMC", "GPRMC"):
            # Stamp the wall-clock fix and the liveness timer on every
            # RMC sentence, valid or not, so the dropout guard sees
            # fresh data even when the receiver is still hunting a fix
            # (the speed is just not updated in that case).
            if len(parts) > 9:
                last_fix_utc = _format_utc(parts[1], parts[9]) or last_fix_utc
            last_speed_ms = time.ticks_ms()
            if len(parts) > 7 and parts[2] == "A" and parts[7]:
                # NMEA speed is in knots; convert to km/h
                current_speed = float(parts[7]) * 1.852
        elif typ in ("GNGGA", "GPGGA"):
            if len(parts) > 7:
                if parts[6]: fix_quality = int(parts[6])
                if parts[7]: satellites  = int(parts[7])
    except Exception:
        pass

# ---- 4) UI -----------------------------------------------------------------
def update_tft():
    # Long-press button feedback: solid colour until flash_until_ms
    # expires. Honours the 10Hz tick so NMEA isn't dropped.
    if time.ticks_diff(time.ticks_ms(), flash_until_ms) < 0:
        disp.fill(flash_color)
        disp.show()
        return
    disp.fill(BLACK)
    if current_screen == 0:
        # ---- Driving screen: 160x80 landscape ------------------------
        # Layout:
        #   y=0..11   status bar (state label, sats, status dot)
        #   y=12      hairline
        #   y=14..37  speed value (scale-3, fixed 5 chars, right edge at 155)
        #   y=47      hairline
        #   y=50..73  timer value (scale-3, fixed 5 chars, right edge at 155)
        #
        # The fixed 5-char format "SSSS.S" / "TTTT.T" means the right
        # edge never moves as the digits change, so the readout stays
        # rock-steady.
        #
        # Status bar
        if state == "WAI":
            state_lbl, dot_color = "READY", GREEN
        elif state == "RUN":
            state_lbl, dot_color = "RUN  ", RED
        else:
            state_lbl, dot_color = "COOL ", BLUE
        text8(state_lbl, 0, 2, dot_color, BLACK)
        text8("SAT %2d" % min(satellites, 99), 60, 2, GRAY, BLACK)
        disp.fill_rect(148, 2, 10, 10, dot_color)
        # Header hairline
        disp.hline(0, 12, PANEL_WIDTH, GRAY)
        # Speed value
        speed_color = WHITE if state != "WAI" else WHITE
        speed_str = "%5.1f" % current_speed      # fixed 5 chars
        draw_big_text_right(speed_str, PANEL_WIDTH - 5, 14, speed_color, scale=3)
        text8("km/h", 0,  30, GRAY, BLACK)
        # Speed/timer divider
        disp.hline(0, 47, PANEL_WIDTH, GRAY)
        # Timer value
        timer_color = RED if state == "RUN" else WHITE
        timer_str = "%5.1f" % current_timer      # fixed 5 chars
        draw_big_text_right(timer_str, PANEL_WIDTH - 5, 50, timer_color, scale=3)
        text8("sec",  0,  66, GRAY, BLACK)
    else:
        # ---- Info screen: 160x80 landscape --------------------------
        # Header bar 0..11 (title + sat count), hairline at 12, then
        # a 2-column grid: left = best run + current speed, right =
        # last 3 runs. Vertical divider at x=80.
        text8("INFO",       0,  2, BLUE, BLACK)
        text8("SAT %2d" % min(satellites, 99), 60, 2, GRAY, BLACK)
        text8("BEST",      120, 2, GRAY, BLACK)
        disp.hline(0, 12, PANEL_WIDTH, GRAY)
        # Left column
        text8("BEST RUN",  4, 16, GRAY, BLACK)
        best_str = "%.2fs" % best_time if best_time > 0 else "--.-s"
        draw_big_text_right(best_str, 76, 22, GREEN, scale=2)
        text8("HUIDIG",    4, 46, GRAY, BLACK)
        text8("%5.1f km/h" % current_speed, 4, 56, WHITE, BLACK)
        # Vertical divider
        disp.vline(80, 12, 68, GRAY)
        # Right column: last 3 runs, with rank + value, scale-1.
        text8("LAATSTE",  84, 16, GRAY, BLACK)
        y_pos = 26
        if not recent_runs:
            text8("Geen data", 84, y_pos, GRAY, BLACK)
        else:
            for i, run in enumerate(recent_runs[:3]):
                # "1. 7.20s"  - rank, dots, value. Value is right-aligned
                # to x=156 so the digits line up regardless of width.
                rank_str = "%d." % (i + 1)
                text8(rank_str, 84, y_pos, GRAY, BLACK)
                val_str = "%.2fs" % run
                draw_big_text_right(val_str, PANEL_WIDTH - 4, y_pos, WHITE, scale=1)
                y_pos += 14
    disp.show()

# ---- 5) webserver (read-only log dump) -------------------------------------
ap = network.WLAN(network.AP_IF)
ap.config(essid=WIFI_SSID, password=WIFI_PASS)
ap.active(True)
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("", 80))
srv.listen(1)
srv.settimeout(0)  # non-blocking accept

def _http_response(status, body, content_type="text/html"):
    return ("HTTP/1.1 %s\r\n"
            "Content-Type: %s\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n\r\n" % (status, content_type)).encode() + body

def _runs_page():
    try:
        with open(LOG_FILE, "r") as f:
            data = f.read()
    except OSError:
        data = "Geen data"
    return _http_response("200 OK",
        b"<html><body><h1>Tracker Runs</h1><pre>" +
        data.encode() + b"</pre></body></html>")

def _config_get():
    body = '{"start": %.1f, "end": %.1f, "reset": %.1f}' % (
        _CFG["start"], _CFG["end"], _CFG["reset"])
    return _http_response("200 OK", body.encode(), "application/json")

def _config_set(query):
    """Parse /config?start=..&end=..&reset=.., update _CFG, persist."""
    global _CFG
    new = dict(_CFG)
    for kv in query.split("&"):
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        if k not in ("start", "end", "reset"):
            continue
        try:
            new[k] = float(v)
        except ValueError:
            pass
    _CFG = _clamp_cfg(new)
    _save_config(_CFG)
    msg = ("OK start=%.0f end=%.0f reset=%.0f" % (
        _CFG["start"], _CFG["end"], _CFG["reset"])).encode()
    return _http_response("200 OK",
        b"<html><body><h1>Config saved</h1><pre>" + msg +
        b"</pre></body></html>")

def handle_web():
    try:
        cl, _ = srv.accept()
    except OSError:
        return
    try:
        cl.settimeout(0.1)
        req = cl.recv(1024)
        if not req:
            return
        try:
            first = req.decode("utf-8", "ignore").split(" ", 2)
            if len(first) < 2:
                return
            method, target = first[0], first[1]
        except Exception:
            return
        # path + query split
        if "?" in target:
            path, query = target.split("?", 1)
        else:
            path, query = target, ""
        path = path.split("#", 1)[0]
        if method == "GET" and path == "/config" and query:
            resp = _config_set(query)
        elif method == "GET" and path == "/config":
            resp = _config_get()
        elif method == "GET" and path == "/":
            resp = _runs_page()
        else:
            resp = _http_response("404 Not Found", b"<h1>404</h1>")
        cl.send(resp)
    except OSError:
        pass
    finally:
        try: cl.close()
        except Exception: pass

# ---- 6) main loop ----------------------------------------------------------
btn_pressed   = False
press_start   = 0
cleared_list  = False
cleared_best  = False

# initial paint
update_tft()

print("Drag-race timer running.")
print("Panel:", PANEL_WIDTH, "x", PANEL_HEIGHT,
      "xstart=", PANEL_XSTART, "ystart=", PANEL_YSTART,
      "rotation=", PANEL_ROTATION)
print("WIFI AP:", WIFI_SSID, "/", WIFI_PASS)
print("Hold USER_SW to clear runs (>=2s) or reset best (>=5s).")

while True:
    now = time.ticks_ms()

    # 1) button
    btn_state = (btn_prg.value() == 0)  # active low
    if btn_state and not btn_pressed:
        btn_pressed = True
        press_start = now
        cleared_list = cleared_best = False
    elif btn_state and btn_pressed:
        hold = time.ticks_diff(now, press_start)
        if hold >= 5000 and not cleared_best:
            cleared_best = True
            best_time = 0.0
            recent_runs = []
            flash_color = RED
            flash_until_ms = time.ticks_ms() + 150
        elif 2000 <= hold < 5000 and not cleared_list:
            cleared_list = True
            recent_runs = []
            flash_color = YELLOW
            flash_until_ms = time.ticks_ms() + 150
    elif not btn_state and btn_pressed:
        btn_pressed = False
        if time.ticks_diff(now, press_start) < 2000:
            current_screen = 1 - current_screen

    # 2) GPS read (drain in chunks, not one line at a time)
    if gps_uart.any():
        chunk = gps_uart.read(256)
        if chunk:
            for line in chunk.split(b"\n"):
                if line:
                    parse_nmea(line)

    # 3) state machine
    # Dropout guard: if we lost GNSS mid-RUN, fall back to COO without
    # logging so a stalled run doesn't trap the device at e.g. 119 km/h.
    if state == "RUN" and time.ticks_diff(now, last_speed_ms) > GNSS_STALE_MS:
        state = "COO"
    if state == "WAI":
        current_timer = 0.0
        if current_speed >= _CFG["start"]:
            start_time_ms = now
            state = "RUN"
            current_screen = 0
    elif state == "RUN":
        current_timer = time.ticks_diff(now, start_time_ms) / 1000.0
        if current_speed >= _CFG["end"]:
            final_time = current_timer
            if best_time == 0.0 or final_time < best_time:
                best_time = final_time
            recent_runs.insert(0, final_time)
            if len(recent_runs) > 3:
                recent_runs.pop()
            try:
                with open(LOG_FILE, "a") as f:
                    f.write("%s,%.2f,%.2f\n" % (
                        last_fix_utc or "no-fix", final_time, best_time))
            except OSError as e:
                print("log err:", e)
            state = "COO"
    elif state == "COO":
        if current_speed < _CFG["reset"]:
            state = "WAI"

    # 4) redraw (max 10 Hz)
    if time.ticks_diff(now, last_display_update) >= 100:
        last_display_update = now
        update_tft()

    # 5) webserver (non-blocking)
    if time.ticks_diff(now, last_web_handle) >= 200:
        last_web_handle = now
        handle_web()
