# Contributing

Use Python 3.9 or newer and keep the default suite offline:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Changes to AgentTrace require an explicit schema-version decision, updates to `schema/`, validation tests, and a compatibility note. MCP changes must state the protocol revision and must not turn the project-owned fixture into an implied conformance implementation.

Please include tests for success and failure paths. Do not add automatic retries around tools with unknown side effects.
