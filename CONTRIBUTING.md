# Contributing

## Branches

`main` is protected: work on a branch and merge through a pull request.

Branch names: `<type>/<short-description>`, e.g. `feat/sim-map-loader`, `fix/clock-drift`.
Use the same types as for commits.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <summary>

<optional body: why, not what>
```

- **type**: `feat` new feature, `fix` bug fix, `docs`, `refactor`, `test`,
  `chore` maintenance, `ci`, `build` dependencies and packaging, `perf`, `experimental`
- **scope** (optional): `core`, `behavior`, `perception`, `recorder`, `protocol`, `sim`, `robot`, `models`, `ci`, `repo`
- **summary**: imperative, lowercase, no full stop, header max 72 characters
- `!` after type/scope marks a breaking change, e.g. `feat(core)!: rename Clock.now`

Examples:

```
feat(sim): add 2D map loader
fix(perception): ignore empty audio frames
chore: bump ruff
```

### Check locally

Enable the hook once per clone:

```sh
git config core.hooksPath .githooks
```

CI checks every commit of a pull request with the same script.

## Documentation

Docs live in `docs/` and change in the same commit as the code:

- Python: Google-style docstrings (the API reference is generated from them)
- JavaScript: `// @ts-check`, a `@file` comment and JSDoc on every function
- a decision gets an ADR in `docs/adr/`, an iteration a dev log entry in `docs/simulator/devlog.md`

Preview with `uv run --group docs mkdocs serve`.

## Pull requests

- Keep them small and focused on one task
- CI must be green before merging
- At least one review from a team member
