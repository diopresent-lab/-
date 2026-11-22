import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "reel"))
import make_reel as mr  # noqa: E402

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "reel", "configs", "example.json")


def base_cfg():
    with open(EXAMPLE, encoding="utf-8") as f:
        return mr.merge(mr.DEFAULTS, json.load(f))


def test_example_config_is_valid():
    errors, _ = mr.validate(base_cfg())
    assert errors == []


def test_hook_names_include_main_and_variants():
    assert mr.hook_names(base_cfg()) == ["friend", "contrast", "question", "age", "tag"]


def test_with_hook_swaps_text_and_sub_without_touching_original():
    cfg = base_cfg()
    out = mr.with_hook(cfg, name="contrast")
    assert out["hook"]["text"] == "낮엔 [도면]\n밤엔 [노래]"
    assert out["hook"]["sub"] == "40대 건축사의 이중생활"
    assert out["hook"]["name"] == "contrast"
    assert cfg["hook"]["name"] == "friend"


def test_with_hook_variant_without_sub_drops_main_sub():
    cfg = base_cfg()
    cfg["hook"]["variants"].append({"name": "bare", "text": "짧은 훅"})
    assert "sub" not in mr.with_hook(cfg, name="bare")["hook"]


def test_with_hook_custom_text():
    out = mr.with_hook(base_cfg(), text="[친구] 떠올려 보세요", sub="보조")
    assert out["hook"]["text"] == "[친구] 떠올려 보세요"
    assert out["hook"]["sub"] == "보조"


def test_unknown_hook_name_errors():
    with pytest.raises(mr.ConfigError):
        mr.with_hook(base_cfg(), name="nope")


@pytest.mark.parametrize("variant, msg", [
    ({"name": "contrast", "text": "x"}, "중복"),
    ({"name": "a b", "text": "x"}, "영문"),
    ({"name": "late", "text": "x", "end": 3.5}, "3초"),
    ({"text": "x"}, "name과 text"),
])
def test_bad_variants_are_rejected(variant, msg):
    cfg = base_cfg()
    cfg["hook"]["variants"].append(variant)
    errors, _ = mr.validate(cfg)
    assert any(msg in e for e in errors), errors


def test_long_hook_warns():
    cfg = base_cfg()
    cfg["hook"]["text"] = "이 훅 문구는 일부러 아주 길게 써서 삼 초 안에 다 읽기 어렵습니다"
    _, warnings = mr.validate(cfg)
    assert any("20자" in w for w in warnings)


def test_bad_style_rejected():
    cfg = base_cfg()
    cfg["hook"]["style"] = "neon"
    errors, _ = mr.validate(cfg)
    assert any("style" in e for e in errors)


def test_first_frame_shows_hook(tmp_path):
    try:
        fonts = mr.Fonts(base_cfg()["theme"])
    except mr.ConfigError:
        pytest.skip("한글 글꼴 없음")
    cfg = base_cfg()
    cfg["visual"] = "none"
    frame = mr.render_frame(cfg, fonts, 0.0)
    # 훅 영역(가운데 위쪽)에 강조색 픽셀이 있어야 한다 = 0초부터 훅이 보인다
    region = frame.crop((60, 450, 1020, 950)).getcolors(1 << 20)
    accent = tuple(int(cfg["theme"]["accent"][i:i + 2], 16) for i in (1, 3, 5))
    assert any(c == accent for _, c in region)
