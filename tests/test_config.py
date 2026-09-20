from pathlib import Path

from threads_to_naver.config import Config


def test_footer_settings_are_loaded_relative_to_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'footer_url = "https://naver.me/example"\n'
        'footer_image_path = "assets/footer.png"\n',
        encoding="utf-8",
    )

    config = Config.load(config_path)

    assert config.footer_url == "https://naver.me/example"
    assert config.footer_image_path == (tmp_path / "assets/footer.png").resolve()


def test_simplenote_defaults_use_local_read_only_runtime(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('source = "simplenote"\n', encoding="utf-8")

    config = Config.load(config_path)

    assert config.source == "simplenote"
    assert config.simplenote_tag == "naver"
    assert config.simplenote_provider == "local"
    assert config.simplenote_scan_limit == 100
    assert config.simplenote_max_notes_per_run == 2
    assert config.simplenote_mcp_command.name == "simplenote-mcp"


def test_simplenote_api_provider_does_not_require_a_local_store(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'source = "simplenote"\nsimplenote_provider = "api"\n',
        encoding="utf-8",
    )

    config = Config.load(config_path)

    assert config.simplenote_provider == "api"
    assert config.simplenote_store_path is None
