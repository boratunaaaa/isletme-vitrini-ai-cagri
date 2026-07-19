from __future__ import annotations

import sys

import pytest

from agent import main as main_module


def test_check_config_flag_still_works(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VOICE_AGENT_ENV", "development")
    monkeypatch.setattr(sys, "argv", ["agent.main", "--check-config"])
    main_module.get_settings.cache_clear()

    exit_code = main_module.main()

    assert exit_code == 0
    assert "configuration valid" in capsys.readouterr().out


def test_unrecognized_subcommand_no_longer_crashes_argparse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRODUCTION_INFRA_REPORT.md: `python -m agent.main dev`/`start` (LiveKit
    Agents'ın kendi Typer alt komutları) daha önce bu argparse katmanında
    "unrecognized arguments" ile SystemExit(2) veriyordu. Artık `dev`/`start`
    argparse'ı atlayıp sys.argv üzerinden `agents.cli.run_app()`'a ulaşmalı —
    gerçek bir LiveKit worker'ı başlatmadan bunu doğrulamak için `run_worker`
    monkeypatch'lenir."""
    monkeypatch.setenv("VOICE_AGENT_ENV", "development")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-token")
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret")
    monkeypatch.setenv("LIVEKIT_SIP_OUTBOUND_TRUNK_ID", "test-trunk")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(sys, "argv", ["agent.main", "dev"])
    main_module.get_settings.cache_clear()

    captured_argv: list[str] = []

    def fake_run_worker(settings: object) -> None:
        captured_argv.extend(sys.argv)

    monkeypatch.setattr("agent.job_handler.run_worker", fake_run_worker)

    exit_code = main_module.main()

    assert exit_code == 0
    # argparse'ın tükettiği program adı korunmalı, "dev" ise run_worker'a
    # (dolayısıyla LiveKit'in kendi Typer ayrıştırıcısına) ulaşmalı.
    assert captured_argv == ["agent.main", "dev"]


def test_production_env_without_credentials_fails_fast_not_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gerçek credential yokken production modunda sessizce güvensiz
    varsayılana düşmemeli — açık bir ConfigurationError ile başarısız olmalı
    (PRODUCTION_INFRA_REPORT.md: restart-loop yerine öngörülebilir hata)."""
    monkeypatch.setenv("VOICE_AGENT_ENV", "production")
    for key in (
        "INTERNAL_SERVICE_TOKEN",
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "LIVEKIT_SIP_OUTBOUND_TRUNK_ID",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(sys, "argv", ["agent.main", "start"])
    main_module.get_settings.cache_clear()

    with pytest.raises(main_module.ConfigurationError):
        main_module.main()
