# Heltec Wireless Tracker V2 — Drag-Race Timer

A drag-race / speed-trap timer for the **Heltec Wireless Tracker V2**
(ESP32-S3FN8, 80×160 ST7735S TFT, UC6580 multi-GNSS).

The device measures the time it takes a vehicle to accelerate from a
configurable start speed to a configurable end speed (default 60 → 120 km/h),
logs every run to `runs.csv`, shows the best run and the last three runs on
the built-in display, and serves the log over a Wi-Fi access point.

![Hardware photo placeholder](hardware/board_photo.jpg)

## Hardware

- Heltec Wireless Tracker V2 (Rev 2.0)
- ESP32-S3FN8, 8 MB flash
- On-board UC6580 GNSS receiver (GPS/GLONASS/Galileo/BeiDou, L1+L5)
- On-board SX1262 LoRa transceiver
- 80×160 ST7735S colour TFT (used in landscape 160×80)
- USER button (GPIO 0, active low)
- Active-low backlight on GPIO 21

Pin map, schematic and a long-form bring-up log are in `hardware/` and `docs/`.

## Firmware

This application runs on a **custom MicroPython firmware** that disables
external PSRAM and the USB-Serial/JTAG peripheral so GPIO 33–37/43–44 stay free.

Download the prebuilt firmware image and read the flashing instructions from
the companion project:

🔗 [ProtoPulse-dev/heltec-wireless-tracker-v2-micropython](https://github.com/ProtoPulse-dev/heltec-wireless-tracker-v2-micropython)

> On the custom firmware the REPL is on TinyUSB CDC at `/dev/ttyACM0`.

## Install the application

Copy `src/*.py` to the board's root filesystem and make `drag_race.py` the
boot script:

```bash
mpremote connect /dev/ttyACM0 fs cp src/*.py :
mpremote connect /dev/ttyACM0 fs cp src/drag_race.py :main.py
mpremote connect /dev/ttyACM0 reset
```

The device will reboot into the drag-race UI.

### Optional: use the bring-up splash instead

If you want the GNSS bring-up splash screen at boot:

```bash
mpremote connect /dev/ttyACM0 fs cp src/main.py :main.py
mpremote connect /dev/ttyACM0 reset
```

## Usage

### Driving screen

Shows current GNSS speed and the live timer. When speed crosses **Start
Speed** the timer starts; when it crosses **End Speed** the run is saved and
the state switches to **COOL** until speed drops below **Reset Speed**.

### Info screen

Short-press the USER button to toggle between driving and info screens. The
info screen shows:

- Best run ever
- Current speed
- Last three runs

### Hold actions

- **Hold USER ≥ 2 s:** clear the last-three list (yellow flash).
- **Hold USER ≥ 5 s:** clear best run and last-three list (red flash).

### Web interface

The device creates an AP named `GPS_TIMER_ESP32` with password `12345678`.
Connect and open:

- `http://192.168.4.1/` — view the run log (`runs.csv`).
- `http://192.168.4.1/config` — read current thresholds.
- `http://192.168.4.1/config?start=60&end=120&reset=55` — set new thresholds.

Thresholds are persisted to `config.json` and reloaded on boot.

### Changing thresholds in code

Edit the defaults in `src/drag_race.py`:

```python
START_SPEED_DEF = 60.0  # km/h
END_SPEED_DEF   = 120.0 # km/h
RESET_SPEED_DEF = 55.0  # km/h
```

## File layout

```
dragracer_app/
├── src/
│   ├── drag_race.py          # Main drag-race timer application
│   ├── main.py               # GNSS bring-up / splash page
│   ├── heltec_tracker_v2.py  # Board pin map
│   ├── st7735s.py            # ST7735S display driver
│   ├── font8x8.py            # 8×8 ASCII font
│   └── sx1262.py / sx126x.py / _sx126x.py  # SX1262 LoRa driver
├── hardware/
│   ├── pinout.png
│   ├── schematic.pdf
│   └── schematic.png
├── docs/
│   └── bringup_log.md
├── LICENSE                   # MIT
├── THIRD_PARTY.md            # Attribution
└── README.md                 # This file
```

## LoRa

The SX1262 driver files are included (`src/sx1262.py`, `src/sx126x.py`,
`src/_sx126x.py`) but the drag-race timer does not currently use LoRa. They
are ready for future extensions such as broadcasting run times to a base
station.

## License

MIT — see `LICENSE`.

Third-party attribution is in `THIRD_PARTY.md`.

## Acknowledgements

- Display driver derived from Adafruit's ST7735 libraries and boochow's
  MicroPython-ST7735 (MIT).
- LoRa driver derived from `micropySX126X` by E H Ong (MIT).
