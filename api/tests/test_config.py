import pytest

from app.config import read_secret, require_production_value


def test_environment_secret_is_used_without_file(monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "local-password")
    assert read_secret("POSTGRES_PASSWORD") == "local-password"


def test_secret_file_takes_precedence(monkeypatch, tmp_path):
    secret = tmp_path / "database-password"
    secret.write_text("production-password\n")
    monkeypatch.setenv("POSTGRES_PASSWORD", "visible-password")
    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", str(secret))
    assert read_secret("POSTGRES_PASSWORD") == "production-password"


def test_insecure_placeholder_is_rejected_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        require_production_value("PASSWORD", "CHANGE_ME", min_length=20)


def test_long_secret_is_accepted_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    require_production_value("PASSWORD", "a-long-random-production-secret", min_length=20)
