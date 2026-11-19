# 2. React and Three.js for the web simulator

Date: 2026-11-06 · Status: accepted, partly replaced by [ADR 3](0003-mujoco-simulator.md) (physics, React, TypeScript)

## Context

ADR 1 made the simulator a web 3D app and left its technology open. It needs a simple 3D scene of the
competition field, a way to place the dog, bone and referee (Live mode), a dog's-eye camera view, and a UI
that will be designed later from the simulator concept.

## Decision

- React with Three.js through React Three Fiber, in TypeScript, built with Vite.
- drei helpers for placing objects, camera controls and labels in the scene.
- No physics engine; movement is a simple motion model.

Alternatives considered: plain Three.js (more wiring for the UI and placing), Angular with Three.js
(known from work, but a smaller 3D ecosystem), Babylon.js (heavier), game engines with a web export
such as Unity or Godot (large, another language, awkward to connect to Python).

## Consequences

- The web app gets its own tooling (npm) and a CI job once it exists.
- Connection, data format and the remaining choices stay proposals in the simulator concept until implemented.
