# Browser viewer

`apps/dog-simulator` draws what the sim host simulates and sends the user's commands back.
It simulates nothing itself, so it can be restyled freely without changing behaviour.

## Files

| File | Job |
| --- | --- |
| `index.html` | page layout: 3D view, camera inset, side panel |
| `src/main.js` | starts everything, handles placing objects with a floor click |
| `src/connection.js` | WebSocket to the sim host, reconnects every second |
| `src/scene.js` | three.js scene: one mesh per MuJoCo geom, trail, springs, dog's camera view |
| `src/panel.js` | buttons, keyboard driving, joint/sensor readouts, detection boxes |
| `src/protocol.js` | JSDoc types of the messages; mirrors `dog_protocol` |
| `src/style.css` | dark theme |

## How a frame is drawn

1. On connect the sim host sends a **scene** message: every geom's shape, size and colour,
   plus the triangles of every CAD mesh (once, shared by all geoms that use it).
   `scene.js` builds one three.js mesh each (boxes get rounded edges, CAD parts flat shading).
   Geoms with alpha 0, like the wheels' contact shapes, are not drawn.
2. About 30 times a second a **frame** message moves every mesh to MuJoCo's pose. It also places
   the dog's camera and carries the joint, sensor and spring readings.
3. The page renders the main view, then the scene again from the dog's camera into the inset.
   The detector's boxes are drawn on top, so you see what the core "sees".

The world is z-up like MuJoCo, so poses are copied without converting (`DEFAULT_UP` is set to z).

## Controls

| Control | Sends |
| --- | --- |
| Speak buttons | `voice`, a word for the core's audio recognition (needs `--core`) |
| Gesture buttons | `gesture`, held until changed (needs `--core`) |
| Pico buttons, W A S D | `pico`, a UART command straight to the emulated Pico |
| Not-Aus | `emergency_stop` |
| place bone / person, then click the floor | `place` |
| reset | `reset` (a running core loses its home tracking: restart it) |

## Code conventions

Every file starts with `// @ts-check` and a `@file` comment. Every function and class has a JSDoc
block with its parameter types. `npm run typecheck` runs TypeScript over the JSDoc types, so a wrong
field name in a message fails the check.

```bash
npm --prefix apps/dog-simulator run typecheck
```
