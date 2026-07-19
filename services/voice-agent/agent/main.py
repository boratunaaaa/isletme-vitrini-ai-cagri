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
            "configuration valid for dry check; runtime credentials missing: " + ", ".join(missing)
        )
    else:
        print("configuration valid; runtime credentials present")
    return 0


def main() -> int:
    # NOT (PRODUCTION_INFRA_REPORT.md): `parse_args()` daha önce `dev`/`start`
    # gibi LiveKit CLI (Typer tabanlı `agents.cli.run_app`) alt komutlarını
    # "unrecognized arguments" hatasıyla reddediyordu — `python -m agent.main
    # dev` (Makefile) ve production'da gereken `python -m agent.main start`
    # ASLA çalışmıyordu (empirik doğrulandı: argparse SystemExit(2)). Bu
    # yalnızca CLI argüman ayrıştırma düzeltmesidir; konuşma akışı/iş mantığı
    # değişmedi. `parse_known_args()` yalnız `--check-config`'i tüketir,
    # kalan argümanlar (`dev`/`start`/vb.) `sys.argv`'e geri konup
    # `agents.cli.run_app()`'ın kendi Typer ayrıştırıcısına bırakılır.
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-config", action="store_true")
    args, remaining = parser.parse_known_args()
    if args.check_config:
        return _check_config()
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    settings.require_runtime_ready()
    from agent.job_handler import run_worker

    sys.argv = [sys.argv[0], *remaining]
    run_worker(settings)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
