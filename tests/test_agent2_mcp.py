"""Agent 2 — the shared checks are byte-identical whether called locally or over
the MCP server. Also guards that the §5 drift fix is consistent across transports."""

import os


def test_local_and_mcp_drift_identical():
    from tools import statistical_checks as local
    try:
        from mcp_server.client import drift_check as mcp_drift
    except Exception:
        import pytest
        pytest.skip("mcp SDK not installed")

    times = list(range(1, 9))
    # a perfect linear trend — exercises the §5 fix over both transports
    values = [2.0 + 0.1 * i for i in range(8)]
    l = local.drift_check(times, values, threshold=3.5, direction="above")
    m = mcp_drift(times, values, threshold=3.5, direction="above")
    assert l == m
    assert l["drifting"] is True


def test_local_and_mcp_anomaly_identical():
    from tools import statistical_checks as local
    try:
        from mcp_server.client import anomaly_significance_check as mcp_anom
    except Exception:
        import pytest
        pytest.skip("mcp SDK not installed")

    series = [3.5, 3.5, 3.4, 3.6, 3.5, 3.5, 2.0]
    assert local.anomaly_significance_check(series) == mcp_anom(series)
