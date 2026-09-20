# Contributing

Use Python 3.9 or newer and keep the default suite offline:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Changes to AgentTrace require an explicit schema-version decision, updates to `schema/`, validation tests, and a compatibility note. MCP changes must state the protocol revision and must not turn the project-owned fixture into an implied conformance implementation.

Please include tests for success and failure paths. Do not add automatic retries around tools with unknown side effects.

Before opening a pull request:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
git diff --check
```

Explain the observable regression being addressed, the Trace or Contract
evidence, compatibility impact, and any sensitive-data boundary. Keep the core
dependency-free unless a dependency is essential; framework integrations
belong in optional extras.

Do not report vulnerabilities or include credentials/customer Trace data in a
public issue. Follow [SECURITY.md](SECURITY.md). Participation is governed by
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
