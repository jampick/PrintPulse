"""Tests for printpulse.config module."""

from printpulse.config import Config, FONT_MAP, PAGE_PRESETS


def test_font_map_is_populated():
    assert len(FONT_MAP) > 10
    for name, hershey_id in FONT_MAP.items():
        assert isinstance(name, str)
        assert isinstance(hershey_id, str)


def test_font_map_has_common_fonts():
    assert "Cursive" in FONT_MAP
    assert "Block" in FONT_MAP
    assert "Gothic" in FONT_MAP


def test_page_presets():
    assert "letter" in PAGE_PRESETS
    assert "a4" in PAGE_PRESETS
    assert "a3" in PAGE_PRESETS
    for name, dims in PAGE_PRESETS.items():
        assert len(dims) == 2
        assert dims[0] > 0
        assert dims[1] > 0


def test_config_defaults():
    cfg = Config()
    assert cfg.page_width_in == 8.5
    assert cfg.page_height_in == 11.0
    assert cfg.margin_in == 0.75
    assert cfg.margin_top_in == 0.5
    assert cfg.font_name == "futural"
    assert cfg.font_size == 14.0
    assert cfg.dry_run is False


def test_config_pt_properties():
    cfg = Config()
    assert cfg.page_width_pt == 8.5 * 72
    assert cfg.page_height_pt == 11.0 * 72
    assert cfg.margin_pt == 0.75 * 72
    assert cfg.margin_top_pt == 0.5 * 72


def test_config_text_area():
    cfg = Config()
    expected_w = cfg.page_width_pt - 2 * cfg.margin_pt
    expected_h = cfg.page_height_pt - cfg.margin_top_pt - cfg.margin_pt
    assert cfg.text_area_width_pt == expected_w
    assert cfg.text_area_height_pt == expected_h


def test_apply_page_preset():
    cfg = Config()
    cfg.apply_page_preset("a4")
    assert cfg.page_width_in == 8.27
    assert cfg.page_height_in == 11.69


def test_apply_invalid_preset_is_noop():
    cfg = Config()
    original_w = cfg.page_width_in
    cfg.apply_page_preset("nonexistent")
    assert cfg.page_width_in == original_w
