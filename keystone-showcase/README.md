# Keystone showcase — illustrative interface

Open `index.html` locally. All embedded numbers are placeholders. A visible banner,
footer and Agent 3 panel disclose this. No visitor triggers a live run.

The Agent 3 chart is explicitly an illustrative drawing: the engine returns
three-day event CAR statistics, not the eleven-day curve shown in the demo.
The panel publishes no forward scenario or probability.

## Export an actual Agent 3 result

From the repository root, with the project environment activated:

```bash
python -m agent3.bundles /path/to/bundle.json --output replay.json --html report.html
```

Open the generated `report.html` separately. It uses the shared publication-aware
renderers and only replay-verified fields. A mismatch blocks export; an incomplete
attempt gets a status-only report. HTML text is escaped, output files are
write-once, and the original evidence bundle is unchanged.

These exports do not populate the demo manifest. No generic collector or hosted
live execution is implemented. See `../docs/agent3-batch4.md` for bundle, replay,
index recovery and limitations.
