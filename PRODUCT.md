# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Undecided. The web technology for `apps/dog-simulator` is an open decision (ADR 0001 leaves it to be done). The brain and sim host stay Python (uv workspace); the simulator is a separate web app with its own tooling.

## Users

Primary: the team's software developers, building and debugging the dog's brain (dog-core) without the robot. They run full competition runs, test commands live via webcam and microphone, repeat bone searches, and need to see at any moment what the dog recognized, what state it is in, and why it decided what it did.

Secondary, and the UI must still read clearly for them:
- the whole team, checking the concept end to end and agreeing on the dog's behaviour;
- supervisors at MS3 (04.12.2026), seeing the first working version in a demo;
- PREN2 hardware tests, comparing real runs with simulated ones.

## Product Purpose

dog-simulator is the dog's world and body in a browser: a 3D rebuild of the competition field that dog-core runs against, so the team can develop and test the brain without hardware. It makes command recognition and the bone search visible, testable and repeatable (task section 3.3).

Success: dog-core completes a full competition run against the virtual dog and field; any moment of a run is understandable; situations can be set up and rerun; logic errors are found before parts are bought or built.

Not the goal: realistic physics, or replacing tests on the real robot.

## Positioning

One brain, two bodies. The simulator never contains the brain; the same Python dog-core runs against the simulator (via `apps/sim-host`) and on the Raspberry Pi (`apps/robot`). Only the adapters differ, and `packages/dog-protocol` is the single contract between simulator and sim host. dog-core only receives what a real sensor would report; the world itself never crosses.

## Operating Context

- Runs on a team laptop, beside the Python sim host process; the person in front of the laptop can act as the referee via webcam and microphone.
- Modes: Live (place dog, bone and referee yourself; give commands live), Scenario (scripted setup, automatic pass/fail), Replay (PREN2; inspect a recorded run on a timeline, candidate viewer Rerun).
- Perception levels per sensor and scenario: Injected (ready-made detections), Rendered (dog's-eye images of the 3D scene, PREN2), Real (laptop webcam and microphone).
- The competition run is the reference: start field, 2 voice and 2 gesture commands acknowledged face to face, SUCH starts the search and a 2-minute clock, dog finds, touches and reports the bone, returns head first and sits with a sound. E-stop interrupts at any time.
- Used for MS3 demos, and for screenshots and video in the project report.

## Capabilities and Constraints

- Scene at true scale, only what sensors or the run need: 30° search segment of radius 5 m in tape, pylons at the corners, 20 × 50 cm start field, interaction area around it, a 21 cm white bone, a stand-in referee, a simple dog body with a head camera, plain indoor floor.
- Must be visible: the scene, what the dog sees, what was recognized, the dog's state and why.
- Behaviour states: IDLE → SEARCH → FOUND → RETURN → SIT. Commands: voice HIER, BRAV, SITZ, SUCH; gestures SITZ, PLATZ, AUF.
- Sim time is owned by the simulator: pause, step, speed up.
- MS3 scenarios: full competition run, search only, commands only, failure cases (unknown word, unclear gesture, bone at the edge, E-stop, search past 2 min).
- MS3 priorities in order: full run with injected detections; real commands; demo-ready visuals. Replay, Rendered perception, the trick and a live view of the real robot are PREN2.
- Terminology: "dog-core" means the brain (packages `dog-core`, `dog-behavior`, `dog-perception`, `dog-recorder`). See `GLOSSARY.md` and `docs/concepts/`.
- Open: interaction area R 1.5 m (drawing) vs D 1.5 m (text); referee position and the dog's starting heading; how injected detections get realistic errors; failure reactions; how placing works in the 3D view; the camera switch rule; scenario file format.

## Brand Commitments

- Interface text in English. Command names stay German as the competition uses them (SITZ, PLATZ, SUCH, HIER, BRAV, AUF).
- Domain names match the concept docs (modes Live / Scenario / Replay; perception levels Injected / Rendered / Real; block names from the architecture concept).
- Look: close to the category standard for robotics tools, but light theme (not dark), professional and light in weight (thin type, no heavy blocks), and no stock "AI default" fonts (stated by the team, 2026-11-06).

## Evidence on Hand

- Concepts: `docs/concepts/simulator.md`, `docs/concepts/architecture.md`, with diagrams in `docs/concepts/images/` (field, blocks, overview, jobs, loop).
- Decision: `docs/adr/0001-web-3d-simulator.md`.
- Untracked behaviour reference: `apps/sim-host/prototype/pygame_sim.py` (2D Cockpit, Test bench, Replay front-ends). Ideas only, not a visual reference.
- No real-run recordings, measured detection rates, or robot hardware data yet; do not fabricate them.

## Product Principles

1. Show why, not just what: every visible action traces back to a recognition and a state.
2. The world never leaks into the brain: the UI may show truth, but the dog acts only on sensor data, and the UI keeps the two distinguishable.
3. Repeatable over pretty: a scenario that reruns identically is worth more than a richer scene.
4. Scope to the competition: model only what the field, the sensors or the run need.
5. Developer-dense, demo-legible: built for debugging, readable when a supervisor is watching.
