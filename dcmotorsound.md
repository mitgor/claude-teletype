# DC Motor Sound & Printer Music Research

Research into GitHub projects and techniques for playing music using printer motors, stepper motors, and their applicability to Juki daisy wheel printers.

---

## Table of Contents

1. [How Stepper Motor Music Works](#1-how-stepper-motor-music-works)
2. [Dot-Matrix & Impact Printer Music Projects](#2-dot-matrix--impact-printer-music-projects)
3. [3D Printer / CNC G-Code Music Projects](#3-3d-printer--cnc-g-code-music-projects)
4. [Floppy Drive Music Projects](#4-floppy-drive-music-projects)
5. [Standalone Stepper Motor Music Projects](#5-standalone-stepper-motor-music-projects)
6. [DC Motor & BLDC Motor Music](#6-dc-motor--bldc-motor-music)
7. [MIDI to Motor Conversion](#7-midi-to-motor-conversion)
8. [Hardware Interfaces & Drivers](#8-hardware-interfaces--drivers)
9. [Juki Daisy Wheel Printer Analysis](#9-juki-daisy-wheel-printer-analysis)
10. [Applicability to Juki Printers](#10-applicability-to-juki-printers)
11. [Key References & Sources](#11-key-references--sources)

---

## 1. How Stepper Motor Music Works

### Core Sound Generation

Stepper motors produce sound through **magnetostriction** -- a property of ferromagnetic materials that causes them to expand or contract under magnetic fields. When the motor steps at a rate within the audible range (20 Hz - 20 kHz), these vibrations are perceived as a pitched tone.

The relationship is direct: **step frequency = audio frequency**. To play A4 (concert pitch), command the motor to step at 440 steps/second.

### Frequency Ranges by Motor Type

| Motor Type | Lower Limit | Upper Limit | Musical Range |
|---|---|---|---|
| Floppy drive stepper | ~20 Hz | ~400-440 Hz | Sub-bass to ~A4 |
| NEMA 17 (full step) | ~20 Hz | ~1-2 kHz | Full bass through mid-range |
| NEMA 17 (microstepped) | ~20 Hz | ~4+ kHz | Extended range |
| Small 28BYJ-48 | ~20 Hz | ~500 Hz | Limited range |

### Stepping Mode vs Sound Quality

- **Full-step**: Loudest, harshest sound with strong harmonics. Buzzy and aggressive.
- **Half-step**: ~29% of full-step energy. Slightly cleaner tone.
- **Microstepping (1/16, 1/32)**: Uses sinusoidal current waveforms. Much smoother but quieter. 1/32 microstepping retains only ~0.1% of full-step energy.

Most music projects use full-step or half-step to maximize volume and the characteristic mechanical timbre.

### Motor Type Comparison for Music

| Feature | Stepper Motor | Brushed DC Motor | BLDC Motor |
|---|---|---|---|
| Pitch precision | Excellent (discrete steps) | Poor (continuous, noisy) | Very good (SVM control) |
| Frequency range | ~20 Hz - 2+ kHz | ~20 Hz - 500 Hz | ~20 Hz - 10 kHz |
| Polyphony per motor | 1 note only | 1 note only | Up to 7 notes (chords!) |
| Volume | Moderate-loud | Low-moderate | Moderate |
| Timbre | Buzzy, mechanical | Noisy, harsh | Chip-tune-like, smoother |
| Driver complexity | Low (STEP/DIR) | Low (H-bridge) | High (FOC/SVM) |

---

## 2. Dot-Matrix & Impact Printer Music Projects

These are the most directly relevant -- actual document printers making music.

### MIDIDesaster -- Dot Matrix Printer MIDI Instrument

- **Source:** Documented on [Hackaday](https://hackaday.com/2014/02/20/eye-of-the-tiger-as-played-by-a-dot-matrix-printer/) (no public GitHub repo)
- **Printer:** 24-pin dot matrix printer
- **How it works:** Custom hardware using **Atmega8 + FPGA** connected to the printer's original circuit board. The Atmega8 takes MIDI data and communicates to the FPGA while driving the stepper motors. The FPGA handles PWM to drive the individual 24 printer pins. Can play **up to 21 notes simultaneously** across 16 MIDI channels with individual volume, pitch, and key velocity.
- **Language:** Embedded C / VHDL (FPGA)
- **Demos:** Eye of the Tiger, Duke Nukem theme, Hysteria by Muse

### Paul Slocum -- Dot Matrix Synth (Epson LQ-500)

- **Project page:** https://www.qotile.net/dotmatrix.html
- **Source code:** [EpsonLQ500_Programming_Kit.zip](http://www.qotile.net/temp/EpsonLQ500_Programming_Kit.zip)
- **Printer:** Epson LQ-500 (1985 dot matrix)
- **How it works:** Custom firmware written to the printer's EPROM. Tones created by driving the print head at different frequencies. Sound from two sources: (1) print head pins firing against paper, and (2) stepper motor vibration. Controlled via 8-button pad. The printer **prints real pictures while you play it**.
- **Language:** Assembly (custom EPROM firmware)
- **Status:** Art installation piece (exhibited at The New Museum of Contemporary Art, NYC)

### [The User] -- Symphony for Dot Matrix Printers

- **Project page:** http://www.theuser.org/dotmatrix/en/intro.html
- **Printer:** 12 early-1990s era dot matrix printers
- **How it works:** Software by Thaddeus Thomas (ReDada). 12 printers connected via LAN. Reads from **ASCII text-file scores** which, when printed, create textures, tones, and rhythms. Printers' mechanical noises are the sole sound source.

### scanner-stepper (chfoo)

- **Repository:** https://github.com/chfoo/scanner-stepper (5 stars)
- **Printer:** HP ScanJet scanner stepper motor
- **How it works:** Arduino + Python. Audio-to-text pitch detection converts frequencies into serial commands for Arduino, which drives the stepper motor via L293D H-bridge.
- **Language:** Python / C++ (Arduino)
- **License:** MIT

---

## 3. 3D Printer / CNC G-Code Music Projects

These use stepper motors in 3D printers/CNC machines. Techniques are directly transferable to any stepper-motor-driven carriage.

### mid2cnc (TeamTeamUSA) -- 47 stars

- **Repository:** https://github.com/TeamTeamUSA/mid2cnc
- **Original author:** Tim Gipson (http://tim.cexx.org/?p=633)
- **How it works:** Python MIDI parser converts MIDI files to G-code. Stepper stepping rate = pitch, note duration = distance traveled. The foundational project in this space.
- **Language:** Python
- **Notable forks:**
  - [jherrm/midi-to-cnc](https://github.com/jherrm/midi-to-cnc) -- 3-axis polyphony for Printrbot
  - [jimmieclark3/mid2cnc_grbl](https://github.com/jimmieclark3/mid2cnc_grbl) -- GRBL-compatible
  - [rickarddahlstrand/MIDI-to-CNC](https://github.com/rickarddahlstrand/MIDI-to-CNC) (22 stars) -- Lulzbot, 3 MIDI tracks to 3 axes

### midi-m300 (alexyu132) -- 121 stars

- **Repository:** https://github.com/alexyu132/midi-m300
- **Live demo:** https://alexyu132.github.io/midi-m300/
- **How it works:** Web-based tool converting MIDI tracks to Marlin `M300` speaker G-code commands.
- **Language:** HTML/CSS
- **License:** GPL-3.0

### MIDI-Stepper-Motor-Music (barlowtj48) -- 113 stars

- **Repository:** https://github.com/barlowtj48/MIDI-Stepper-Motor-Music
- **How it works:** Python accepts MIDI input via virtual MIDI port (loopMIDI/IAC Driver). Each motor assigned a MIDI channel. Arduino with A4988 drivers generates timed pulses.
- **Language:** Python / C++
- **License:** MIT
- **Cost:** ~$60-70 in components

### Arduino-MIDI-Stepper-Motor-Instrument (jzkmath) -- 106 stars

- **Repository:** https://github.com/jzkmath/Arduino-MIDI-Stepper-Motor-Instrument
- **How it works:** Accepts MIDI via DIN socket, serial-to-MIDI, or USB MIDI. Arduino CNC Shield with A4988 drivers. Most complete Arduino stepper music project.
- **Language:** C++ / C
- **License:** GPL-3.0
- **Status:** V2 in development with FPGA, custom PCBs, 32 steppers

### Midi23D (cavallium) -- 17 stars

- **Repository:** https://github.com/cavallium/Midi23D
- **How it works:** Java GUI converting MIDI notes to G-code movement commands. Multi-motor support with motor testing/calibration mode.
- **Language:** Java

### Musical_Marlin (Toglefritz) -- 12 stars

- **Repository:** https://github.com/Toglefritz/Musical_Marlin
- **How it works:** Modified Marlin firmware. Musical note frequencies mapped to stepper step rates (steps/second).
- **Language:** C / C++

### Other Notable Projects

| Project | Stars | Language | Notes |
|---------|-------|----------|-------|
| [midi2gcode](https://github.com/phuang1024/midi2gcode) | 9 | Python | CLI tool, axis selection |
| [CNCmusic](https://github.com/pgeorgiadis/CNCmusic) | - | - | Text notation to G-code |
| [midiCNC](https://github.com/alnwlsn/midiCNC) | - | Python | Up to 6 axes via grbl-mega-5x |
| [gCodeMusic](https://github.com/forflo/gCodeMusic) | 6 | Haskell | Music EDSL, supports chords |
| [MusicalMarlin](https://github.com/unlimitedbacon/MusicalMarlin) | 2 | C/C++ | 3-channel polyphonic, M808 command |
| [GCodeAudializer](https://github.com/martymcguire/GCodeAudializer) | 3 | Processing | Reverse: G-code to .wav simulation |
| [gcodesynth](https://github.com/Hierosoft/gcodesynth) | 1 | Python | Previews M300 as sine waves via pyaudio |

---

## 4. Floppy Drive Music Projects

Floppy drives contain small stepper motors and are the most popular platform for motor music.

### Moppy2 (Sammy1Am) -- 331 stars

- **Repository:** https://github.com/Sammy1Am/Moppy2
- **How it works:** Generates timed pulses at desired note frequencies via STEP and DIRECTION pins. Java control software + Arduino firmware. Supports MIDI In/Out for live keyboard playing. Each drive = one monophonic voice.
- **Language:** Java / C++
- **Predecessor:** [MoppyClassic](https://github.com/Sammy1Am/MoppyClassic) (archived)

### Other Floppy Music Projects

| Project | Description |
|---------|-------------|
| [MIDItoMoppy](https://github.com/dmadison/MIDItoMoppy) | Library to convert MIDI to Moppy format without PC |
| [floppymusic](https://github.com/Kingdread/floppymusic) | Raspberry Pi + Rust floppy controller |
| [midifloppy](https://github.com/Ultrawipf/midifloppy) | Arduino Due + MIDI USB |
| [Arduino-MIDI-Floppy-Drive-Instrument](https://github.com/jzkmath/Arduino-MIDI-Floppy-Drive-Instrument) | Up to 24 floppy drives via Arduino Mega |

---

## 5. Standalone Stepper Motor Music Projects

| Project | Stars | Language | Description |
|---------|-------|----------|-------------|
| [MusicalMotors](https://github.com/shawnanastasio/MusicalMotors) | 8 | Python/C++ | Serial commands for steppers + floppy drives |
| [3-stepper-mario](https://github.com/robharper/3-stepper-mario) | - | C++ | 3 steppers on Arduino Uno, Super Mario theme |
| [stepper-motor-synth](https://github.com/PeterCxy/stepper-motor-synth) | - | C++ | Arduino MIDI synth with pitch table generator |
| [Stepper_Motor_Symphony](https://github.com/Amp-Lab-at-VT/Stepper_Motor_Symphony) | 1 | Java/C++ | 9 NEMA 17 motors, ESP8266, JFugue MIDI |
| [stepper-motor-music](https://github.com/joshbuker/stepper-motor-music) | 2 | C++ | Arduino UNO + L298N + NEMA 17 |
| [steppr](https://github.com/nathanielatom/steppr) | 0 | Python | RPi 4, PWM-driven, reads MIDI files |
| [Makeblock music-bot](https://github.com/Makeblock-official/music-bot) | 3 | C++ | Official Makeblock stepper music robot |

---

## 6. DC Motor & BLDC Motor Music

### Brushed DC Motors

DC motors **can** produce controllable tones but through a different mechanism:

- **Direction-switching method:** Rapidly alternate H-bridge between forward/reverse at audio frequency. Motor vibrates in place rather than spinning, producing a buzzing tone. Similar to how speakers work.
- **Limitations:** Poor tone quality (broad-spectrum noise from brushes), imprecise frequency control, volume and pitch hard to independently control.

### Brushless DC (BLDC) Motors

BLDC motors are significantly more promising:

- **Space Vector Modulation (SVM):** Manipulating motor winding drive signals to induce vibrations at specific frequencies. Achieves ~10 kHz range with a "distinctly chip-tune like" quality.
- **Polyphonic capability:** A single BLDC motor can play chords of **up to 7 simultaneous notes** by superimposing frequencies in the SVM waveform -- impossible with stepper motors.
- **SimpleFOC library:** https://docs.simplefoc.com/ -- Arduino Field-Oriented Control for BLDC motors, community members have built music projects on top of it.

Reference: [Hackaday - Musical Motors, BLDC Edition](https://hackaday.com/2025/09/12/musical-motors-bldc-edition/)

---

## 7. MIDI to Motor Conversion

### Note-to-Frequency Formula

```
frequency_hz = 440.0 * 2^((midi_note - 69) / 12.0)
period_us = 1,000,000 / frequency_hz
```

MIDI note 69 = A4 = 440 Hz. MIDI note 60 = Middle C = ~261.63 Hz. The `period_us` is the interval between consecutive STEP pulses.

### Software Approaches

1. **Pre-processed / Offline:** Parse MIDI file on host, convert to (motor, frequency, duration) commands or G-code. Examples: mid2cnc, midiCNC, MIDI-Stepper-Motor-Music.

2. **Real-time MIDI:** Microcontroller listens for MIDI Note On/Off messages, immediately sets motor step frequency. Uses hardware timer interrupts. Examples: Arduino-MIDI-Stepper-Motor-Instrument, Moppy2.

3. **Hybrid / Buffered:** Host reads MIDI and streams commands to Arduino over serial in real-time. Arduino acts as command interpreter.

### Key Constraint

**One stepper motor = one note at a time.** Polyphony requires multiple motors. MIDI channels are typically mapped 1:1 to motors. Some implementations include note-stealing algorithms.

---

## 8. Hardware Interfaces & Drivers

### Arduino + Stepper Drivers (Most Common)

- **A4988**: 1/16 microstepping, up to 2A/phase, ~$2/board. Most common driver for music projects.
- **DRV8825**: 1/32 microstepping, up to 2.5A/phase. Pin-compatible A4988 replacement.
- **Interface:** Only 2 pins per motor (STEP + DIR). Pulse STEP at desired frequency.
- **Arduino CNC Shield V3:** Holds 4 stepper drivers, pre-wired to Arduino Uno GPIO. The single most popular hardware platform for stepper motor music.

### Floppy Drive Interface (34-pin)

- Pin 20: STEP (active low, pulse to advance one step)
- Pin 18: DIRECTION (high/low selects direction)
- Pin 12: DRIVE SELECT (active low to enable)
- Arduino connects directly -- floppy drives have built-in stepper driver ICs.

### Raspberry Pi GPIO

- Direct GPIO via `RPi.GPIO` has timing jitter (Linux is not real-time OS)
- **pigpio** library uses DMA-based hardware-timed waveforms for precise pulses
- Raspberry Pi Pico (RP2040) PIO state machines are ideal for real-time motor control

### ESC/P Printer Control Libraries (Building Blocks)

| Library | Language | Notes |
|---------|----------|-------|
| [python-escp](https://github.com/yackx/python-escp) | Python | Drive ESC/P printers |
| [escprinter](https://github.com/drayah/escprinter) | Java | Epson ESC/P and ESC/P2, tested with LQ-570 |

---

## 9. Juki Daisy Wheel Printer Analysis

### Motor Systems

The Juki 6100 uses **four distinct motor/actuator systems**:

| Motor | Type | Resolution | Voltage | Purpose |
|-------|------|-----------|---------|---------|
| Daisy Wheel | Rotary stepper | 3.6°/step (100 positions/rev) | +24 VDC | Character selection |
| Carriage | Linear stepper (permanent magnets) | 1/120 inch/step | +30 VDC | Print head horizontal movement |
| Paper Feed | Rotary stepper | 1/48 inch minimum | +24 VDC | Paper advance/reverse |
| Ribbon | DC motor | N/A | +24 VDC | Ribbon advance via spring clutches |
| Hammer | Electromagnetic solenoid | N/A | +30 VDC | Character strike |

**Key difference from Diablo 630:** The Diablo used DC servo motors with feedback (air-core transformer rotary sensors). The Juki uses open-loop stepper motors -- simpler, cheaper, and crucially for music purposes, the steppers produce more controllable and more audible stepping frequencies.

### Control Architecture

- **Master CPU:** 8051 at 7.37 MHz -- receives host data, calculates shortest rotation path
- **Slave CPU:** Second 8051 on SCU-1 board -- generates motor stepping pulses
- **Pulse generation:** Port 1 bits 7-8 generate two square waves at 90° phase offset, decoded to four-phase stepping pulses
- **Motor selection:** VFG gating line (Port 2, bit 2) selects daisy wheel or paper feed motor; PMEN (Port 2, bit 1) enables/disables stepping
- **Carriage:** Constant-current, frequency-modulated driver. Movement by successively changing coil current direction against permanent magnets.

### Critical Limitation

**Multiplexed motor control:** The daisy wheel and paper feed motors share the same four-phase pulse hardware, selected by a gating signal. This means **only one of these stepper motors can be actively stepping at a time**. The carriage linear stepper has its own driver but is coordinated by the same slave CPU.

### Protocol: Diablo 630 (NOT ESC/P)

The Juki uses the **Diablo 630 command set** (a slight superset), NOT Epson ESC/P. This is the standard for daisy wheel printers.

Key escape sequences for motor control:

| Sequence | Function | Motor Affected |
|----------|----------|---------------|
| BS | Backspace 1 position | Carriage |
| HT | Horizontal tab | Carriage |
| LF | Line feed | Paper feed |
| FF | Form feed | Paper feed |
| CR | Carriage return | Carriage (full sweep) |
| ESC BS | 1/120 inch backspace | Carriage (fine) |
| ESC LF | Reverse line feed | Paper feed |
| ESC U | Half-line feed forward | Paper feed |
| ESC D | Half-line feed reverse | Paper feed |
| ESC 3 | Graphics mode ON (1/60" horiz, 1/48" vert) | Both |
| ESC 4 | Graphics mode OFF | Both |
| ESC 5 | Forward print mode | Carriage direction |
| ESC 6 | Backward print mode | Carriage direction |
| ESC / | Enable bidirectional print | Carriage |
| ESC US(n) | Set character spacing index | Carriage step size |
| ESC RS(n) | Set line spacing index | Paper feed step size |

### Interfaces

- **Parallel:** Centronics 36-pin (Amphenol 57-30360), TTL, max 2m cable, 500 CPS max
- **Serial (optional):** RS-232C DB-25, 300-2400 baud, XON/XOFF or ETX/ACK flow control
- **Alternative:** 20mA current loop

### Juki Model Variants

| Feature | Juki 6100 | Juki 6300 | Juki 2200 |
|---------|-----------|-----------|-----------|
| Speed | 18 CPS | 40 CPS | 10 CPS |
| Daisy wheel | TA-compatible, 100 chars | Diablo-compatible, 96 chars | TA-compatible |
| Paper width | 13" max | 16" max | Standard |
| Noise | <63 dB | 60 dB | Unknown |
| Buffer | 2K (expandable to 8K) | Unknown | Unknown |

---

## 10. Applicability to Juki Printers

### Approach 1: Software-Only via Escape Codes (Easiest)

**Method:** Send rapid sequences of carriage movements (BS, HT, CR), line feeds (LF, ESC LF, ESC U, ESC D), and character prints through the standard parallel/serial interface.

**Pros:**
- No hardware modification required
- Works with existing printer firmware
- Can use standard parallel port or USB-to-parallel adapter
- The existing `claude-teletype` project already has Juki profile with escape code support

**Cons:**
- Limited frequency control -- the printer firmware determines motor speeds, not the host
- The Centronics handshaking (BUSY/ACKNLG) limits command throughput to ~500 CPS
- Cannot directly control step frequency -- only request movements at firmware-determined speeds
- Music would be rhythmic patterns of mechanical sounds rather than precise pitches

**Potential technique:** Use **graphics mode** (`ESC 3`) for finer positioning (1/60" horizontal, 1/48" vertical) and rapid micro-movements. Alternate between forward/reverse line feeds (ESC U / ESC D) and micro-backspaces (ESC BS) to create rapid oscillation.

### Approach 2: Bypass Firmware, Drive Motors via Arduino (Most Musical)

**Method:** Disconnect the Juki's slave CPU from the motor drivers. Connect Arduino + stepper drivers directly to the motor coils.

**Pros:**
- Full frequency control over all three stepper motors
- Three independent voices (daisy wheel, carriage, paper feed)
- Can use existing MIDI-to-stepper libraries (Moppy2, MIDI-Stepper-Motor-Music)
- Precise pitch control

**Cons:**
- Requires disassembly and rewiring
- Need to identify motor coil pinouts from the Juki 6100 Technical Manual
- Linear stepper motor (carriage) may need custom driver -- standard A4988 designed for rotary steppers
- Risk of damaging printer
- Loses normal printing functionality (unless switchable)

**Reference project:** [OpenDaisy](https://github.com/bitcraft/opendaisy) -- Arduino firmware that replaces the original MCU in daisy wheel typewriters (Smith Corona, Brother, Nakajima). Uses PlatformIO + custom AccelStepper fork. Directly relevant as a template.

### Approach 3: Intercept Slave CPU Signals (Advanced)

**Method:** Tap into the signal lines between the Juki's slave CPU (8051) and the motor drivers. Inject custom stepping pulses.

**Pros:**
- Could allow switching between normal printing and music mode
- Preserves original hardware integrity

**Cons:**
- Requires detailed analysis of the circuit board
- Timing conflicts with the existing CPU
- Complex signal-level interfacing

### Approach 4: Hammer Solenoid as Percussion

**Method:** Use the electromagnetic hammer (normally for striking characters) as a rhythmic percussion instrument alongside motor tones.

**Pros:**
- Adds a percussive "click" channel to the stepper motor tones
- The hammer produces a sharp, loud transient -- perfect for rhythm
- Could fire the hammer at rhythmic intervals while motors play melody

**Cons:**
- Repeated rapid firing may damage the hammer mechanism
- Requires control of the hammer driver circuit

### Frequency Estimates for Juki Motors

Based on the motor specifications:

- **Daisy wheel:** 100 steps/revolution, 3.6°/step. At typical character selection speeds, likely operates in the 100-500 Hz range. Could potentially be driven faster for higher notes.
- **Carriage:** 1/120 inch/step = 120 steps/inch. At 18 CPS with ~0.1" average character spacing, ~216 steps/sec (~216 Hz). In free movement, could potentially reach higher frequencies.
- **Paper feed:** 1/48 inch/step = 48 steps/inch. Lower frequency operation. At maximum speed, likely 50-200 Hz range.

### Recommended Approach for claude-teletype

Given that `claude-teletype` already communicates with Juki printers via the parallel interface:

1. **Start with Approach 1** (software-only): Add a "music mode" that sends carefully timed sequences of movement commands. Even if precise pitch control isn't possible, rhythmic patterns of carriage movements, line feeds, and character strikes can produce recognizable musical patterns -- similar to the "Symphony for Dot Matrix Printers" project.

2. **Experiment with graphics mode:** `ESC 3` enables 1/60" horizontal and 1/48" vertical resolution, allowing finer-grained movement commands that could approximate frequency control.

3. **Explore timing:** The key question is whether the Juki firmware processes movement commands fast enough to approximate audible frequencies. At 500 CPS throughput, and assuming each movement command is 1-3 bytes, the maximum command rate is ~167-500 commands/second, which falls in the low-frequency audible range (167-500 Hz).

4. **Future: hardware bypass** using OpenDaisy as a reference for direct motor control if software-only approach is insufficient.

---

## 11. Key References & Sources

### Primary Technical Documents

- [Juki 6100 Technical Manual (May 1984)](https://bitsavers.org/pdf/juki/Juki_6100_Technical_Manual_May84.pdf) -- Full schematics, motor drivers, CPU architecture
- [Juki 6100 Operation Manual (Sep 1983)](http://www.bitsavers.org/pdf/juki/Juki_6100_Operation_Manual_Sep83.pdf) -- Complete escape code reference, interface pinouts
- [Diablo 630 Protocol (Wikipedia)](https://en.wikipedia.org/wiki/Diablo_630)

### Most Relevant GitHub Projects

| Project | Stars | URL |
|---------|-------|-----|
| Moppy2 | 331 | https://github.com/Sammy1Am/Moppy2 |
| midi-m300 | 121 | https://github.com/alexyu132/midi-m300 |
| MIDI-Stepper-Motor-Music | 113 | https://github.com/barlowtj48/MIDI-Stepper-Motor-Music |
| Arduino-MIDI-Stepper-Motor-Instrument | 106 | https://github.com/jzkmath/Arduino-MIDI-Stepper-Motor-Instrument |
| mid2cnc | 47 | https://github.com/TeamTeamUSA/mid2cnc |
| OpenDaisy (daisy wheel typewriters) | - | https://github.com/bitcraft/opendaisy |

### Articles & Demos

- [Hackaday: Eye of the Tiger on Dot Matrix](https://hackaday.com/2014/02/20/eye-of-the-tiger-as-played-by-a-dot-matrix-printer/)
- [Paul Slocum: Dot Matrix Synth](https://www.qotile.net/dotmatrix.html)
- [Alexis Garado: Stepper Motor Music](https://garado.dev/posts/stepper-motor-music/)
- [Parts Not Included: Musical Floppy Drives](https://www.partsnotincluded.com/getting-started-musical-floppy-drives/)
- [Lucas Oshiro: Playing Songs in a 3D Printer](https://lucasoshiro.github.io/software-en/2020-07-31-music_gcode/)
- [SimpleFOC: BLDC Motor Music](https://community.simplefoc.com/t/simplefoc-playing-sweet-music/149)
