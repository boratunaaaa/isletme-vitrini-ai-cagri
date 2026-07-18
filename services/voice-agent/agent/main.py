from __future__ import annotations

import argparse
import sys

from agent.config import get_settings
from agent.errors import ConfigurationError
from agent.logging import configure_logging


def _check_config() -> int:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    missing = settings.missing_runtime_settings()
    if settings.VOICE_AGENT_ENV == "production" and missing:
        raise ConfigurationError("missing production runtime settings: " + ", ".join(missing))
    if missing:
        print(
            "configuration valid for dry check; runtime credentials missing: "
            + ", ".join(missing)
        )
    else:
        print("configuration valid; runtime credentials present")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    if args.check_config:
        return _check_config()
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    settings.require_runtime_ready()
    from agent.job_handler import run_worker

    run_worker(settings)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
