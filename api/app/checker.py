import time
from urllib.parse import urljoin

import httpx

from app.ssrf import UnsafeMonitorTargetError, validate_monitor_url


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5


def check_url(
    url: str,
    timeout_seconds: int,
    expected_status_code: int,
    transport=None,
):
    started_at = time.perf_counter()

    try:
        current_url = str(url)
        with httpx.Client(follow_redirects=False, transport=transport) as client:
            for redirect_count in range(MAX_REDIRECTS + 1):
                validate_monitor_url(current_url)
                remaining = timeout_seconds - (time.perf_counter() - started_at)
                if remaining <= 0:
                    raise httpx.TimeoutException("monitor timeout exceeded")
                with client.stream("GET", current_url, timeout=remaining) as response:
                    if response.status_code not in REDIRECT_STATUSES:
                        status_code = response.status_code
                        break
                    location = response.headers.get("location")
                    if not location:
                        status_code = response.status_code
                        break
                    if redirect_count == MAX_REDIRECTS:
                        raise UnsafeMonitorTargetError("monitor target exceeded 5 redirects")
                    current_url = urljoin(current_url, location)

        response_time_ms = round((time.perf_counter() - started_at) * 1000)
        return {
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "succeeded": status_code == expected_status_code,
            "error_message": None,
        }
    except (httpx.RequestError, UnsafeMonitorTargetError) as error:
        response_time_ms = round((time.perf_counter() - started_at) * 1000)
        return {
            "status_code": None,
            "response_time_ms": response_time_ms,
            "succeeded": False,
            "error_message": str(error)[:1000],
        }
