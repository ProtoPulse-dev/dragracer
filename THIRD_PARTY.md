# Third-party software

This project includes code derived from or copied from other open-source
projects. All original licenses and copyright notices are preserved below.

## SX1262 LoRa driver

- **Files affected:** `src/_sx126x.py`, `src/sx126x.py`, `src/sx1262.py`
- **Original project:** `micropySX126X`
- **Source:** https://github.com/ehong-tl/micropySX126X
- **Original author:** E H Ong (port from RadioLib by Jan Gromeš)
- **License:** MIT
- **Local modifications:**
  - Added `SoftSPI` support for the Heltec Wireless Tracker V2 (SX1262 on
    GPIO 8/9/10/11, not exposed as a hardware SPI channel in MicroPython).
  - Rewrote `SPItransfer()` to use single-byte full-duplex transfers, because
    MicroPython `SoftSPI.read()` does not honour the outgoing byte pattern
    required by the SX1262 status-byte protocol.
  - Added `spi_bus=-1` constructor path to force bit-banged SoftSPI.

## ST7735S display driver

- **File affected:** `src/st7735s.py`
- **Inspirations:**
  - Adafruit CircuitPython `adafruit_st7735r` — MIT
    https://github.com/adafruit/Adafruit_CircuitPython_ST7735R
  - Adafruit Arduino `Adafruit_ST7735` — MIT
    https://github.com/adafruit/Adafruit-ST7735-Library
  - boochow `MicroPython-ST7735` rotation/offset handling
    https://github.com/boochow/MicroPython-ST7735
- **License:** MIT
- **Local modifications:**
  - Rewrote as a MicroPython-only driver for the Univision N096-1608TBBIG09-C08
    80×160 panel on the Heltec Wireless Tracker V2.
  - Removed partial-mode commands (`PTLAR`/`PTLON`) that caused a black band on
    this panel.
  - Adjusted gamma, power, and Vcom tables for the N096 glass.

## 8×8 font

- **File affected:** `src/font8x8.py`
- **Origin:** Commonly reproduced 8×8 monospaced ASCII bitmap font table.
- **License:** Effectively public-domain / unknown provenance. No independent
  copyright is asserted over the glyph bitmap data in this project.

## Heltec pin mapping

- **File affected:** `src/heltec_tracker_v2.py`
- **Source of facts:** Heltec Wireless Tracker V2 pin-map image and schematic
  published by Heltec Automation.
- These are hardware facts, not copyrighted code.
