from types import SimpleNamespace

from app.provisioning import ReminderProvisioning


def test_ntfy_password_stdin_uses_lf_bytes_and_recovers_existing_user(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((list(command), kwargs))
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0,
                               stderr=b"user already exists" if len(calls) == 1 else b"")

    monkeypatch.setattr("app.provisioning.subprocess.run", run)
    provisioning = ReminderProvisioning.__new__(ReminderProvisioning)
    provisioning.settings = SimpleNamespace(ntfy_container="synthetic-ntfy")
    provisioning._ntfy("synthetic-user", password="synthetic-password")
    assert len(calls) == 2
    for command, options in calls:
        assert options["input"] == b"synthetic-password\n"
        assert b"\r" not in options["input"]
        assert not options.get("text")
        assert "synthetic-password" not in " ".join(command)
    assert "user change-pass" in calls[1][0][6]
