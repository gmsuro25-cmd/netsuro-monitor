from app.state_machine import transition_state


def test_three_failures_open_incident_and_two_successes_resolve_it():
    state = transition_state("UP", 0, 4, False)
    assert (state.status, state.failures, state.open_incident) == (
        "DEGRADED",
        1,
        False,
    )

    state = transition_state(state.status, state.failures, state.successes, False)
    assert (state.status, state.failures) == ("DEGRADED", 2)

    state = transition_state(state.status, state.failures, state.successes, False)
    assert (state.status, state.failures, state.open_incident) == (
        "DOWN",
        3,
        True,
    )

    state = transition_state(state.status, state.failures, state.successes, True)
    assert (state.status, state.successes, state.resolve_incident) == (
        "RECOVERING",
        1,
        False,
    )

    state = transition_state(state.status, state.failures, state.successes, True)
    assert (state.status, state.successes, state.resolve_incident) == (
        "UP",
        2,
        True,
    )


def test_success_resets_failure_counter():
    state = transition_state("DEGRADED", 2, 0, True)
    assert state.status == "UP"
    assert state.failures == 0
    assert state.successes == 1
