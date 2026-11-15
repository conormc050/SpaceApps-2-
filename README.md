# S.G.U.F. — A Gamified Health Monitoring System for Astronauts

**Team Sol Searchers · NASA Space Apps Challenge 2026 · HackAthlone (Athlone, Ireland)**
Challenge: *Create Health Monitoring Software for Astronauts on Space Missions*

Zack Dolan (software developer) · Amelia Reinhardt (microbiologist) · Jack Brady (design engineer) · Conor McEvoy (game developer)

> Every health value in this repository is **SIMULATED** or comes from a hobby-grade test sensor on our own kit. Nothing here is medical data or medical advice. See [Disclaimers](#disclaimers).

---

## Why

Not every astronaut is a doctor. On a long mission the crew has to run its own health checks, read the results, and decide when to call Earth, all while the link to a flight surgeon gets slower the further they travel. We wanted a system that:

- lets an astronaut check themselves in a few minutes without medical training,
- removes human error from reading and reporting the numbers,
- protects the crew's mental bandwidth by explaining results in calm, plain language,
- tells the crew clearly when to involve a flight surgeon, and
- makes a repetitive daily chore something the crew actually wants to do.

## What S.G.U.F. does

1. **Tag login.** The astronaut taps their RFID tag on the wearable. Tag IDs are mapped to crew profiles through salted hashes in `config/tags.json`; no real card ID is stored in the repository.
2. **Quick check-up, twice a day.** The wearable reads pulse (MAX30105 pulse sensor) and movement (MPU6050 IMU). A short on-screen questionnaire covers activity, posture, back and hip aches, and a 1 to 5 mood check-in.
3. **Compared with your own baseline.** The habitat hub (Raspberry Pi 5) stores every reading and compares it with that astronaut's own first-week baseline, not a population average.
4. **Traffic light and plain words.** The wrist shows green (normal), amber (check again) or red (contact the flight surgeon), and the LCD and crew app show a short, reassuring message, for example: *"Your red blood cell count is a bit lower than usual. This is very common in spaceflight due to fluid shifts… Mission Control has automatically received these results."*
5. **Earth gets the detail.** A flight-surgeon dashboard receives status per astronaut, amber and red flags, and mood only if abnormal, sent in batches so it works over an ISS-style link (1 to 2 s) or a Mars-style link (3 to 22 min).
6. **Points for showing up.** Each check-up and sleep scan earns points, with an on-time bonus and a multiplier that grows with consecutive on-time check-ups. Points reward taking check-ups, **never** the health values, so nobody scores lower for a worrying reading. A mission scoreboard is normalised per day in space so long missions do not win by default.
7. **Planned: microneedle blood panel every two days.** A microneedle patch would read white cells, platelets and red cells. A fall in white cells and platelets against baseline is treated as an *exposure indicator* that prompts a call to the flight surgeon. It is not a radiation dose.

## How it maps to NASA's five hazards of spaceflight

| Hazard | What S.G.U.F. watches |
|---|---|
| Space radiation | Blood-count trend against the astronaut's own baseline (simulated, indicator only) |
| Isolation and confinement | Daily mood check-in, points and a shared mission scoreboard |
| Distance from Earth | Decisions made in the habitat; batched store-and-forward summaries to Earth |
| Gravity fields | Posture and back/hip ache questions, movement and exercise minutes (no step counts in microgravity) |
| Hostile closed environments | Cabin temperature, humidity and pressure logged alongside sleep and mood |

## Real versus simulated

| Indicator | Source |
|---|---|
| Pulse (BPM) | Real: MAX30105 sensor on our Arduino kit |
| Movement / exercise minutes | Real: MPU6050 IMU |
| Tag login | Real: MFRC522 RFID reader |
| Cabin temperature, humidity, pressure | Real: Raspberry Pi sensors (`tools/sensor_test.py`) |
| Mood, posture, aches | Real: self-reported, non-clinical |
| Skin surface temperature | Simulated (skin surface, never core temperature) |
| Sleep hours | Simulated, ISS-like (~6 h a night, after Barger et al. 2014) |
| Blood pressure | Simulated, logged with posture |
| Blood counts (WBC, platelets, RBC) | Simulated, planned microneedle sensor |
| Cabin air quality, noise, light | Simulated |

Two simulated crew members are generated: **ABC** has a normal fortnight and must raise no alerts; **DEF** develops a worrying trend in the second week (shorter sleep, higher resting heart rate, higher skin temperature, falling white cells and platelets) and turns amber. The simulator writes `data/<crew>/SIMULATED_*.csv` plus a manifest. All thresholds are demo values, not clinical limits.

## Hardware

- Arduino (Mega-class board in the kit): MAX30105 pulse sensor, MPU6050 IMU, MFRC522 RFID reader, 16x2 I2C LCD, red/amber/green LEDs, joystick, HC-05 style Bluetooth module
- Raspberry Pi 5 habitat hub with DHT11 temperature/humidity sensor
- Microneedle patch: proposed only, researched (materials, sterilisation, point-of-care blood counting), not built

## Software

- Python 3.12: NumPy, pandas, SciPy, pyserial, Pillow, Streamlit (crew app), Playwright and imageio-ffmpeg (demo recording)
- Arduino C++: MFRC522, SparkFun MAX3010x, Adafruit MPU6050, Adafruit Unified Sensor, LiquidCrystal_I2C
- SQLite for the hub store, static HTML/SVG for diagrams

## Repository layout

```
arduino/            Arduino sketches: lcd_display (LCD protocol firmware), tag_reader, bluetooth_test
sketch_nov14b/      Integrated wearable sketch used on the day: pulse, IMU, RFID, LCD, traffic light
healthsim/          Python package
  simulate.py         multi-crew simulator (ABC, DEF)
  loaders.py          CSV loaders
  sleep.py            actigraphy-style sleep estimate
  heart.py            pulse peak detection
  skin_temp.py        skin surface temperature trend
  gamify.py           points, multiplier, scoreboard
  pipeline.py         runs the analysis and writes summaries
  protocol.py         host <-> Arduino serial protocol
  tags.py             salted tag-to-crew mapping
  bridge.py           habitat hub: SQLite store and HTTP bridge
  vitals_page.py      Streamlit crew app (Live Vitals & Baseline)
  diagrams.py         draws the system-flow and two-checks diagrams in assets/
  demo_video.py, record_demo.py   demo screencast and scoreboard renders
config/settings.json  every number, threshold, label, pin and scenario value
config/tags.json      salted tag hashes
data/ABC, data/DEF    SIMULATED_* CSVs and manifests
assets/               diagrams, LCD renders, demo GIF/MP4
run_checks.py         307 automated checks (normal and stress scenarios, determinism, rules, bridge, diagrams)
submission/           7-slide demo deck (PPTX and PDF)
```

Several modules were planned but not finished in the 48 hours: `alerts.py`, `baseline.py`, `blood.py`, `cabin.py`, `earthlink.py`, `lcd.py`, `mood.py` and `dashboard.py` are empty placeholders. Their behaviour is described in `FABLE_PROMPT.md` and `BUILD_PROMPT.md` and is shown as simulated or planned in the deck.

## Running it

```
pip install -r requirements.txt
python run_checks.py
python -m healthsim.simulate
python -m healthsim.pipeline
streamlit run healthsim/vitals_page.py
```

Flash `sketch_nov14b/sketch_nov14b.ino` to the Arduino with the libraries listed above. `healthsim/bridge.py --port COM3` (or `/dev/ttyUSB0`) connects the hub to the wearable over serial.

## Disclaimers

- Every simulated value, file and screen is labelled **SIMULATED**. No real person's data appears anywhere.
- Simulated data validates the logic only, not accuracy. All thresholds are demo values, not clinical limits.
- Skin temperature is skin **surface** temperature, never core temperature.
- Mood is a non-clinical, self-reported wellbeing check-in.
- The blood-count trend is an exposure indicator only, with many possible causes. We do not measure radiation dose.
- This project is not medical advice. Any advice shown is general wellness guidance, always with a clear point at which to contact the flight surgeon.
- Sources marked `"source_verified": false` in `config/settings.json` (Barger et al. 2014 sleep figures; Furniturewalla et al. 2018 impedance cytometry) were used from memory of the papers and have not yet been re-checked line by line.

## Use of AI tools (Super Intelligence disclosure)

AI tools were used and are acknowledged here and in every data manifest (`data/*/SIMULATED_manifest.json`, field `ai_acknowledgement`):

- **Anthropic Claude**: generated most of the Python in `healthsim/`, `run_checks.py`, the Arduino protocol firmware in `arduino/`, the simulated datasets, the diagrams in `assets/`, and helped draft slide text. The full prompts are in `FABLE_PROMPT.md` and `BUILD_PROMPT.md`.
- **Google Gemini**: used by one teammate for research summaries and for help drafting the plain-language on-screen health messages. Those chats were not saved, so the Gemini prompts cannot be reproduced here; the Claude prompts above are complete.

All AI output was reviewed, tested and edited by the team. The project uses no NASA logos, flags or mission identifiers. The arcade-style scoreboard is our own design and borrows no game's name, characters, art or music.

## NASA data and resources

- 5 Hazards of Human Spaceflight, NASA Human Research Program: https://www.nasa.gov/hrp/hazards/
- NASA HRP Human Spaceflight Risks: https://www.nasa.gov/hrp/risks/
- NASA HRP Ongoing Research: https://www.nasa.gov/hrp/ongoing-hrp-research/
- NASA Manages Astronaut Health with Effective Diagnostics Research (NASA Glenn): https://www.nasa.gov/centers-and-facilities/glenn/nasa-manages-astronaut-health-with-effective-diagnostics-research/
- The Human Body in Space (NASA HRP): https://www.nasa.gov/humans-in-space/the-human-body-in-space/
- NASA public-domain Earth and space imagery used in the deck: https://images.nasa.gov/

## Space agency partner and other resources

- Canadian Space Agency, Why do we conduct science experiments in space?: https://www.asc-csa.gc.ca/eng/iss/science/why-do-we-conduct-science-experiments-in-space.asp
- Canadian Space Agency, Monitoring radiation and astronaut health (2026): https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp
- Barger et al. 2014, Prevalence of sleep deficiency and use of hypnotic drugs in astronauts, Lancet Neurology: https://pmc.ncbi.nlm.nih.gov/articles/PMC4188436/
- An integrated wearable microneedle array for the continuous monitoring of multiple biomarkers in interstitial fluid, Nature Biomedical Engineering: https://www.nature.com/articles/s41551-022-00887-1
- An epidermal patch for the simultaneous monitoring of haemodynamic and metabolic biomarkers, Nature Biomedical Engineering: https://www.nature.com/articles/s41551-021-00685-1
- Furniturewalla et al. 2018, Fully integrated wearable impedance cytometry platform, Microsystems & Nanoengineering: https://www.nature.com/articles/s41378-018-0019-0
- Biological implications of polydimethylsiloxane-based microfluidic cell culture (PMC): https://pmc.ncbi.nlm.nih.gov/articles/PMC2792742/
- Less Is More: Oligomer Extraction and Hydrothermal Annealing Increase PDMS Adhesion Forces (PMC): https://pmc.ncbi.nlm.nih.gov/articles/PMC9866318/
- FDA 510(k) review K190225, point-of-care blood count analyser: https://www.accessdata.fda.gov/cdrh_docs/reviews/K190225.pdf
- FDA 510(k) review memorandum K161521: https://www.accessdata.fda.gov/cdrh_docs/reviews/K161521.pdf
- HemoScreen, complete blood count at the point of care (Aidian): https://www.aidian.eu/no/nyheter/hemoscreen-complete-blood-count-at-the-point-of-care
- Stainless Steel Passivation (CSI): https://www.csidesigns.com/blog/articles/passivation-of-stainless-steel-what-is-it-and-how-does-it-work
- 304 Stainless Steel Pickling and Passivation procedure: https://www.electroplatingmachines.com/news/304-stainless-steel-pickling-and-passivation-detailed-procedure.html
- Raspberry Pi 5 photo: Suyash Dwivedi, CC BY-SA 4.0, via Wikimedia Commons: https://commons.wikimedia.org/wiki/File:Raspberry_Pi_5.jpg
- Open-source libraries: NumPy, pandas, SciPy, pyserial, Pillow, Streamlit, Playwright, imageio-ffmpeg, MFRC522, SparkFun MAX3010x, Adafruit MPU6050, Adafruit Unified Sensor, LiquidCrystal_I2C

## Licence

Code and simulated data: MIT. Team photos and the Sol Searchers logo remain the team's own.
