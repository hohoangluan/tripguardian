from fixtures import si, srec

from decision.diversify import display_group, pick, sizes
from decision.model import Cand
from decision.settings import default

CFG = default()


def c(fid, score, dup=None, group="cafe", role="experience"):
    x = Cand(srec(fid, dup=dup, group=group), role)
    x.score = score
    return x


def test_sizes_follow_days_pace_and_anchors():
    assert sizes(si(), 2, 1, CFG) == {"experience": 12, "meal": 7}
    assert sizes(si(pace={"level": "slow"}), 1, 5, CFG)["experience"] == 2  # never below one slot


def test_display_group():
    assert display_group(c("A", 1, role="meal"), CFG) == "meal"
    assert display_group(c("A", 1, group="garden_farm"), CFG) == "nature"
    assert display_group(c("A", 1, group="cafe"), CFG) == "chill"
    assert display_group(c("A", 1, group="unheard"), CFG) == "sights"


def test_pick_one_per_near_duplicate_group_rest_are_alternatives():
    a, b, cc, d = c("A", 3.0, dup=1), c("B", 2.0, dup=1), c("C", 1.5), c("D", 1.0)
    reps, alts = pick([d, cc, b, a], 2, CFG)
    assert [r.id for r in reps] == ["A", "C"] and [x.id for x in alts["A"]] == ["B"]
    assert pick([a], 0, CFG) == ([], {})
