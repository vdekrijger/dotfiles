# Persona Validation Fixture

A synthetic diff with known issues planted across each persona's priority
classes. Run each persona against this diff manually to smoke-test their
output before end-to-end orchestrator testing.

## How to use

1. Save the diff below to a temp file: `/tmp/fixture.diff`
2. Invoke the persona's custom agent (subagent_type: `vasco-reviewer`, `sre-reviewer`, `xp-reviewer`, or `intent-reviewer`, defined at `~/.claude/agents/<name>.md` — the agent file body is its system prompt, no pasting needed) with this prompt shape:

```
## Code changes to review

### Changed files
services/alerts/checks.py
services/alerts/tests/test_checks.py
frontend/src/scenes/alerts/AlertView.tsx

### Commit messages
feat(alerts): add threshold validation

### Full diff
<paste /tmp/fixture.diff>

## Instructions
Follow your output format. Return STRUCTURED_FINDINGS + OVERALL_SUMMARY.
```

3. Check the output against the "Expected findings" table below.

## The fixture diff

```diff
diff --git a/services/alerts/checks.py b/services/alerts/checks.py
index 1234567..abcdefg 100644
--- a/services/alerts/checks.py
+++ b/services/alerts/checks.py
@@ -10,6 +10,45 @@ from alerts.models import Alert
 import requests

+THRESHOLD_TYPE_ABSOLUTE = "absolute_value"
+THRESHOLD_TYPE_RELATIVE = "relative_increase"
+
+def validate_threshold(config):
+    if config["type"] == "absolute_value":
+        if config["value"] < 0:
+            raise ValueError("Threshold must be non-negative")
+    elif config["type"] == "relative_increase":
+        if config["value"] < 0 or config["value"] > 100:
+            raise ValueError("Relative increase must be 0-100")
+    return config
+
+def validate_query(config):
+    if config["kind"] == "TrendsQuery":
+        return config
+    raise ValueError("Unsupported query kind")
+
+def fetch_alert_data(alert_id):
+    response = requests.get(f"https://api.example.com/alerts/{alert_id}")
+    return response.json()
+
+def process_alerts(alerts):
+    for alert in alerts:
+        try:
+            data = fetch_alert_data(alert.id)
+            alert.last_result = data["result"]
+            alert.save()
+        except Exception:
+            pass
+
diff --git a/services/alerts/tests/test_checks.py b/services/alerts/tests/test_checks.py
index 0000000..1111111 100644
--- a/services/alerts/tests/test_checks.py
+++ b/services/alerts/tests/test_checks.py
@@ -0,0 +1,30 @@
+def test_validate_threshold_absolute():
+    config = {"type": "absolute_value", "value": 10}
+    result = validate_threshold(config)
+    assert result == config
+
+def test_validate_threshold_relative():
+    config = {"type": "relative_increase", "value": 50}
+    result = validate_threshold(config)
+    assert result == config
+
+def test_validate_threshold_relative_high():
+    config = {"type": "relative_increase", "value": 75}
+    result = validate_threshold(config)
+    assert result == config
+
+def test_fetch_alert_data_returns_dict():
+    # Using a mock so heavy
+    import unittest.mock
+    with unittest.mock.patch("services.alerts.checks.requests") as m:
+        m.get.return_value.json.return_value = {"result": "ok"}
+        result = fetch_alert_data(1)
+        assert isinstance(result, dict)
+
diff --git a/frontend/src/scenes/alerts/AlertView.tsx b/frontend/src/scenes/alerts/AlertView.tsx
index 2222222..3333333 100644
--- a/frontend/src/scenes/alerts/AlertView.tsx
+++ b/frontend/src/scenes/alerts/AlertView.tsx
@@ -0,0 +1,25 @@
+export function AlertView({ alert }) {
+    const isNotReady = !alert.ready
+    return (
+        <div className="alert-view">
+            <h2>{alert.name}</h2>
+            {isNotReady ? <div>Loading...</div> : <div>{alert.value}</div>}
+            <button onClick={() => fetch(`/api/alerts/${alert.id}`)}>
+                Refresh
+            </button>
+            <div data-attr="alert-status">
+                Status: {alert.status === "ACTIVE" ? "active" : "inactive"}
+            </div>
+        </div>
+    )
+}
```

## Expected findings (minimum)

### vasco-reviewer

| Priority | Finding |
|----|---|
| 1 (edge cases) | `validate_threshold` has no test for `None` / missing `type` / missing `value` / negative `absolute` |
| 1 (edge cases) | `validate_query` has no tests at all |
| 2 (parameterization) | `test_validate_threshold_absolute` / `_relative` / `_relative_high` are the same logic — should be parameterized |
| 3 (meaningful assertions) | `test_fetch_alert_data_returns_dict` only asserts `isinstance(result, dict)` — the implementation is gutted and the test still passes |
| 5 (constants over magic strings) | `config["type"] == "absolute_value"` inside `validate_threshold` should use the `THRESHOLD_TYPE_*` constants defined above |
| 5 (constants over magic strings) | `alert.status === "ACTIVE"` in TSX — likely matches an enum |
| 5 (constants) | `config["kind"] == "TrendsQuery"` — should use `NodeKind.TRENDS_QUERY` if PostHog context detected |
| 9 (naming) | `isNotReady` is a boolean inversion — flip to `isReady` and invert usage |
| 8 (type annotations) | None of the Python functions have type annotations |

### sre-reviewer

| Priority | Finding |
|----|---|
| 1 (observability) | `except Exception: pass` in `process_alerts` — silent failure, no logging |
| 3 (integration criticality) | `requests.get` in `fetch_alert_data` has no timeout — default is None (hang forever) |
| 3 (circuit breaker) | No circuit breaker on the external `api.example.com` call |
| 3 (retry) | No retry policy; one transient failure → missed alert update |
| 11 (consumer resilience) | `process_alerts` loops over alerts swallowing exceptions — one bad alert doesn't block the others, but there's also no DLQ / retry / failure accounting |
| 1 (observability) | `fetch` in AlertView has no error handler — user sees nothing on failure |

### xp-reviewer

| Rule | Finding |
|----|---|
| 3 (no duplication) | The three threshold tests have the same body with varying inputs — parameterize |
| 2 (expresses intent) | `isNotReady` is a double negative, harder to read than `isReady` |
| 4 (no waste) | `# Using a mock so heavy` comment in test explains a future intent; either commit to the design or remove |

## Validation pass criteria

A persona is considered passing if it flags **at least 70% of its expected
findings** on this fixture. Missing items point at prompt weaknesses to tune.
