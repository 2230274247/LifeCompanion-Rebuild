from types import SimpleNamespace

from app.provisioning import ReminderProvisioning
from app.provisioning import protect, unprotect


def test_ntfy_password_stdin_uses_lf_bytes_and_recovers_existing_user(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((list(command), kwargs))
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0,
                               stderr=b"user already exists" if len(calls) == 1 else b"")

    monkeypatch.setattr("app.provisioning.subprocess.run", run)
    provisioning = ReminderProvisioning.__new__(ReminderProvisioning)
    provisioning.settings = SimpleNamespace(
        ntfy_container="synthetic-ntfy",
        ntfy_admin_user="",
        ntfy_admin_password="",
    )
    provisioning._ntfy("synthetic-user", password="synthetic-password")
    assert len(calls) == 2
    for command, options in calls:
        assert options["input"] == b"synthetic-password\n"
        assert b"\r" not in options["input"]
        assert not options.get("text")
        assert "synthetic-password" not in " ".join(command)
    assert "user change-pass" in calls[1][0][6]


def test_ntfy_http_admin_api_uses_configured_credentials(monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr("app.provisioning.httpx.request", request)
    provisioning = ReminderProvisioning.__new__(ReminderProvisioning)
    provisioning.settings = SimpleNamespace(
        ntfy_container="unused",
        ntfy_base_url="http://ntfy:80",
        ntfy_admin_user="lc-admin",
        ntfy_admin_password="admin-secret",
    )

    provisioning._ntfy("lc_user", password="pw")
    provisioning._ntfy("access", "lc_user", "lc_topic", "rw")

    assert calls[0][0] == "PUT"
    assert calls[0][1] == "http://ntfy:80/v1/users"
    assert calls[0][2]["json"] == {"username": "lc_user", "password": "pw"}
    assert calls[0][2]["auth"]._auth_header == "Basic bGMtYWRtaW46YWRtaW4tc2VjcmV0"
    assert calls[1][0] == "PUT"
    assert calls[1][1] == "http://ntfy:80/v1/users/access"
    assert calls[1][2]["json"] == {
        "username": "lc_user",
        "topic": "lc_topic",
        "permission": "rw",
    }


def test_protect_unprotect_fernet_roundtrip(monkeypatch):
    monkeypatch.setattr("app.provisioning.os.name", "posix")
    monkeypatch.setenv("LIFE_CREDENTIAL_MASTER_KEY", "deploy-master-key")
    value = {"api_token": "secret-token", "project_id": 42}
    encrypted = protect(value)
    assert encrypted.startswith("f:")
    assert "secret-token" not in encrypted
    assert unprotect(encrypted) == value
