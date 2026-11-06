# 1. Web 3D simulator instead of a 2D Python simulator

Date: 2026-11-06 · Status: accepted

## Context

The task (section 3.3) asks for a simulator that makes command recognition and the bone search visible
and lets the team develop and test the software without hardware; a first version is due at MS3
(04.12.2026). On 2026-10-02 we chose a 2D top-down simulator in Python; a pygame prototype explored it.

## Decision

- The simulator is a web 3D application, `apps/dog-simulator`. It is the dog's world and body;
  it never contains the brain.
- The brain (`dog-core`, `dog-behavior`, `dog-perception`, `dog-recorder`) stays Python and runs in its
  own process: `apps/sim-host` on the laptop, `apps/robot` on the Raspberry Pi. Only the adapters differ.
- `packages/dog-protocol` is the single definition of the data exchanged between simulator and sim host.
  The brain must not import it.
- Robot-learning simulators (e.g. ManiSkill) were considered and rejected: native only, GPU-oriented,
  no browser, and they cover little of what the simulator needs.

## Consequences

- Two languages in one repo: Python in the uv workspace, the web app beside it with its own tooling and CI
  job once it exists.
- Simulator technology, the connection to the sim host and the data format are still to be done.
- The pygame prototype stays an untracked reference for behaviour ideas (Cockpit, Test bench, Replay).
