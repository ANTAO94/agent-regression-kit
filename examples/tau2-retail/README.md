# τ²-bench retail validation

This example evaluates Agent Regression Kit against a pinned result file from
the independent `sierra-research/tau2-bench` project.

```bash
mkdir -p work/tau2
curl --fail --location --retry 3 \
  --output work/tau2/results.json \
  "$(python -c 'import json; print(json.load(open("examples/tau2-retail/source.json"))["download_url"])')"

echo "6d6badb43b716adca31591b0b40e15fd493b49adddaa8e2c47035bb557549257  work/tau2/results.json" \
  | shasum -a 256 -c -

python examples/tau2_retail_validation.py \
  --results work/tau2/results.json \
  --out work/tau2/report.json \
  --traces-dir work/tau2/sample-traces
```

The expected v4.12 matrix is 267 true passes, 153 true blocks, zero false alarms
and zero missed failures across 420 eligible write scenarios. The v4.12
contract uses explicit outcome equivalence for reviewed alternatives while
keeping object arguments and unexpected successful writes fail-closed. See the
[bilingual validation guide](../../docs/tau2-independent-validation.md) for
terminology, provenance, interpretation and limitations.
