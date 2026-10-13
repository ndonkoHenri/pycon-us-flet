"""The hypothesis `ci` and `dev` profiles tests/conftest.py registers (testing-and-quality.md §3.1)."""

from hypothesis import HealthCheck, settings


def test_ci_profile_extends_hypothesis_builtin_with_more_examples() -> None:
    ci = settings.get_profile("ci")
    assert ci.max_examples == 200
    assert ci.derandomize is True
    assert ci.deadline is None
    assert ci.database is None
    assert ci.print_blob is True
    assert HealthCheck.too_slow in ci.suppress_health_check


def test_local_runs_use_the_dev_profile_without_a_deadline() -> None:
    """A busy Mac overran the default 200 ms deadline in a correctness property."""
    dev = settings.get_profile("dev")
    assert dev.deadline is None
    assert dev.max_examples == settings.get_profile("default").max_examples
