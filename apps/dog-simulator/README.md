# dog-simulator

Browser viewer for the dog simulator. It draws what `apps/sim-host` simulates with MuJoCo and sends
commands back; it never contains the brain or the physics.

Technology: Vite + plain three.js, JavaScript with JSDoc types checked by TypeScript
([ADR 3](../../docs/adr/0003-mujoco-simulator.md)).

```sh
npm install
npm run dev        # http://localhost:5173, connects to ws://localhost:8780 (override with ?ws=...)
npm run typecheck  # check the JSDoc types
npm run build      # static files in dist/
```

Docs: [docs/simulator/viewer.md](../../docs/simulator/viewer.md).
