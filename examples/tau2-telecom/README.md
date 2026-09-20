# τ² telecom validation / 电信域验证

This example validates the framework against the pinned `telecom` domain from
the independent [tau2-bench](https://github.com/sierra-research/tau2-bench)
release `v1.0.1`.

## Reproduce the published result

```bash
mkdir -p work/tau2-telecom
python -m pip install -r examples/optional-requirements.txt
tau2 download-results \
  --output work/tau2-telecom/results.json \
  "$(python -c 'import json; print(json.load(open("examples/tau2-telecom/source.json"))["download_url"])')"
echo "04fad1a6fb3ff8804be31c54cf5a993b64868e37683c226e014e7adbf60841d9  work/tau2-telecom/results.json" \
  | shasum -a 256 -c -
python examples/tau2_telecom_validation.py \
  --results work/tau2-telecom/results.json \
  --out work/tau2-telecom/report.json \
  --traces-dir work/tau2-telecom/sample-traces \
  --min-eligible 300 \
  --min-failures 200 \
  --min-failure-recall 0.99 \
  --max-false-alarm-rate 0.05 \
  --max-missed-failure-rate 0.0
```

The published file contains 456 trajectories. The adapter evaluates 364
scenarios whose Contract contains at least one assistant-owned write action;
92 scenarios contain only simulator/user-owned actions and are reported as
excluded rather than silently treated as Agent evidence. The published result
observed 147 true passes, 217 true blocks, 0 false alarms and 0 missed
failures for that scoped contract.

Telecom is a two-actor trace: assistant calls are the Agent behavior path,
while user-owned tool results are environment evidence. The adapter keeps
those boundaries explicit and uses environment assertions for service status,
mobile data, speed, MMS, refueling and overdue-bill evidence.

## Prospective model result

The pinned `o4-mini` file uses the same task domain but a different model
result. Reproduce it with:

```bash
python examples/tau2_telecom_validation.py \
  --results work/tau2-telecom-o4/results.json \
  --source-manifest examples/tau2-telecom/prospective-o4-mini-source.json \
  --out work/tau2-telecom-o4/report.json \
  --min-eligible 300 \
  --min-failures 200 \
  --min-failure-recall 0.98 \
  --max-false-alarm-rate 0.10 \
  --max-missed-failure-rate 0.02
```

The prospective observation was 136 true passes, 216 true blocks, 9 false
alarms and 3 missed failures (98.63% failure recall and 6.21% false-alarm
rate). The relaxed observation thresholds are recorded explicitly; they are
not a general quality guarantee and do not convert a calibration file into
unseen-task generalization evidence.

## Task-disjoint holdout proxy

v4.20 adds a reproducible task-level split. It hashes each task ID with
SHA-256, assigns buckets modulo 100, and reserves buckets `0..19` for the
holdout. The split definition contains only task-set counts and digests; reward
labels are not consulted when selecting the partition.

```bash
python examples/tau2_telecom_holdout_validation.py \
  --results work/tau2-telecom/results.json \
  --source-manifest examples/tau2-telecom/source.json \
  --split-definition examples/tau2-telecom/task-split.json \
  --partition holdout \
  --out work/tau2-telecom/holdout-report.json \
  --min-eligible 80 \
  --min-failures 30 \
  --min-failure-recall 0.99 \
  --max-false-alarm-rate 0.05 \
  --max-missed-failure-rate 0.0
```

The published holdout contains 28 tasks, 100 eligible simulations, 47 true
passes, 53 true blocks, 0 false alarms and 0 missed failures. The prospective
o4-mini holdout contains the same 28 tasks and yields 50 true passes, 46 true
blocks, 4 false alarms and 0 missed failures (100% failure recall and 7.41%
false-alarm rate under the explicit 10% observation threshold).

This is a task-disjoint holdout proxy over the same published task family, not
an independent upstream task source or universal unseen-domain generalization
claim. The split digest and limitations are recorded in
[`docs/v4.20-acceptance.md`](../../docs/v4.20-acceptance.md).

来源文件的 URL、tag、commit 和 SHA-256 记录在两个 manifest 中。电信域还
验证了一个重要边界：模拟器的 user-owned tool call 不应被误当成 Agent 的
assistant path；它们只作为环境证据参与断言。
