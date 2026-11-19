# PREN Dog Software

Software for our autonomous dog robot (HSLU PREN HS26/FS27): voice and gesture recognition,
bone search, and a simulator to develop and test the robot's brain without hardware.

| I want to… | Read |
| --- | --- |
| run the simulator | [Simulator overview](simulator/index.md) |
| understand or change the robot model | [Robot model](simulator/robot-model.md) |
| know what the Pico must do over UART | [Pico emulator](simulator/pico-emulator.md) |
| connect the dog core to the simulator | [Core integration](simulator/core-integration.md) |
| work on the 3D view | [Browser viewer](simulator/viewer.md) |
| see what changed and why | [Dev log](simulator/devlog.md) |
| look up a class or function | [Reference](reference/sim-host.md) |

## Keeping these docs current

The docs live next to the code and change in the same commit:

- **Python**: Google-style docstrings. The [reference pages](reference/sim-host.md) are generated from them.
- **JavaScript**: JSDoc comments with `// @ts-check`; `npm run typecheck` checks the types they declare.
- **Decisions**: one ADR per decision in `docs/adr/`.
- **Iterations**: a short entry in the [dev log](simulator/devlog.md) for each one.

Preview locally with live reload:

```bash
uv run --group docs mkdocs serve
```
