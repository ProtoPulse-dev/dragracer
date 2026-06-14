"""
ST7735S driver for the Heltec Wireless Tracker V2 (Rev 2.0).

SPDX-FileCopyrightText: 2026 ProtoPulse-dev
SPDX-License-Identifier: MIT

The init-sequence structure and command constants are derived from Adafruit's
ST7735 family drivers:
  - Adafruit CircuitPython ST7735R (MIT)
    https://github.com/adafruit/Adafruit_CircuitPython_ST7735R
  - Adafruit Arduino ST7735 (MIT)
    https://github.com/adafruit/Adafruit-ST7735-Library
The rotation/offset handling was inspired by boochow's MicroPython-ST7735:
  https://github.com/boochow/MicroPython-ST7735
The gamma tables, panel-specific offsets, and partial-mode removal are local
modifications for the Univision N096-1608TBBIG09-C08 80x160 panel on the
Heltec Wireless Tracker V2.

Despite the legacy filename, the actual glass on this board is the Univision
N096-1608TBBIG09-C08 80x160 panel driven by an **ST7735S**
(see Heltec datasheet under plans/). The ST7789 and ST7735S share the
same SPI/MADCTL/CASET/RASET/RAMWR command set, so the same driver
works for both, but the ST7735S needs a longer init sequence with
gamma and power tables or the colours come out dull.

API
---
    tft = ST7789(spi, cs, dc, rst, bl=None,
                 width=80, height=160,        # native portrait
                 xstart=26, ystart=0,         # panel offset
                 rotation=0)
    tft.fill(color)
    tft.fill_rect(x, y, w, h, color)
    tft.pixel(x, y, color)
    tft.text8x8(x, y, "Hi", color)
"""
from micropython import const
import time

_SWRESET = const(0x01)
_SLPOUT  = const(0x11)
_PTLON   = const(0x12)   # Partial Display Mode ON
_NORON   = const(0x13)   # Normal Display Mode ON
_PTLAR   = const(0x30)   # Partial Area (set partial display window)
_COLMOD  = const(0x3A)
_MADCTL  = const(0x36)
_INVON   = const(0x21)
_INVOFF  = const(0x20)
_DISPON  = const(0x29)
_TEOFF   = const(0x34)   # Tearing Effect Line OFF
_CASET   = const(0x2A)
_RASET   = const(0x2B)
_RAMWR   = const(0x2C)
# ST7735S-specific commands
_FRMCTR1 = const(0xB1)
_FRMCTR2 = const(0xB2)
_FRMCTR3 = const(0xB3)
_INVCTR  = const(0xB4)
_PWCTR1  = const(0xC0)
_PWCTR2  = const(0xC1)
_PWCTR3  = const(0xC2)
_PWCTR4  = const(0xC3)
_PWCTR5  = const(0xC4)
_VMCTR1  = const(0xC5)
_GMCTRP1 = const(0xE0)
_GMCTRN1 = const(0xE1)

_MADCTL_MY  = const(0x80)
_MADCTL_MX  = const(0x40)
_MADCTL_MV  = const(0x20)
_MADCTL_ML  = const(0x10)
_MADCTL_BGR = const(0x08)


def _safe_init(pin, mode, value):
    try:
        pin.init(mode, value=value)
    except TypeError:
        pin.value(value)


class ST7735S:
    def __init__(self, spi, cs, dc, rst=None, bl=None,
                 width=80, height=160,
                 xstart=26, ystart=0,
                 rotation=0, baudrate=40_000_000):
        self.spi  = spi
        self.cs   = cs
        self.dc   = dc
        self.rst  = rst
        self.bl   = bl
        self.width  = width
        self.height = height
        # `xstart` and `ystart` are the *portrait* column/row offsets
        # (`colstart`, `rowstart` in Adafruit terminology). For
        # landscape rotations the axis-swap is applied inside
        # `_apply_rotation` so the right offset lands on the right
        # physical axis without the caller having to know about MV.
        self._colstart = xstart
        self._rowstart = ystart
        self._bgr = True
        self._rotation = rotation
        self._baudrate = baudrate
        # Default the active offsets to the portrait values;
        # `_apply_rotation` will overwrite them for MV=1 rotations.
        self._xstart = xstart
        self._ystart = ystart

        self.spi.init(baudrate=baudrate, polarity=0, phase=0,
                      bits=8, firstbit=self.spi.MSB)
        _safe_init(self.cs, self.cs.OUT, 1)
        _safe_init(self.dc, self.dc.OUT, 0)
        if self.rst is not None:
            _safe_init(self.rst, self.rst.OUT, 1)
        if self.bl is not None:
            _safe_init(self.bl, self.bl.OUT, 1)

        if self.rst is not None:
            self.rst.value(0); time.sleep_ms(50)
            self.rst.value(1); time.sleep_ms(150)

        self._write_cmd(_SWRESET); time.sleep_ms(150)
        self._write_cmd(_SLPOUT);  time.sleep_ms(120)

        # --- ST7735S frame-rate controls (normal / idle / partial) -----
        self._write_cmd(_FRMCTR1); self._write_data(b"\x01\x2C\x2D")
        self._write_cmd(_FRMCTR2); self._write_data(b"\x01\x2C\x2D")
        self._write_cmd(_FRMCTR3); self._write_data(b"\x01\x2C\x2D\x01\x2C\x2D")
        # Display inversion control: line-inversion in normal mode
        self._write_cmd(_INVCTR);  self._write_data(b"\x07")
        # --- Power / Vcom ----------------------------------------------------
        self._write_cmd(_PWCTR1);  self._write_data(b"\xA2\x02\x84")
        self._write_cmd(_PWCTR2);  self._write_data(b"\xC5")
        self._write_cmd(_PWCTR3);  self._write_data(b"\x0A\x00")
        self._write_cmd(_PWCTR4);  self._write_data(b"\x8A\x2A")
        self._write_cmd(_PWCTR5);  self._write_data(b"\x8A\xEE")
        self._write_cmd(_VMCTR1);  self._write_data(b"\x06")
        # Disable inversion
        self._write_cmd(_INVOFF)
        # --- Gamma tables ("muted" low-gain values) -------------------------
        # These produce less saturated / less over-bright colors than the
        # stock Red/Green/Black-tab tables on this particular N096 ST7735S.
        self._write_cmd(_GMCTRP1)
        self._write_data(bytes([0x0F,0x15,0x0F,0x0B,0x09,0x08,0x09,0x0C,
                                0x0E,0x10,0x12,0x14,0x06,0x08,0x04,0x03]))
        self._write_cmd(_GMCTRN1)
        self._write_data(bytes([0x0F,0x15,0x0F,0x0B,0x09,0x08,0x09,0x0C,
                                0x0E,0x10,0x12,0x14,0x06,0x08,0x04,0x03]))

        self._write_cmd(_COLMOD);  self._write_data(b"\x55")
        # Turn off tearing-effect line so it doesn't drive stray rows.
        self._write_cmd(_TEOFF)
        # Explicitly enter Normal Display Mode. Without NORON the
        # ST7735S can power up in Partial Display Mode, scanning a
        # window that includes the control rows above the active area
        # -- which shows up as a stuck white line at the top of the
        # panel even though our framebuffer has nothing there.
        self._write_cmd(_NORON); time.sleep_ms(10)
        self._write_cmd(_DISPON); time.sleep_ms(100)
        self._apply_rotation(rotation)
        # Clear the entire panel GRAM (full 132x162) to black so the
        # off-window area below our 80-row framebuffer is not random
        # noise. Bypass `_set_window` (which applies our ystart/xstart
        # offsets) and write the raw CASET/RASET.
        self._write_cmd(_CASET); self._write_data(bytes([0x00, 0x00, 0x00, 0x83]))  # 0..131
        self._write_cmd(_RASET); self._write_data(bytes([0x00, 0x00, 0x00, 0xA1]))  # 0..161
        self._write_cmd(_RAMWR)
        self.cs.value(0); self.dc.value(1)
        zero_line = bytes(132 * 2)
        for _ in range(162):
            self.spi.write(zero_line)
        self.cs.value(1)
        self._apply_rotation(rotation)
        # Clip the panel's scan-out window to skip the noisy/stuck
        # gate rows above the active area. The N096-1608TBBIG09-C08
        # has 162 gate outputs, but the first 27 are non-display
        # (26 un-driven control rows + 1 stuck-on row). With the
        # standard "normal mode" scan, those rows are displayed, so
        # even though we never write to them they show random GRAM
        # contents (= "noisy white"). The fix is to enter Partial
        # Mode (PTLON) after bounding the partial area (PTLAR) to
        # start at gate row 27.
        #
        # In landscape (MV=1) the gate driver is addressed via
        # CASET, so the gate-row offset is `_xstart` (= 27). In
        # portrait (MV=0) the gate is via RASET, so the gate-row
        # offset is `_ystart` (= 26). Either way, the convention
        # is "the offset the user passed as the FIRST arg of the
        # constructor" — `xstart` — is the gate-row offset.
        # NOTE: Partial mode (PTLAR/PTLON) was empirically found to clip
        # the active scan window and leave a black band on the long edge
        # of this panel.  Normal display mode (NORON) with the correct
        # CASET/RASET offsets is sufficient.
        self.fill(0x0000)

    def _write_cmd(self, c):
        self.cs.value(0); self.dc.value(0)
        self.spi.write(bytes([c])); self.cs.value(1)

    def _write_data(self, d):
        self.cs.value(0); self.dc.value(1)
        self.spi.write(d); self.cs.value(1)

    def _set_window(self, x0, y0, x1, y1):
        # CASET/RASET are in *panel* coordinates. The MADCTL rotation
        # is applied by the panel itself; we just translate the
        # framebuffer's (x, y) by the (xstart, ystart) offsets which
        # are pre-swapped by `_apply_rotation` to account for the
        # MV=1 axis swap. Reference: Adafruit ST7735 setAddrWindow.
        x0 += self._xstart; x1 += self._xstart
        y0 += self._ystart; y1 += self._ystart
        self._write_cmd(_CASET)
        self._write_data(bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._write_cmd(_RASET)
        self._write_data(bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
        self._write_cmd(_RAMWR)

    def set_rotation(self, r):
        """Set rotation 0..5 (this panel needs 4 and 5 for landscape)."""
        r = int(r)
        if r < 0 or r > 5:
            r = 0
        self._rotation = r
        c = self._colstart
        s = self._rowstart
        color_bit = _MADCTL_BGR if self._bgr else _MADCTL_RGB
        if   r == 0: m = _MADCTL_MX | _MADCTL_MY | color_bit
        elif r == 1: m = _MADCTL_MY | _MADCTL_MV | color_bit
        elif r == 2: m =                       color_bit
        elif r == 3: m = _MADCTL_MX | _MADCTL_MV | color_bit
        elif r == 4: m = _MADCTL_MX | _MADCTL_MY | _MADCTL_MV | color_bit
        else:        m = _MADCTL_MV | _MADCTL_MY | color_bit
        # Offsets are applied directly to CASET/RASET; the panel's MV bit
        # handles the axis swap in hardware, so the same colstart/rowstart
        # values are used for every rotation.
        self._xstart = c
        self._ystart = s
        self._write_cmd(_MADCTL)
        self._write_data(bytes([m]))

    def _apply_rotation(self, r):
        # ST7735S rotations. The constructor args `xstart` and
        # `ystart` are applied DIRECTLY to CASET and RASET
        # respectively, regardless of the MADCTL rotation bits.
        #
        # The ST7735 datasheet says MV=1 exchanges CASET and RASET
        # in terms of which driver they feed (source vs gate). The
        # driver's MADCTL bits also include MY/MX which mirror each
        # driver's scan direction. The combination of the two means
        # that, empirically on the N096-1608TBBIG09-C08, the offset
        # that the user wants in PORTRAIT goes into CASET (called
        # `xstart` here) and the offset that goes into RASET (called
        # `ystart`) is the offset needed in PORTRAIT for the Y axis.
        # In landscape the SAME `_xstart`/`_ystart` values are used
        # and the panel's MV/MX/MY bit pattern handles the rotation
        # and mirroring in hardware.
        #
        # This matches the boochow MicroPython-ST7735 reference
        # driver and the historical working drag_race.py config of
        # `xstart=0, ystart=26, rotation=5` for the Heltec 80x160
        # panel in landscape.
        colstart = self._colstart
        rowstart = self._rowstart
        if   r == 0: m = _MADCTL_MX | _MADCTL_MY | _MADCTL_BGR
        elif r == 1: m = _MADCTL_MY | _MADCTL_MV | _MADCTL_BGR
        elif r == 2: m =                       _MADCTL_BGR
        elif r == 3: m = _MADCTL_MX | _MADCTL_MV | _MADCTL_BGR
        elif r == 4: m = _MADCTL_MX | _MADCTL_MY | _MADCTL_MV | _MADCTL_BGR
        elif r == 5: m = _MADCTL_MV | _MADCTL_MY | _MADCTL_BGR
        else:        m =                       _MADCTL_BGR
        self._xstart = colstart
        self._ystart = rowstart
        self._write_cmd(_MADCTL); self._write_data(bytes([m]))

    def fill(self, color):
        hi, lo = color >> 8, color & 0xFF
        line = bytes([hi, lo] * self.width)
        self._set_window(0, 0, self.width - 1, self.height - 1)
        self.cs.value(0); self.dc.value(1)
        for _ in range(self.height):
            self.spi.write(line)
        self.cs.value(1)

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0: return
        x0 = max(0, x); y0 = max(0, y)
        x1 = min(self.width  - 1, x + w - 1)
        y1 = min(self.height - 1, y + h - 1)
        if x1 < x0 or y1 < y0: return
        hi, lo = color >> 8, color & 0xFF
        line = bytes([hi, lo] * (x1 - x0 + 1))
        self._set_window(x0, y0, x1, y1)
        self.cs.value(0); self.dc.value(1)
        for _ in range(y1 - y0 + 1):
            self.spi.write(line)
        self.cs.value(1)

    def pixel(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            self._set_window(x, y, x, y)
            self._write_data(bytes([color >> 8, color & 0xFF]))

    def text8x8(self, x, y, s, color=0xFFFF, bg=0x0000):
        from font8x8 import font8x8_basic
        for ch in s:
            code = ord(ch)
            if code < 0x20 or code > 0x7E:
                code = 0x20
            off = (code - 0x20) * 8
            self._blit_glyph(x, y,
                             font8x8_basic[off:off + 8],
                             color, bg)
            x += 8

    def _blit_glyph(self, x, y, glyph_bytes, color, bg):
        for col in range(8):
            bits = glyph_bytes[col]
            for row in range(8):
                if bits & 1:
                    self.pixel(x + col, y + row, color)
                elif bg is not None:
                    self.pixel(x + col, y + row, bg)
                bits >>= 1

    def show_framebuf(self, fb, x=0, y=0, w=None, h=None):
        """Blit a `framebuf.FrameBuffer` in RGB565 mode to the panel.

        `fb.pixel(x, y)` returns a 16-bit colour. We stream the buffer
        row by row so we never materialise a full-size line buffer in RAM.
        """
        if w is None: w = fb.width
        if h is None: h = fb.height
        if (x, y, w, h) == (0, 0, self.width, self.height) \
                and fb.width == self.width and fb.height == self.height:
            # fast path: full-screen blit
            self._set_window(0, 0, self.width - 1, self.height - 1)
            self.cs.value(0); self.dc.value(1)
            # FrameBuffer in RGB565 stores big-endian hi,lo per pixel.
            self.spi.write(fb.buf)
            self.cs.value(1)
            return
        # generic rect blit
        for row in range(h):
            line = bytearray(w * 2)
            for col in range(w):
                c = fb.pixel(col, row)
                line[col*2]   = (c >> 8) & 0xFF
                line[col*2+1] = c & 0xFF
            self._set_window(x, y + row, x + w - 1, y + row)
            self.cs.value(0); self.dc.value(1)
            self.spi.write(line)
            self.cs.value(1)

    def backlight(self, on=True):
        if self.bl is not None:
            # Backlight is active-low on this board.
            self.bl.value(0 if on else 1)
