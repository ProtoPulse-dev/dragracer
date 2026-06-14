"""
Heltec Wireless Tracker V2 — board pin map (MicroPython).

SPDX-FileCopyrightText: 2026 ProtoPulse-dev
SPDX-License-Identifier: MIT

Pin map verified against the official Heltec pin map
  https://resource.heltec.cn/download/Wireless_Tracker_V2/Pin_Map/Tracker_v2.3.png
and the schematic `HTIT-Tracker_V2.3.pdf`.

NOTE — silicon variant and PSRAM
--------------------------------
The Wireless Tracker V2 is built around the ESP32-S3FN8 (quad SPI flash,
8 MB, no integrated PSRAM). The board does have an external 8 MB
Octal-SPI PSRAM whose data bus sits on GPIO 33..40; if that PSRAM is
enabled, those pins cannot be used for anything else.

In the public firmware we **disable the external PSRAM entirely** in
order to keep GPIO 33..37 free for the GNSS UART and other peripherals.
The chip's internal 8 MB flash is more than enough for firmware +
filesystem. See the board definition in `board/HELTEC_TRACKER_V2/` for
the sdkconfig that turns PSRAM off.

GNSS pin map (confirmed live on UART2 at 115200 baud):
   GPIO 35 = GNSS_RST   (ESP drives UC6580's nRESET, active LOW)
   GPIO 33 = GNSS_TX    (UC6580's TX_OUT -> ESP RX)
   GPIO 34 = GNSS_RX    (ESP TX -> UC6580's RX_IN)
"""

# ---- on-board TFT (ST7735S 80x160, J2 header) -----------------------------
TFT_CS   = 38    # J2.12 — FSPIWP / SUBSPIWP / TFT_CS
TFT_SCLK = 41    # J2.13 — MTDI            / TFT_SCLK
TFT_MOSI = 42    # J2.14 — MTMS            / TFT_SDIN  (SPI MOSI)
TFT_RS   = 40    # J2.15 — MTDO            / TFT_RS    (data/command)
TFT_RST  = 39    # J2.16 — MTCK            / TFT_RES
TFT_BL   = 21    # J1.16 — TFT_LED_K       (active LOW)

# ---- power-rail gates (must be enabled before any peripheral init) -------
VEXT_CTRL = 3    # J2.7  — Vext_Ctrl   (active HIGH: drive HIGH to power
                 #                     the on-board 3.3V rail for TFT/GNSS)
VFEM_CTRL = 7    # J2.3  — VFEM_Ctrl   (LoRa front-end module power)
ADC_CTRL  = 2    # J2.8  — ADC_Ctrl    (battery voltage divider enable)

# ---- battery / ADC --------------------------------------------------------
BAT_ADC = 1      # ADC1_CH0 — battery voltage divider output

# ---- J2 header UART0 (free for general use) --------------------------------
J2_TXD = 43      # J2.20 — U0TXD
J2_RXD = 44      # J2.19 — U0RXD

# ---- user / button --------------------------------------------------------
USR_BTN = 0      # J2.10 — USER_SW (active LOW)
USR_LED = 21     # controllable LED on the board is the backlight pin

# ---- GNSS (UC6580, multi-constellation L1+L5) -----------------------------
GNSS_RST = 35    # J1.13 — SPIIO6  -> UC6580 nRESET (active LOW)
GNSS_TX  = 33    # J1.19 — SPIIO4  <- UC6580 TX_OUT (ESP RX)
GNSS_RX  = 34    # J1.20 — SPIIO5  -> UC6580 RX_IN  (ESP TX)
GNSS_PPS = 36    # J1.14 — SPIIO7  <- UC6580 PPS    (1PPS, 1Hz)

# Default NMEA baud for the UC6580 on this board. The Heltec factory
# Arduino sketch uses 115200 8N1; the live NMEA captured on 2026-03-26
# confirmed the chip is talking at this rate out of the box.
GNSS_BAUD = 115200

# ---- LoRa (SX1262) --------------------------------------------------------
# Verified against the Heltec Arduino library board-config.h and schematic.
LoRa_NSS   = 8   # SX1262 chip select
LoRa_RST   = 12  # SX1262 reset (active LOW)
LoRa_BUSY  = 13  # SX1262 busy (HIGH while busy)
LoRa_DIO1  = 14  # SX1262 IRQ
LoRa_SCK   = 9   # SPI clock
LoRa_MOSI  = 10  # SPI MOSI
LoRa_MISO  = 11  # SPI MISO

# Front-end PA control pins (external RF switch / PA on the Tracker V2).
# VFEM_Ctrl powers the LoRa front-end; PA_CSD and PA_CTX are used by the
# official Heltec driver for TX/RX antenna switching.
LORA_PA_POWER = 7   # VFEM_Ctrl: drive HIGH to enable LoRa 3.3V rail
LORA_PA_CSD   = 4   # chip shutdown (active HIGH?  LOW = enabled)
LORA_PA_CTX   = 5   # TX enable (active HIGH)

BOARD_NAME   = "Heltec Wireless Tracker V2 (Rev 2.0, ESP32-S3FN8, no PSRAM)"
MCPU_FREQ_HZ = 240_000_000
