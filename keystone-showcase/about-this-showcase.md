# About this showcase

**This page is an illustrative interface demo. Every number in its embedded
manifest is a placeholder, including Agent 1, Agent 2 and Agent 3 panels.** Company
names are examples. These panels do not demonstrate real runs, issuer accuracy,
statistical significance or reproducibility. No browser action runs an agent.

The repository contains separate research, covenant-monitoring, event/news and
FP&A components. Their README and acceptance guides describe implemented scope
and verification limits. The demo is not an acceptance record for any agent.

## Real Agent 3 saved-run reports

Run either Agent 3 CLI to retain a terminal `bundle.json`, then use:

```bash
python -m agent3.bundles /path/to/bundle.json --output replay.json --html report.html
```

Open `report.html` separately. The exporter checks bundle integrity and rebuilds
deterministic stages offline before displaying analytical output. Held, failed,
refused and unavailable states stay restricted. Incomplete attempts provide a
status-only report; mismatched replays cannot be exported. Exports display the
attempt ID, input fingerprint, integrity hash and replay result.

Track A rebuilds historical statistics from retained normalized return windows;
Track B reconstructs relevance/clustering and aggregates retained scorer responses.
It does not refetch prices, articles or model weights. No export invents a daily
CAAR path or a forward probability. Hashes detect changed files, not authentic
issuer sources or maliciously recomputed hashes.

The static demo and real exported reports remain separate. There is no automatic
manifest collector, combined Track A/B report, live scheduler or notification flow.
