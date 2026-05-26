import pytest
from nanobot.config.schema import Config, EmailToolConfig, WelinkToolConfig


def test_email_config_defaults():
    cfg = EmailToolConfig()
    assert cfg.enable is False
    assert cfg.allowed_domains == ["huawei.com"]


def test_welink_config_defaults():
    cfg = WelinkToolConfig()
    assert cfg.enable is False
    assert cfg.xiaoluban_url == "http://xiaoluban.rnd.huawei.com:80/"
    assert cfg.xiaoluban_auth == ""
    assert cfg.rate_limit_per_minute == 20
    assert cfg.rate_limit_per_day == 200


def test_tools_config_includes_email_and_welink():
    cfg = Config()
    assert hasattr(cfg.tools, "email")
    assert hasattr(cfg.tools, "welink")
    assert cfg.tools.email.enable is False
    assert cfg.tools.welink.enable is False


def test_config_from_json():
    cfg = Config.model_validate({
        "tools": {
            "email": {"enable": True, "allowedDomains": ["huawei.com", "example.com"]},
            "welink": {"enable": True, "xiaolubanAuth": "j00954996_abc123"},
        }
    })
    assert cfg.tools.email.enable is True
    assert cfg.tools.email.allowed_domains == ["huawei.com", "example.com"]
    assert cfg.tools.welink.enable is True
    assert cfg.tools.welink.xiaoluban_auth == "j00954996_abc123"
