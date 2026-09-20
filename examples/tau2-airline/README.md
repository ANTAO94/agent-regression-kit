# τ²-bench airline validation

This example validates Agent Regression Kit against a second τ²-bench task
domain. It is deliberately separate from the retail evaluator: airline
contracts use airline write tools and explicitly ignore `payment_id` only when
the task does not declare that field. A payment ID declared by the task remains
an assertion.

```bash
mkdir -p work/tau2-airline
curl --fail --location --retry 3 \
  --output work/tau2-airline/results.json \
  "$(python -c 'import json; print(json.load(open("examples/tau2-airline/source.json"))["download_url"])')"

echo "41788956547a100fb8e34baf159f36dd1f07f0765798a5fdaf917576c5dba9d0  work/tau2-airline/results.json" \
  | shasum -a 256 -c -

python examples/tau2_airline_validation.py \
  --results work/tau2-airline/results.json \
  --out work/tau2-airline/report.json \
  --traces-dir work/tau2-airline/sample-traces
```

The pinned published airline result contains 200 trajectories, 120 eligible
write scenarios and 69 oracle failures. The v4.18 contract decision reports
100% failure recall and a 3.92% false-alarm rate on this domain. This is
evidence that the contract engine transfers beyond retail; it is not a claim
that every airline workflow or every model is covered.

For the prospective o4-mini result, use its matching manifest. The validator
rejects a result file whose SHA-256 does not match the manifest:

```bash
python examples/tau2_airline_validation.py \
  --results work/tau2-airline-o4/results.json \
  --source-manifest examples/tau2-airline/prospective-o4-mini-source.json \
  --out work/tau2-airline-o4/report.json \
  --min-eligible 100 \
  --min-failures 50 \
  --min-failure-recall 0.99 \
  --max-false-alarm-rate 0.12 \
  --max-missed-failure-rate 0.0
```

The prospective model result is reported separately because its observed
false-alarm rate is 10.42%; the relaxed 12% threshold is an explicit
model/domain observation, not the project's general maturity target.
