from wattforest.events import EventLog
from wattforest.rng import DeterministicRNG


def test_rng_is_repeatable_for_same_context():
    rng = DeterministicRNG(42)
    assert rng.uniform("growth", 10, 1, 2) == rng.uniform("growth", 10, 1, 2)


def test_event_log_defaults_seed():
    assert EventLog().global_seed == 42
