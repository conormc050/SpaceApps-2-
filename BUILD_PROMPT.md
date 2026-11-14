# Prompt for the development chat

Paste everything below this line into a new chat started in this folder.

---

You are continuing a student team's NASA Space Apps 2026 project: a wearable health monitor for astronauts with a gamified LCD screen and a ground summary for flight surgeons. Submission closes Sunday 15 November 2026, 11:59 pm. Tomorrow morning the team connects a real Arduino Uno, so the device path comes first.

## Read these before writing anything

1. `FABLE_PROMPT.md`: the full brief. Its "How to work with us", "Hard rules", "Decisions already made", "Alert and advice rules" and "Checks that must pass" sections all still apply. Read them in full.
2. `config/settings.json`: every number, threshold, text label, pin and scenario value. Never hard-code a value that belongs here. If you need a new number, add it here.
3. `healthsim/config.py`, `healthsim/protocol.py`, `healthsim/tags.py`: finished foundation code. Use it, do not rewrite it.
4. `run_checks.py`: 138 checks pass now. It must still end in `RESULT: PASS` after every step.

## Working rules

- Keep replies short. Code goes in files, never pasted in chat. No code comments. No JavaScript without asking.
- Python is `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (not on PATH). Installed: numpy, pandas, scipy. Not installed: Pillow and pyserial. Install them when first needed and add them to `requirements.txt`.
- One step per reply. After each step run `run_checks.py`, add checks for what you built, report the pass count and stop. If a check fails, show the output; do not loosen a limit to make it pass.
- Do not edit `FABLE_PROMPT.md`, and do not change `protocol.py` or the `serial` section of the settings without asking, because the Arduino sketch depends on them.
- There is no Arduino compiler on this machine. Sketches cannot be tested here, so keep them small and plain, and say clearly that they are untested.

## What the Arduino can and cannot do

An Uno has 2 KB of memory and cannot run Python. The split is fixed:

- **Uno**: draws LCD frames it receives, reads the tag reader and buttons, drives the buzzer and status lights. Nothing else.
- **Host** (laptop or Raspberry Pi, over USB serial at 9600 baud): simulation, baselines, alerts, scoring, screen content.

The wire format is in `settings.json` under `serial` and implemented in `healthsim/protocol.py`. Host to Uno: `L<row><text>` sets a row, `G<slot><16 hex>` defines a custom character, `C` clears, `S<G|A|R|O>` sets the status light, `B<ms>` beeps. Uno to host: `READY <cols> <rows>`, `T<tag id>`, `K<1-4>`, `V<name>=<number>`. Bytes 128 to 135 inside text mean custom characters 0 to 7. Every line ends in a newline and is under 40 bytes. Pins are under `hardware`; they are chosen so the LCD and the tag reader do not clash.

## Existing code you are changing

- `simulate.py` simulates one person with 7 to 9 h sleep, random exercise, step counts and timestamps without a time zone. `generate(out_dir, **overrides)` writes `SIMULATED_*.csv` plus a manifest.
- `gamify.py` scores steps and sleep hours, which breaks two hard rules. It gets replaced in step 3.
- `sleep.py`, `heart.py`, `skin_temp.py`, `loaders.py`, `pipeline.py` work and are checked. Reuse them per crew member.
- Old single-person files sit directly in `data/` and `output/`. Delete them once `data/ABC/`, `data/DEF/` and `data/cabin/` are being written.
- Some existing checks assert the old behaviour (7 to 9 h sleep, step points). Replace those checks with the new rule when you change the behaviour, and say which ones you replaced.

## Build order (changed so the device works by morning)

1. **Multi-crew simulator.** ABC and DEF from `crew`, `scenarios`, `schedule`, `sleep` and `simulation` in the settings: 14 days (7 calibration, 7 scenario), ISS-like sleep, one scheduled 2 h exercise block a day, UTC timestamps, no steps anywhere (movement and exercise minutes instead), ground-truth labels kept. Files go to `data/<crew>/` with a manifest built from `config.manifest_header()`.
2. **Baselines and alerts.** `baseline.py`: first-week mean and day-to-day spread per person. `alerts.py`: the rules table, using the `baselines` rule and each indicator's settings; green, amber, red; one advice line and one contact line per alert. Indicators whose data does not exist yet report "no data" and never alert.
3. **Scoring.** Rewrite `gamify.py` from the `scoring` settings: points for check-ups and sleep scans, on-time bonus, multiplier, shared scoreboard sorted by points. No health value may change a score.
4. **LCD screens.** `lcd.py`: build each screen in the `lcd.screens` list as text frames that pass `protocol.check_text`, with custom characters for animations, and render PNG and GIF pictures into `assets/` named by slide (for example `slide4_lcd_status.png`).
5. **Device.** `arduino/lcd_display/lcd_display.ino`: the full firmware for the protocol above, with `USE_I2C_LCD` and `USE_RFID` switches at the top, a fixed 48-byte line buffer, no `String` class. `arduino/tag_reader/tag_reader.ino`: a minimal stand-alone reader test. A host script that replays simulated data either to pictures or to a serial port (`--port COM3`), and a way to enrol a real card through `tags.enrol` so its ID is never written to the repository.
6. **Blood panel, blood sugar, blood pressure** (`blood.py`), then connect the blood-count alert.
7. **Cabin environment and effect analysis** (`cabin.py`), including the humidity effect of zero, which the analysis must not report as a contributor.
8. **Mood interpretation** (`mood.py`): questionnaire weighting, mismatch flag, follow-up question.
9. **Earth link and dashboard** (`earthlink.py`, `dashboard.py`, `dashboard/index.html` as static HTML with inline SVG).
10. **Deck pictures, README and the full check list** from `FABLE_PROMPT.md`.

If time runs short, steps 1 to 5 plus 9 and 10 make a complete submission; say so rather than rushing 6 to 8.

## Things already found that you must respect

- DEF's skin temperature rise is set to 0.9 C, not the 0.6 C first suggested. A 0.6 C rise over two days peaks at 0.45 C on the "24 h mean against the prior 72 h" rule and can never trip the 0.5 C threshold.
- Night-to-night sleep spread is 0.35 h per person. The 0.7 h in the brief is treated as the spread between people. With 0.7 h per person, DEF's short-sleep alert fired in only about 65 percent of trials.
- DEF's resting heart rate rise of 12 BPM fires in about 98 percent of trials. If an expected DEF alert does not fire for a seed, raise the scenario value in the settings and report it. Never loosen the rule, and never let ABC alert.
- Sources marked `"source_verified": false` or `"verified": false` in the settings have not been checked against the papers. List them in the README as unverified until someone checks them.

## First reply

Confirm in under 15 lines that you have read the four items above and state what step 1 will change. Then do step 1.
