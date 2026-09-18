# History fixtures

These small JSON files demonstrate the v3.1 history input contract. Name
files with a stable prefix such as `001-`, `002-`, and `003-` so the CLI can
order releases deterministically:

```bash
agent-regression history \
  --report-dir examples/history \
  --format markdown \
  --out outputs/history.md
```

The command also accepts full stability, compare, batch, and coverage reports
produced by earlier commands. Unrecognized JSON files are listed under
`skipped` instead of silently becoming trend points.
