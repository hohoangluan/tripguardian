from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
LANDING = ROOT / "web/src/user/screens/Landing.tsx"
STYLES = ROOT / "web/src/user/css/landing.css"


def test_landing_uses_six_chapter_sticky_3d_story() -> None:
    source = LANDING.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "const BEATS = 6" in source
    assert 'className="tg-l3__chs"' in source
    assert len(re.findall(r'className="tg-l3__ch(?: |")', source)) == 6
    assert "scrollTrigger: { trigger: sec" in source
    assert ".tg-l3 { position: relative; height: 640vh; }" in styles
    assert ".tg-l3__stage { position: sticky;" in styles


def test_landing_keeps_approved_hero_layout_and_current_guest_entry() -> None:
    source = LANDING.read_text(encoding="utf-8")

    assert "Lịch trình Đà Lạt <em>vừa với bạn.</em>" in source
    assert "Kể chuyến đi trong 2 phút." in source
    assert "Lên lịch chuyến của bạn" in source
    assert "Xem cách hoạt động" in source
    assert "Miễn phí" in source
    assert "Không cần tài khoản" in source
    assert "Chỉ gồm nơi có thật" in source
    assert "Xoay thử Đà Lạt 3D" in source
    assert "await startGuest()" in source


def test_landing_retains_non_animated_fallbacks() -> None:
    source = LANDING.read_text(encoding="utf-8")

    assert "const PLATES = [" in source
    assert "if (!still)" in source
    assert "tg-l3__plates" in source
    assert "?3d=on" in source
