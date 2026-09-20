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
