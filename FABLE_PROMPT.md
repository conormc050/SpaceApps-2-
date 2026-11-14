# Prompt for the build chat

Paste everything below this line into the new chat. Start the chat in the folder that holds the existing `healthsim/` code.

---

You are helping a student team build a project for the NASA Space Apps Challenge 2026 (hackathon 14 to 15 November 2026), challenge "Create Health Monitoring Software for Astronauts on Space Missions". Submission closes Sunday 15 November, 11:59 pm local time.

## How to work with us

- Keep explanations brief.
- Deliver code as files in the project folder, never pasted inline in chat.
- Do not add code comments.
- Do not change any JavaScript unless we ask. Prefer generating the Earth dashboard as static HTML, SVG or PNG from Python. If JavaScript turns out to be unavoidable, ask first.
- First reply: confirm the plan and the file structure in under 25 lines. Then build step by step, running the checks after each step. Ask a question only when blocked.
- On Windows, `python` is not on PATH. Use `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`. Dependencies are numpy, pandas and scipy.
- Report results faithfully. If a check fails, say so with the output.

## What we are building

A wearable health monitor for astronauts with a gamified LCD screen and a ground-facing summary for flight surgeons on Earth. Our submission is a 7-slide deck on a public link plus a public GitHub repository. There is no live demo. The kit hardware is only photographed for the deck. So every screen and chart must also exist as a picture (PNG or GIF, each under 10 MB).

Slide plan: 1 title and problem, 2 the five hazards mapped to what we monitor, 3 how the system works, 4 astronaut screen (status, advice, scoreboard), 5 Earth dashboard, 6 real versus simulated and what the checks show, 7 limits, next steps and sources.

The challenge asks for a visual tool that helps astronauts assess their own health, gives guidance on actions, says when to involve flight surgeons, and may use any data that represents a health indicator, including simulated blood sugar. NASA's five hazards: space radiation, isolation and confinement, distance from Earth, gravity fields, hostile closed environments.

## Hard rules (never break these)

1. Every simulated value, file and screen is labelled SIMULATED. No real person's data anywhere.
2. Simulated data validates logic only, not accuracy. Say so in the README.
3. Skin temperature is skin surface temperature, never core temperature. Label it that way everywhere.
4. Mood is a non-clinical self-reported wellbeing check-in. Never frame it as clinical.
5. We are not medical advice. Advice is general wellness for small things, always with a clear point to contact the flight surgeon.
6. Radiation: we do not measure dose. The blood-count trend is an exposure indicator only, with many possible causes.
7. Points reward taking check-ups, never health values.
8. The arcade-style scoreboard is our own design. Do not use any game's name, characters, art or music.
9. Do not use NASA logos, flags or mission identifiers.
10. Never put a real card or tag ID in the repo. Map tags to crew profiles through salted hashes in a config file.
11. AI disclosure: the submission must describe how AI tools were used. Code and data generated with AI must be acknowledged in descriptive text and metadata, so put the acknowledgement in the README and in each data manifest (we do not want code comments). Any AI-made images need a visible watermark.

## What already exists (Python package `healthsim/`, 124 checks passing)

- `simulate.py`: one simulated person, minute-level sleep/activity/heart rate/skin temperature, mood daily, 50 Hz pulse-sensor windows, ground-truth labels, `SIMULATED_` file prefix, manifest.
- `loaders.py`, `sleep.py` (actigraphy-style sleep estimate), `heart.py` (peak detection), `skin_temp.py` (trend alerts, 24 h mean versus the prior 72 h), `gamify.py` (points), `pipeline.py` (writes summaries to `output/`).
- `run_checks.py` at the project root: normal and stress scenarios, determinism, rules.

Known problems to fix: `gamify.py` scores steps, which do not exist in microgravity; the simulator assumes 7 to 9 h sleep; there is only one person; alerts use fixed thresholds.

## Decisions already made

- Crew: two simulated astronauts, ABC (a normal week, must raise no alerts) and DEF (a worrying trend that turns amber). Suggested DEF trend: skin surface temperature up about 0.6 C over two days, sleep about 1.5 h under baseline, resting heart rate about 12 BPM up, white cells and platelets down about 25 percent. Make these settings.
- Sleep: ISS-like. About 6 h a night with a spread of about 0.7 h (the Barger et al. 2014 Lancet Neurology study of NASA crews reports 6.09 +/- 0.67 h on the ISS against 8.5 h scheduled; verify at https://pmc.ncbi.nlm.nih.gov/articles/PMC4188436/).
- Baselines: each person's first week of calibration gives their average and day-to-day spread. Amber means more than two spreads from baseline for 2 days in a row, or a fixed minimum change if larger (for example 0.5 C for skin temperature).
- Multiplier: starts at 1x, +0.25x per on-time check-up in a row, caps at 2x, resets to 1x after a miss.
- Mood goes to Earth only when abnormal (score of 2 or below for 3 days, a drop of 2 or more in a day, or answers that keep disagreeing with sleep and heart data). The astronaut sees any such flag first.
- Simulated time is sped up: a simulated week plays in about a minute.
- Scenario label: "ISS now, Mars-ready", with a link-delay setting (near real time with gaps for the ISS, minutes of delay for Mars).

## Alert and advice rules (demo values, not clinical limits)

| Indicator | Amber when | Quick help | Contact flight surgeon when |
|---|---|---|---|
| Resting heart rate | 10+ BPM above baseline for 2 days | Sit 5 min, slow breathing, measure again | Still high after re-measuring, or you feel unwell |
| Skin surface temperature | 24 h mean 0.5 C above the 72 h baseline for 6 h | Rest, check sensor fit and cabin temperature, measure again | Rise continues next day |
| Sleep | 2 nights at least 1 h below own baseline | Dim lights and cut noise an hour before bed | 3 or more short nights |
| Mood check-in | See the mood rule above | Short break, talk to a crewmate, answer again | Low scores continue 3 more days |
| Cabin air | Air-quality index above cabin baseline for 1 h | Check vents, tell the crew lead | Does not clear |
| Cabin noise and light at night | Well above usual sleeping-hours level | Move, dim or use ear protection | Sleep stays short |
| Blood sugar (simulated) | Outside personal usual range | Log it, measure again, eat or drink per nutrition plan | Still out of range after re-measuring |
| Blood pressure (simulated) | 2 readings above baseline in the same body position | Rest 5 min, measure again in the same position | Stays high |
| Blood counts (simulated) | White cells and platelets both trend below baseline across check-ups | Nothing to self-treat | Straight away; many possible causes; not a dose |

## What to build, in this order

1. **Multi-crew simulator.** Extend `simulate.py` for ABC and DEF with the scenario settings above, ISS-like sleep, a scheduled daily exercise block of about 2 h, UTC timestamps everywhere, and no steps (use movement and exercise minutes). Keep ground-truth labels.
2. **Blood panel.** Simulate the lock-in amplifier output of an impedance cytometer as in Furniturewalla et al., Microsystems & Nanoengineering 4:20 (2018), https://www.nature.com/articles/s41378-018-0019-0: about 1 kHz sampling, a pulse per cell, each pulse a positive peak followed by a negative overshoot, noise and baseline drift, overlapping cells counted as one. Count peaks with a threshold plus a minimum run of consecutive samples (the paper uses 0.5 V and 4 samples; reproduce the idea, not necessarily the values). Convert counts to concentrations with a dilution factor and volume. Report red cells, white cells and platelets, with a data-quality note when overlap undercounting is likely. Be honest in the README: the paper demonstrates counting; telling cell types apart is listed there as future work, so our amplitude-based separation is a simplification. Typical adult ranges (verify before use): red cells about 4.2 to 5.9 million per microlitre, white cells about 4 to 11 thousand, platelets about 150 to 400 thousand. Also simulate blood sugar (mg/dL) and blood pressure with a body-position field (restrained, free-floating, after exercise), both labelled as planned sensors.
3. **Cabin environment and its effect.** Simulate cabin air-quality index, humidity, temperature, pressure, noise and light, with known effect sizes on sleep and mood built in. Write an analysis that estimates those effects and report "possible contributors", never causes. Add a check that the analysis recovers the built-in effects.
4. **Baselines and mood interpretation.** First-week calibration per person. A short self-written questionnaire (about 10 items, our own wording) estimates answer style, for example someone who tends to say "fine". It adjusts how much the mood self-report is weighted, never labels mood. Add the mismatch flag when self-report disagrees with sleep and heart data, with a concrete follow-up question. Do not use gender or personality as priors for mood. An optional sex setting may select physiological reference ranges only.
5. **Alerts, advice and scoring.** Implement the rules table with baseline-relative amber logic. Rework `gamify.py`: points for completing check-ups and sleep scans, an on-time bonus, the multiplier, no points from health values, a shared scoreboard of initials and points (for example ABC 14000, DEF 12490). Put all numbers in one config.
6. **Astronaut LCD.** Default to a 16x2 character LCD (we have not confirmed the model; keep the size configurable). Screens: SIMULATED banner, tag login, mode (check-up or sleep scan), scanning animation, status per area, one advice line that scrolls, score with multiplier, scoreboard, level-up animation. Use the 8 custom characters for animations. Provide a Python renderer that produces PNG and GIF pictures of the LCD, and an Arduino Uno sketch that draws frames received over serial (LiquidCrystal, with an I2C option). The host replays simulated data.
7. **Tag login.** A config maps hashed tag IDs to crew profiles. Provide a reader sketch for an RC522-type 13.56 MHz module and a simulated tap for the pictures.
8. **Earth link and dashboard.** Build a compact summary payload with statuses, amber and red flags, trends, data-quality notes and mood only when abnormal. Add store-and-forward batching with a configurable delay and dropouts. Build the ground dashboard as static HTML, SVG or PNG: per-astronaut status, trends over time, alerts, data quality and a transmission log.
9. **Deck assets, README, checks.** Export every picture the deck needs. Write the README (what it is, how to run, assumptions with sample rates and noise levels, real versus simulated table, limits, sources, AI-use acknowledgement). Extend `run_checks.py` so it reports pass or fail for everything below.

## ISS-specific factors to account for (verify and cite before using in the deck)

- No steps in microgravity. Use movement and exercise minutes.
- About 2 h of exercise a day is scheduled and affects heart rate, temperature and activity.
- No up or down, so log body position and recent exercise with blood pressure.
- Fluid shifts in flight, so baselines are set in flight, with the pre-flight value kept as reference only.
- The ISS runs on UTC with many sunrises a day. Light analysis follows the crew schedule.
- Cabin CO2 and noise differ from Earth. Our gas sensor gives a relative index only.
- Sleep aids are common (Barger et al.). Offer an optional "took a sleep aid" tick.

## Checks that must pass

ABC raises no alerts and DEF raises each expected alert within a stated delay; simulated data is labelled everywhere; mood appears in the Earth payload only when abnormal; the multiplier steps 0.25x, caps at 2x and resets; no points come from health values; no step counts are used; the scoreboard sorts correctly; LCD lines never exceed the screen width; cabin-effect analysis recovers the built-in effects; same seed gives identical files; stress scenarios (more noise and dropouts) still pass with looser limits.

## Hardware (for the deck photo only)

Arduino Uno, Raspberry Pi, RFID/NFC reader, LCD, IMU, sound, humidity, gas, pressure and ultrasonic sensors, buzzer, relay, LEDs, motor, breadboard parts. Still to source: pulse sensor, DS18B20 skin temperature probe, light sensor (LDR), 4 push buttons.

## Reference links

Challenge: https://www.spaceappschallenge.org/2026/challenges/health-monitoring-software/
Submission guide: https://www.spaceappschallenge.org/resources/project-submission-guide/
Judging criteria (1 to 5 each): Impact, Creativity, Validity, Relevance, Presentation.
Sparse CBC radiation paper (mouse only, an indicator not a dose calculator): https://pmc.ncbi.nlm.nih.gov/articles/PMC13639052/
Core body temperature in astronauts: https://www.nature.com/articles/s41598-017-15560-w
