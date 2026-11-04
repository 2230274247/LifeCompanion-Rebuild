import json

from app.config import load_settings


def test_memos_user_tokens_load_from_absolute_file(monkeypatch, tmp_path):
    tokens_file = tmp_path / "memos-tokens.json"
    tokens_file.write_text(
        json.dumps({"users/synthetic-owner": "synthetic-pat"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.config.load_model_keys",
        lambda *args, **kwargs: {
            "file_status": "TEST_ISOLATED",
            "loaded": [],
        },
    )
    monkeypatch.setenv("LIFE_MEMOS_TOKENS_FILE", str(tokens_file))

    settings = load_settings()

    assert settings.memos_user_tokens == {
        "users/synthetic-owner": "synthetic-pat"
    }
