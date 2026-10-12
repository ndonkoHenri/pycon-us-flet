"""The hypothesis `ci` profile tests/conftest.py registers (docs/testing-and-quality.md §3.1)."""

from hypothesis import HealthCheck, settings


def test_ci_profile_extends_hypothesis_builtin_with_more_examples() -> None:
    ci = settings.get_profile("ci")
    assert ci.max_examples == 200
    assert ci.derandomize is True
    assert ci.deadline is None
    assert ci.database is None
    assert ci.print_blob is True
    assert HealthCheck.too_slow in ci.suppress_health_check
