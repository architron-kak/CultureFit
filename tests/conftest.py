"""Fresh process-local budgets and a controllable clock for every test."""
import pytest

from culturefit import llm, main
from culturefit.limits import DailyBudget, RequestLimiter


class FakeClock:
    def __init__(self):
        self.now = 12 * 3600.0  # Noon UTC on an arbitrary day.

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch, clock):
    monkeypatch.setattr(main, "request_limiter", RequestLimiter(clock=clock))
    monkeypatch.setattr(llm, "_llm_budget", DailyBudget(clock=clock))
    monkeypatch.setattr(llm, "_cache", {})
