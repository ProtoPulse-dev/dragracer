# Heltec Wireless Tracker V2 — MicroPython Bring-Up

## Outcome (final) — UPDATED 2026-06-09

**End-to-end working.** Board flashed with a **custom MicroPython firmware**
built from source (`HELTEC_TRACKER_V2` board), the on-board TFT shows the splash
in the correct orientation, the **GNSS (UC6580) is alive on UART2** and
streaming live `$GNGGA` / `$GNRMC` / `$GPGSV` / `$GNGSA` sentences at 115 200
baud, and the splash + live NMEA page are driven by `main.py` on the device.
A drag-race timer app (`src/drag_race.py`) runs in landscape 160×80 and matches
the simulator in `gemini-code-1781045946055.html`.

- **Board**: Heltec Wireless Tracker V2 (silk-screen `v2.3`).
- **MCU**: ESP32-S3FN8 — integrated 8 MB quad flash, **no** integrated PSRAM.
  The on-board module *does* carry an external 8 MB Octal-SPI PSRAM whose data
  bus sits on GPIO 33..40.
- **Firmware**: **custom** `firmware/micropython.tinyusb-cdc-nopsram.bin`
  (1 745 488 bytes, md5 `6a0058673424220007ee1fa4e8b31472`):
  - TinyUSB CDC on `/dev/ttyACM0` (REPL).
  - USB-Serial/JTAG peripheral **disabled** (frees GPIO 19/20/43/44).
  - External PSRAM **disabled** (frees GPIO 33..37 for the GNSS UART and the
    LoRa DIOs). The internal 8 MB flash is plenty for firmware + filesystem.
  - ESP-IDF v5.5.1, Xtensa `crosstool-NG esp-14.2.0_20241119`.
- **GNSS pin map** (live NMEA captured 2026-03-26, 01:17 UTC):
  - `GPIO 35` = `GNSS_RST` (ESP drives UC6580 nRESET, active LOW)
  - `GPIO 33` = `GNSS_TX`  (UC6580 TX_OUT → ESP RX)
  - `GPIO 34` = `GNSS_RX`  (ESP TX → UC6580 RX_IN)
  - `GPIO 36` = `GNSS_PPS` (UC6580 1PPS, 1 Hz)
  - Default baud **115 200** 8N1.
- **USB**: TinyUSB CDC on `/dev/ttyACM0`. Device strings: `Espressif Device`
  (VID/PID 0x303a/0x4002), `Board CDC` interface.
- **On-device behaviour** (`main.py`): splash + 1 Hz backlight heartbeat +
  live NMEA page (fix status, sats, lat, lng, speed, time, date). Live REPL
  also dumps one line per second:
  `[hhmmss.ddmmyy] fix=N sats=NN lat=.. lng=.. spd=..kt n=NN` where `n` is
  the number of NMEA lines drained in that second.
- **Drag-race app** (`src/drag_race.py`): runs in landscape 160×80, parses
  the GNSS stream from UART2, renders the driving screen (large speed with
  "km/h" suffix on the upper line, large timer on the lower line, 12×12
  status dot in the top-right) and the info screen (header + horizontal
  divider + two-column "BEST RUN/HUIDIG" / "LAATSTE" layout). The app
  starts an AP-mode web server on port 80 for run management.

- **Board**: Heltec Wireless Tracker V2 (silk-screen: `v2.3`).
- **MCU**: ESP32-S3 (rev 0.2), Octal SPIRAM, 8 MB flash. (Schematic and wiki
  say "ESP32-S3FN8"; the actual silicon populated is the Octal-SPIRAM variant,
  which the boot log reports as `Generic ESP32S3 module with Octal-SPIRAM`.)
- **Firmware**: MicroPython v1.27.0 (build `ESP32_GENERIC_S3-SPIRAM_OCT-20251209-v1.27.0`).
  - Flashed from `firmware/micropython.bin` after a full chip erase.
  - Header byte verified (`0xE9` ESP32 magic).
- **USB**: USB-Serial/JTAG on `/dev/ttyACM0` (CDC), MAC `44:1b:f6:f8:f6:ac`.
- **Tooling**: `mpremote` for filesystem and REPL, `esptool` for flash operations.

## On-device behaviour (current `main.py`)

Booting prints, then the screen shows five centred lines on the 80×160 portrait panel:

```
       Hello          (yellow, y≈30)
       world          (cyan,   y≈50)
       HELTEC         (white,  y≈80)
       TRACKER V2     (green,  y≈100)
       uPy v1.27.0    (grey,   y≈130)
```

The TFT backlight (active-low on GPIO21) fades off/on at 1 Hz and the on-board
LED is used for the same heartbeat, in sync.

## Critical pin notes

These are the things that wasted the most time and that future-you should not
have to rediscover:

1. **VEXT_CTRL on GPIO 3 must be driven HIGH at boot.**
   - The TFT, GNSS LNA, and the GPS antenna switch are all gated by this rail.
   - The rail also feeds the USB-Serial/JTAG peripheral: toggling VEXT off
     causes the USB device to re-enumerate.
   - Leaving VEXT floating (= low) means the panel never powers up.
2. **GPIO 25 is not a legal MISO for `SPI2`** on ESP32-S3. Use `Pin(2)` instead.
3. **GPIO 33..37 ARE bonded out and usable on the ESP32-S3FN8** that is
   actually on this board — the schematic and pin map are correct. The
   earlier draft of this plan claimed otherwise, which was wrong. The
   `MICROPY_HW_ENABLE_GPIO33..37` flags in
   `mp-build/ports/esp32/boards/HELTEC_TRACKER_V2/mpconfigboard.h` turn them on
   in MicroPython; the stock `ESP32_GENERIC_S3` build refuses them at the
   port gate.
4. **GPIO 43 and 44 init fine, but the USB-Serial/JTAG peripheral holds the
   pads as a peripheral owner.** A `Pin(43, OUT, 1)` ↔ `Pin(44, IN)` loopback
   test reads 50/50 HIGH regardless of the TX drive — the SJ peripheral's
   pad-output driver is winning. To use these pads for anything other than
   USB-SJ, the SJ peripheral must be disabled in `sdkconfig`.
5. **`print(..., flush=True)` is not supported in MicroPython v1.27.0.** It
   raises `ValueError` on the first call and the script never finishes
   initialising. Use plain `print()`.
6. **`Pin.init(mode, value=)` raises `TypeError` if the pin is already
   initialised in a different mode.** The driver has a `_safe_init` helper that
   skips re-init in the existing mode rather than crashing.

## Pin map (Heltec Wireless Tracker V2, ESP32-S3 N8R8)

| Signal        | GPIO | Notes                                              |
|---------------|------|----------------------------------------------------|
| TFT_CS        | 38   | SPI2 chip select                                   |
| TFT_SCLK      | 41   | SPI2 clock                                         |
| TFT_MOSI      | 42   | SPI2 MOSI (no MISO needed)                         |
| TFT_RS / DC   | 40   | Data/Command                                       |
| TFT_RST       | 39   | Reset                                              |
| TFT_BL        | 21   | Backlight, active LOW (0 = on, 1 = off)            |
| VEXT_CTRL     | 3    | **Drive HIGH to power TFT + GNSS + USB-SJ rail**   |
| VFEM_CTRL     | 7    | Front-end module enable (LoRa), drive HIGH to use  |
| ADC_CTRL      | 2    | Battery-Voltage divider enable, drive HIGH to read |
| BAT_ADC       | 1    | ADC1_CH0 — battery voltage                         |
| LED           | 18   | On-board status LED (active HIGH)                  |
| Button        | 0    | User / BOOT button                                 |
| I2C_SDA       | 8    | Shared I2C bus (free for general use on this board)|
| I2C_SCL       | 9    | Shared I2C bus (free for general use on this board)|
| LoRa_NSS      | 10   | SX1262 chip select                                 |
| LoRa_RST      | 12   | SX1262 reset                                       |
| LoRa_BUSY     | 13   | SX1262 busy                                        |
| LoRa_DIO1     | 14   | SX1262 IRQ                                         |
| **GNSS_TX**   | **43** | **UC6580 RX — blocked by USB-SJ peripheral**     |
| **GNSS_RX**   | **44** | **UC6580 TX — blocked by USB-SJ peripheral**     |
| GNSS_RST      | n/a  | Tied to Vext_3V3 via 10K pull-up (R26); no ESP32 control on the populated board |
| GNSS_PPS      | n/a  | 1PPS output from UC6580 pin 34; routes off-board; not currently bonded to an ESP32 GPIO on this layout |

## GNSS — known state, not yet functional

The Heltec Wireless Tracker V2 carries a **UC6580** multi-GNSS receiver
(dual-frequency L1+L5, dual-system GPS+BeiDou, NMEA-0183 at 9600 baud by
default, 1 Hz update). It is the *exact same* module Heltec's "Wireless
Tracker" product line is named after.

What we know about the GNSS section, from the schematic
(`schematic/HTIT-Tracker_V2.3.pdf`) and from probes on the live board:

1. **The UC6580 is powered from `Vext_3V3` through a Schottky diode `D3` (1N5817WS).**
   No MOSFET load switch — the GNSS is unpowered only when VEXT is unpowered.
2. **`GNSS_RST` is pulled HIGH by `R26 10K` to `Vext_3V3`.** No active reset
   driver from the ESP32. The module is out of reset whenever VEXT is up.
3. **`BOOT_MODE` (UC6580 pin 34)** has a 0Ω jumper option (`R40`) in the
   schematic. By convention such jumpers ship DNP, and the UC6580's internal
   pull-down on BOOT_MODE then puts the part in NMEA mode.
4. **The 26 MHz TCXO (`X2`) is enabled** as soon as main power is applied;
   the oscillator has its own 1µF + 0.1µF bypass.
5. **The GNSS UART is on GPIO 43 (TX, ESP32→UC6580) and GPIO 44 (RX, UC6580→ESP32)**
   per the schematic. The schematic pin list on U6 shows `U0TXD` (pad 49) and
   `U0RXD` (pad 50) which on the N8R8 silicon map to GPIO 43 and GPIO 44. The
   header-20 connectors `P2`/`P3` show silk-screen labels `43` and `44`,
   consistent with this.
6. **The USB-Serial/JTAG peripheral is the SJ pad owner on GPIO 43/44** on the
   stock `ESP32_GENERIC_S3-SPIRAM_OCT` build. Confirmed by the GPIO 43 → GPIO 44
   loopback test in `tests/gnss_loopback.py`, which reads GPIO 44 stuck at 1
   regardless of GPIO 43's drive level.

This is a **firmware-level block**, not a hardware problem. The GNSS module is
wired correctly and is receiving power; it is sending NMEA at 9600 baud on
GPIO 44; the SJ peripheral is holding GPIO 44 at its idle level and the
UC6580's TX line never reaches our `Pin(44, Pin.IN)` reader.

### How to bring up the GNSS

Two paths, in order of risk-vs-reward:

**Path 1 — Custom firmware, REPL stays on USB-C (recommended)**

The cleanest fix is to disable the SJ peripheral's claim on GPIO 43/44 *while
keeping the REPL on USB-C*. The way to do this is to move the REPL from the
SJ peripheral to the on-board USB-Serial/JTAG using the **TinyUSB CDC device**
on a different set of USB pads.

The Heltec Wireless Tracker V2 has only one USB port (USB-C, wired to the SJ
peripheral). There is no second USB path on the PCB. So this path actually
does not exist in practice on this board — the only way to free GPIO 43/44 is
to also give up the USB-C REPL.

**Path 2 — Custom firmware + FTDI (the only path that works on this board)**

1. Build a custom MicroPython firmware with `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=n`
   and `CONFIG_ESP_CONSOLE_UART=y` on `UART0` at GPIO 43/44.
2. The board's USB-C port becomes a power-only port. REPL moves to a 3.3V
   FTDI USB-serial adapter on the J2 header (TX→RX, RX→TX, GND→GND).
3. Once the SJ peripheral is out of the way, GPIO 43/44 are free GPIO, and
   `UART(2, tx=43, rx=44, baudrate=9600)` is the GNSS port.
4. `mpremote` workflow becomes `mpremote connect /dev/ttyUSB0 ...` instead of
   `/dev/ttyACM0`.

**Path 3 — Accept that GNSS is unusable on this firmware**

Stop here. Document that the Wireless Tracker V2's headline feature (the
GNSS) is gated behind a custom firmware build on this board, and the
hardware is otherwise fully functional. The board is still useful for
SPI/I2C experimentation, the TFT, Wi-Fi, BLE, and the SX1262 (the LoRa
transceiver is on its own SPI bus and is *not* blocked by the SJ
peripheral — it's free to use on the stock firmware).

## Display configuration that actually works on this panel

- **Panel**: 80×160 physical pixels, **Univision N096-1608TBBIG09-C08**
  (datasheet at <https://resource.heltec.cn/download/Wireless_Tracker_V2/Display_Datasheet/SPEC%20N096-1608TBBIG09-C08%20VER%20A.pdf>).
- **Driver IC**: actually an **ST7735S** (the Heltec wiki says ST7789 but the
  panel datasheet clearly states ST7735S). The two share the same SPI/MADCTL
  command set, so the same driver works for both, but the ST7735S needs the
  full power/gamma init sequence to produce vivid colours — without it the
  panel comes up with washed-out, dull colours.
- **Portrait (default)**: `width=80, height=160, xstart=26, ystart=0, rotation=0`
  (BGR colour order, used by `main.py` splash).
- **Landscape (drag-race UI)**: `width=160, height=80, xstart=0, ystart=26, rotation=5`.
  `rotation=5` is `MV|MY|BGR` (landscape + vertical mirror). It is *not* in the
  original 4-rotation table; the driver was extended with `r=4` (landscape
  180° = `MX|MY|MV|BGR`) and `r=5` (landscape with vertical mirror only).
  `r=1` is mirrored horizontally; `r=3` is mirrored both ways; `r=4` is the
  full 180° rotation. `r=5` is the only one that puts the TL pixel in the
  physical top-left of the glass with the USB-C connector on the left and the
  antenna on the right.
- **Partial mode removed**: the old driver used `PTLAR`/`PTLON` to hide
  off-window noise, but this clipped the active scan window and produced a
  black band on the long edge in both portrait and landscape.  The new
  `st7735s.py` driver stays in normal scan mode and relies on correct
  `CASET`/`RASET` offsets to position the 80×160 active area in the 132×162
  GRAM.
- **SPI must include a spare MISO pin**: on the ESP32-S3, constructing
  `SPI(2, ..., mosi=..., sck=...)` and then calling `spi.init()` later can
  drop the MOSI/SCK pin assignments.  Always create the bus with
  `miso=Pin(2)` (or any input-capable pin) even though the ST7735S does not
  use MISO.
- **Gamma / Vcom**: the driver sets `_FRMCTR1..3`, `_INVCTR`, `_PWCTR1..5`,
  `_VMCTR1=0x06` (Vcom ≈ 0.40 V, low-brightness), the "muted" 16-step gamma
  tables at `GMCTRP1` / `GMCTRN1`, and `INVOFF`. The muted gamma + V0.40 was
  picked via the on-device gamma tuner (`tests/gamma_tuner.py`) — it gives a
  more natural colour depth than the stock Red/Green/Black-tab tables, which
  over-saturate the warm colours on this particular ST7735S.

## Files on the device (after the last `mpremote fs cp`)

```
:st7735s.py           # ST7735S driver for the N096 panel (rotation 0..5)
:font8x8.py           # 8×8 ASCII font, 768 bytes
:heltec_tracker_v2.py # Pin constants + VEXT_CTRL helper
:main.py              # VEXT_CTRL up, splash, 1 Hz backlight heartbeat, runtime 240 MHz
:drag_race.py         # landscape 160×80 drag-race UI + AP-mode web server
```

## Local sources

- `src/st7735s.py` — clean ST7735S driver (replaces the old `st7789.py`);
  uses normal scan mode with correct offsets, no partial-mode workaround.
- `src/font8x8.py`
- `src/heltec_tracker_v2.py`
- `src/main.py`
- `src/drag_race.py` — drag-race timer UI (port of the simulator in
  `gemini-code-1781045946055.html`), running in landscape 160×80 with the
  ST7735S init sequence described above. Pushes the `machine.freq(240_000_000)`
  bump at start-up.
- `tests/smoke.py` — bring-up test (RGB flash, splash, heartbeat pixel).
- `tests/hello_check.py` — 4-blink limited verification.
- `tests/cs_probe.py` — CS pin brute-force probe (used to rule out a wrong CS
  GPIO; returned `0xFF` for all candidates, which is what tipped us off that
  the issue was the VEXT rail, not the SPI pinout).
- `tests/gnss_pin_probe.py` — confirmed GPIO 33/34 are not in the mux
  (`ValueError('invalid pin')`); GPIO 43/44 init fine but are owned by the
  USB-SJ peripheral.
- `tests/gnss_uc6580_probe.py` — 60 s listen + VEXT cycle on GPIO 44 via
  hardware UART2. Zero NMEA traffic. (Cycle killed the USB connection, which
  is itself a strong signal that VEXT powers the SJ peripheral.)
- `tests/gnss_loopback.py` — GPIO 43 → GPIO 44 software loopback. Reads 50/50
  HIGH regardless of TX drive. **Decisive evidence** that the SJ peripheral
  is the blocker, not the GNSS module.
- `tests/landscape_test_nums.py` — 1/2/3/4 quadrant test used to nail down
  the landscape `rotation` value.
- `tests/gamma_tuner.py` — 12-step gamma × Vcom picker with short/long-press
  button control. Used to choose the "muted" gamma table now in the driver.
- `pinout/Tracker_v2.3.png` — Heltec silk-screen pinout.
- `schematic/HTIT-Tracker_V2.3.pdf` and the rendered `schematic/HTIT-Tracker_V2.3.png`
  — schematic used to confirm VEXT_CTRL, the Schottky power gate `D3`, the
  UC6580 part, and the GPIO 43/44 routing.
- `Wireless Tracker v2.pdf` — Rev 1.1 datasheet, used for the GPIO audit.

## Bring-up steps (clean-room, for the record)

1. `pip install esptool mpremote pypdf pypdfium2 pillow` (host tooling).
2. `esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash`
3. `esptool.py --chip esp32s3 --port /dev/ttyACM0 --baud 460800 write_flash 0x0 firmware/micropython.bin`
4. `mpremote connect /dev/ttyACM0 fs cp src/*.py :`
5. `mpremote connect /dev/ttyACM0 reset`
6. The REPL prints the boot banner; the screen lights up and the heartbeat
   begins.

## Known limitations / TODO

- **GNSS** is unusable on the stock firmware. See "GNSS — known state" above.
  Custom firmware + FTDI required, or accept the limitation.
- **LoRa (SX1262)** SPI bus and control lines are wired to dedicated GPIOs
  (10/12/13/14) that are not yet used by any driver on the device. Adding a
  SX1262 driver is independent of the GNSS work and *is* feasible on the
  current firmware (those pins are not blocked by the SJ peripheral).
- **Battery voltage** read needs `ADC_CTRL` (GPIO 2) driven HIGH first;
  the constant is in `heltec_tracker_v2.py` but the read is not yet wired
  into `main.py`.
- **Backlight brightness** is currently a binary on/off via GPIO21. For PWM
  dimming, move the pin to a PWM-capable channel (LEDC) and update
  `main.py` to use `PWM` instead of `Pin`.

---

## Custom firmware build — SUCCESS (2026-06-09)

**Board:** `HELTEC_TRACKER_V2` (`ESP32S3`, `SPIRAM_OCT`)
**Output:** `firmware/micropython.tinyusb-cdc.bin` (1 691 712 bytes, md5 `0b8766033834186a44f939e9c0694b8d`)
**Ninja result:** `[1502/1502]`, 17 % app-partition headroom

### Toolchain

| Component | Version | Location |
|-----------|---------|----------|
| ESP-IDF | **v5.5.1** (required by `ports/esp32/lockfiles/dependencies.lock.esp32`) | `mp-build/ports/esp32/esp-idf/` |
| Xtensa GCC | `crosstool-NG esp-14.2.0_20241119` (unified `xtensa-esp-elf` — S3 included) | `~/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/` |
| IDF Python venv | `idf5.5_py3.13_env` | `~/.espressif/python_env/idf5.5_py3.13_env/` |
| MicroPython | v1.27.0 | `mp-build/` |

The previous attempt with ESP-IDF v5.1.6 + Xtensa 12.2.0 failed at compile with
`xtensa-esp32s3-elf-gcc: error: unrecognized command-line option '-mdisable-hardware-atomics'`
— that flag is new in toolchain ≥ 14.x. Both have since been replaced with the
correct versions above.

### Submodules initialised (after v5.5.1 clone)

```
git submodule update --init lib/berkeley-db-1.xx
git submodule update --init lib/micropython-lib
```

### Build command (one-liner)

```bash
cd "/home/gerrie/Playground/wireless tracker/mp-build/ports/esp32" && \
mkdir -p build-HELTEC_TRACKER_V2 && cd build-HELTEC_TRACKER_V2 && \
export IDF_PATH="/home/gerrie/Playground/wireless tracker/mp-build/ports/esp32/esp-idf" && \
export IDF_PYTHON_ENV_PATH=/home/gerrie/.espressif/python_env/idf5.5_py3.13_env && \
export PATH="$IDF_PYTHON_ENV_PATH/bin:/home/gerrie/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin:/home/gerrie/.espressif/tools/xtensa-esp-elf-gdb/14.2_20240403/xtensa-esp-elf-gdb/bin:/home/gerrie/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20241119/riscv32-esp-elf/bin:/home/gerrie/.espressif/tools/esp32s3ulp-elf/2.38.51-esp-12.2.0/esp32s3ulp-elf/bin:/home/gerrie/.espressif/tools/openocd-esp32/v0.12.0-esp32-20250422/openocd-esp32/bin:/home/gerrie/.espressif/tools/ninja/1.12.1:$PATH" && \
cmake -G Ninja -DMICROPY_BOARD=HELTEC_TRACKER_V2 -DMICROPY_BOARD_VARIANT=SPIRAM_OCT .. && \
ninja
```

### What this firmware changes vs stock `ESP32_GENERIC_S3-SPIRAM_OCT`

- **`MICROPY_HW_ESP_USB_SERIAL_JTAG = 0`** — the built-in USB-SJ peripheral is disabled.
- **`MICROPY_HW_ENABLE_USBDEV = 1`** — TinyUSB CDC is enabled, so the USB-C connector still
  shows up as `/dev/ttyACM0` (REPL) on the host.
- **`MICROPY_HW_ENABLE_UART_REPL = 1`** — UART0 REPL is also available (TX=GPIO 43, RX=GPIO 44,
  115 200 8N1) as a fallback / for hard-bench work without a USB cable. With the SJ peripheral
  disabled, these pads are now safe to use for the UC6580 GNSS UART.
- **TinyUSB CDC is in components:** `espressif__tinyusb` is in the build (visible in
  `idf-component-manager` resolution).
- **Toolchain unified `xtensa-esp-elf`** — IDF ≥ v5.3 stopped shipping per-target toolchains.

---

## Custom firmware build (v2, no-PSRAM) — SUCCESS (2026-06-09)

The first custom build (the section above) left the external PSRAM enabled.
The Heltec module carries the PSRAM in **Octal** mode whose data bus lives on
GPIO 33..40 — exactly the same pins the GNSS UART and the LoRa DIOs need.
With PSRAM enabled the IDF owns those pins, so `Pin(33)` and `Pin(34)` either
trigger the bootrom panic (`invalid pin`) or get clobbered at the GPIO matrix
level. Disabling PSRAM entirely is the only clean fix.

This is fine: the ESP32-S3FN8 has 8 MB of internal flash. The firmware is
1.7 MB; the rest is available for the LittleFS filesystem.

### What changed vs v1

- `boards/HELTEC_TRACKER_V2/mpconfigboard.cmake` no longer includes
  `boards/sdkconfig.spiram_sx`.
- `boards/HELTEC_TRACKER_V2/sdkconfig.board` adds `CONFIG_SPIRAM=n` with a
  comment block explaining why.
- `boards/HELTEC_TRACKER_V2/mpconfigvariant_SPIRAM_OCT.cmake` is left in place
  but is **not used** by the build (no `BOARD_VARIANT` is set on the cmake
  command line). Delete it if you want a clean tree.

### Build

```bash
cd "/home/gerrie/Playground/wireless tracker/mp-build/ports/esp32"
rm -rf build-HELTEC_TRACKER_V2
make BOARD=HELTEC_TRACKER_V2 submodules
make BOARD=HELTEC_TRACKER_V2 -j$(nproc)
```

The resulting `build-HELTEC_TRACKER_V2/micropython.bin` is 1 686 496 bytes.
Merge with esptool:

```bash
cd build-HELTEC_TRACKER_V2
python3 -m esptool --chip esp32s3 merge-bin \
    --flash-mode dio --flash-freq 80m --flash-size 8MB \
    -o /tmp/heltec-tracker-v2-nopsram.bin \
    0x0     bootloader/bootloader.bin \
    0x8000  partition_table/partition-table.bin \
    0x10000 micropython.bin
```

### Flash

```bash
python3 -m esptool --chip esp32s3 -p /dev/ttyACM0 -b 460800 \
    --before default_reset --after hard_reset write_flash \
    0x0 /tmp/heltec-tracker-v2-nopsram.bin
```

A working backup of this build is at
`firmware/micropython.tinyusb-cdc-nopsram.bin`
(md5 `6a0058673424220007ee1fa4e8b31472`).

### Live verification

```text
ALIVE
reset_cause: 5
freq: 160000000
mem_free: 232352
VEXT GPIO3 ok
GPIO33,34 ok (val33= 1 val34= 1 )      # GNSS TX (33) idle high

UART2 ok on (tx=34, rx=33) @115200
baud 115200: got 3688 bytes
>> UC6580I-00 G1B1L1E1 COM1
>> FWVer R6.0.0.0Build3700
>> $GNRMC,011541.80,V,,,,,,,260326,,,N,V*12
>> $GNGGA,011541.80,,,,,0,00,99.99,,,,,,*70
>> $GNGSA,A,1,...,1*33   # GPS
>> $GNGSA,A,1,...,2*30   # GLONASS
>> $GNGSA,A,1,...,4*36   # BeiDou
>> $GNGSA,A,1,...,3*31   # Galileo
>> $GNGSA,A,1,...,5*37   # QQSS
>> $GPGSV,2,1,05,01,26,156,...
```

### Performance note

The board boots at **160 MHz** (the default for the no-PSRAM IDF configuration
in the working build, which keeps the firmware binary small and avoids the
need to rebuild). Both `src/main.py` and `src/drag_race.py` call
`machine.freq(240_000_000)` near the top, so the apps run at the higher clock
without flashing a new firmware. To make 240 MHz the boot default, set
`CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ=240` in
`mp-build/ports/esp32/boards/HELTEC_TRACKER_V2/sdkconfig.board` and rebuild.
