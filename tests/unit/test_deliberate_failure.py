"""Deliberate test failure to verify red CI check and blocked merge button in PR gating."""


def test_deliberate_failure_for_ci_gate():
    assert False, "Deliberate test failure for CI gate verification (Issue #14)"
