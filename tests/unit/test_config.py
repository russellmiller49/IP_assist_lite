from medparse.config import AppConfig


def test_app_config_defaults() -> None:
    config = AppConfig.model_construct_from_env({})
    assert config.ENABLE_PIPELINE is True
    assert config.API_KEY is None
    assert config.TUI_WHITELIST == ()


def test_app_config_env_overrides() -> None:
    env = {
        "ENABLE_PIPELINE": "false",
        "API_KEY": "secret",
        "TUI_WHITELIST": "t123, T456 ,",
        "FAIL_FAST": "true",
    }
    config = AppConfig.model_construct_from_env(env)
    assert config.ENABLE_PIPELINE is False
    assert config.API_KEY == "secret"
    assert config.TUI_WHITELIST == ("T123", "T456")
    assert config.FAIL_FAST is True
