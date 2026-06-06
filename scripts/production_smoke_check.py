from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


DEFAULT_FRONTEND_URL = "https://www.zero2asset.com"
DEFAULT_FALLBACK_FRONTEND_URL = "https://smart-spending-analyzer.vercel.app"
DEFAULT_BACKEND_URL = "https://smart-spending-analyzer.onrender.com"
USER_AGENT = "curl/8.0"


class SmokeHTTPStatusError(RuntimeError):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


@dataclass(frozen=True)
class SmokeTarget:
    label: str
    url: str


def clean_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def build_url(base_url: str, path: str = "") -> str:
    base = clean_base_url(base_url)
    if not path:
        return base
    return f"{base}/{path.lstrip('/')}"


def request_url_with_curl(url: str, timeout: float) -> tuple[int, str]:
    curl_binary = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_binary:
        raise FileNotFoundError("curl is not available")

    result = subprocess.run(
        [
            curl_binary,
            "--location",
            "--silent",
            "--show-error",
            "--output",
            os.devnull,
            "--connect-timeout",
            str(int(timeout)),
            "--max-time",
            str(int(timeout)),
            "--write-out",
            "%{http_code}\\t%{content_type}\\t%{time_total}",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
        check=False,
    )
    if result.returncode != 0:
        raise urllib.error.URLError(result.stderr.strip() or f"curl exited {result.returncode}")

    status_text, content_type, _elapsed = (result.stdout.strip().split("\t") + ["", ""])[:3]
    status = int(status_text or "0")
    if status < 200 or status >= 400:
        raise SmokeHTTPStatusError(status)
    return status, content_type or "unknown"


def request_url_with_urllib(url: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read(1)
        status = response.getcode()
        content_type = response.headers.get("Content-Type", "unknown").split(";")[0]
        return status, content_type


def request_url(url: str, timeout: float) -> tuple[int, str]:
    try:
        return request_url_with_curl(url, timeout)
    except FileNotFoundError:
        return request_url_with_urllib(url, timeout)


def check_target(target: SmokeTarget, timeout: float, retries: int, retry_delay: float) -> bool:
    for attempt in range(1, retries + 2):
        start = time.perf_counter()
        try:
            status, content_type = request_url(target.url, timeout=timeout)
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            print(f"PASS {target.label}: {status} {content_type} in {elapsed_ms}ms")
            return True
        except SmokeHTTPStatusError as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            if attempt <= retries:
                print(
                    f"RETRY {target.label}: attempt {attempt} returned HTTP {exc.status_code} "
                    f"after {elapsed_ms}ms"
                )
                time.sleep(retry_delay)
                continue

            print(f"FAIL {target.label}: HTTP {exc.status_code} after {elapsed_ms}ms")
            return False
        except urllib.error.HTTPError as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            if attempt <= retries:
                print(
                    f"RETRY {target.label}: attempt {attempt} returned HTTP {exc.code} "
                    f"after {elapsed_ms}ms"
                )
                time.sleep(retry_delay)
                continue

            print(f"FAIL {target.label}: HTTP {exc.code} after {elapsed_ms}ms")
            return False
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            if attempt <= retries:
                print(
                    f"RETRY {target.label}: attempt {attempt} failed after {elapsed_ms}ms "
                    f"({type(exc).__name__})"
                )
                time.sleep(retry_delay)
                continue

            print(f"FAIL {target.label}: {type(exc).__name__} after {elapsed_ms}ms")
            return False

    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run no-secret production smoke checks for public app endpoints."
    )
    parser.add_argument(
        "--frontend-url",
        default=os.getenv("FRONTEND_URL", DEFAULT_FRONTEND_URL),
        help="Primary public frontend URL.",
    )
    parser.add_argument(
        "--fallback-frontend-url",
        default=os.getenv("FALLBACK_FRONTEND_URL", DEFAULT_FALLBACK_FRONTEND_URL),
        help="Fallback frontend URL to verify after the primary domain.",
    )
    parser.add_argument(
        "--backend-url",
        default=os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL),
        help="Public backend base URL.",
    )
    parser.add_argument("--timeout", type=float, default=60, help="Per-request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per target after the first attempt.")
    parser.add_argument("--retry-delay", type=float, default=10, help="Seconds to wait between retries.")
    parser.add_argument(
        "--skip-fallback",
        action="store_true",
        help="Skip the fallback frontend URL check.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    targets = [
        SmokeTarget("frontend primary", build_url(args.frontend_url)),
    ]
    if args.fallback_frontend_url and not args.skip_fallback:
        targets.append(SmokeTarget("frontend fallback", build_url(args.fallback_frontend_url)))

    backend_url = clean_base_url(args.backend_url)
    targets.extend(
        [
            SmokeTarget("backend live", build_url(backend_url, "/live")),
            SmokeTarget("backend ready", build_url(backend_url, "/ready")),
            SmokeTarget("backend health", build_url(backend_url, "/health")),
        ]
    )

    results = [
        check_target(
            target,
            timeout=args.timeout,
            retries=max(args.retries, 0),
            retry_delay=max(args.retry_delay, 0),
        )
        for target in targets
    ]

    if all(results):
        print("Production smoke check passed.")
        return 0

    print("Production smoke check failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
