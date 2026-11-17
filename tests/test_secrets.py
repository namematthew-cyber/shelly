from shelly import masking


def test_mask_env_assignments():
    text = "GEMINI_API_KEYS=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345\nSHELLY_TG_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    masked = masking.mask(text)
    assert "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in masked
    assert "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi" not in masked
    assert "GEMINI_API_KEYS=***" in masked
    assert "SHELLY_TG_TOKEN=***" in masked


def test_mask_raw_keys():
    for key in (
        "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        "AQ.Ab8RN6Lfo1234567890123456789012345678901234567890",
        "AKIAIOSFODNN7EXAMPLE",
        "sk-abcdefghijklmnopqrstuvwxyz123456",
    ):
        assert key not in masking.mask(f"вот ключ: {key}")


def test_mask_private_key():
    text = "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
    masked = masking.mask(text)
    assert "secret" not in masked
    assert "PRIVATE KEY" not in masked


def test_mask_can_be_disabled(monkeypatch):
    monkeypatch.setattr(masking, "ENABLED", False)
    assert masking.mask("plain text") == "plain text"
