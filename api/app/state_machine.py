from dataclasses import dataclass


@dataclass(frozen=True)
class StateTransition:
    status: str
    failures: int
    successes: int
    open_incident: bool = False
    resolve_incident: bool = False


def transition_state(
    current_status: str,
    consecutive_failures: int,
    consecutive_successes: int,
    succeeded: bool,
) -> StateTransition:
    if succeeded:
        failures = 0
        successes = consecutive_successes + 1
        if current_status == "DOWN":
            return StateTransition("RECOVERING", failures, successes)
        if current_status == "RECOVERING":
            if successes >= 2:
                return StateTransition(
                    "UP", failures, successes, resolve_incident=True
                )
            return StateTransition("RECOVERING", failures, successes)
        return StateTransition("UP", failures, successes)

    failures = consecutive_failures + 1
    successes = 0
    if current_status in {"PENDING", "UP"}:
        return StateTransition("DEGRADED", failures, successes)
    if current_status == "DEGRADED" and failures >= 3:
        return StateTransition("DOWN", failures, successes, open_incident=True)
    if current_status == "RECOVERING":
        return StateTransition("DOWN", failures, successes)
    return StateTransition(current_status, failures, successes)
