import asyncio
import json
import time

from corpus.crawl.common.throttle import Throttle


def test_grows_one_tab_per_clean_streak_up_to_max(tmp_path):
    t = Throttle(tmp_path / "t.json", start=2, hi=4, grow_after=3, cooldown_s=0)

    async def run():
        for _ in range(20):
            async with t:
                pass
            t.success()
    asyncio.run(run())
    assert t.limit == 4


def test_block_halves_tabs_and_cools_down(tmp_path):
    t = Throttle(tmp_path / "t.json", start=6, hi=8, grow_after=3, cooldown_s=0.3)

    async def run():
        async with t:
            t.blocked()
        start = time.monotonic()
        async with t:
            pass
        return time.monotonic() - start
    waited = asyncio.run(run())
    assert t.limit == 3 and waited >= 0.25


def test_never_below_one_tab(tmp_path):
    t = Throttle(tmp_path / "t.json", start=1, hi=8, grow_after=3, cooldown_s=0)
    t.blocked()
    assert t.limit == 1


def test_concurrency_stays_within_limit(tmp_path):
    t = Throttle(tmp_path / "t.json", start=3, hi=3, grow_after=100, cooldown_s=0)
    active, peak = [0], [0]

    async def job():
        async with t:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            await asyncio.sleep(0.02)
            active[0] -= 1

    async def run():
        await asyncio.gather(*(job() for _ in range(10)))
    asyncio.run(run())
    assert peak[0] == 3


def test_learned_limit_is_saved_and_reused(tmp_path):
    p = tmp_path / "t.json"
    t = Throttle(p, start=2, hi=8, grow_after=1, cooldown_s=0)
    t.success()
    t.success()
    assert json.loads(p.read_text(encoding="utf-8"))["limit"] == 4
    assert Throttle(p, start=2, hi=8).limit == 4
    assert Throttle(p, start=2, hi=3).limit == 3  # never above the configured max


def test_repeated_blocks_double_the_cooldown_and_success_resets(tmp_path):
    t = Throttle(tmp_path / "t.json", start=4, hi=8, cooldown_s=10, max_cooldown_s=35)
    t.blocked()
    first = t._until - time.monotonic()
    t._until = 0  # cooldown over, still blocked
    t.blocked()
    second = t._until - time.monotonic()
    t._until = 0
    t.blocked()
    third = t._until - time.monotonic()
    assert 9 < first <= 10 and 19 < second <= 20 and 34 < third <= 35
    t._until = 0
    t.success()
    t.blocked()
    assert 9 < t._until - time.monotonic() <= 10


def test_one_block_event_seen_by_many_tabs_counts_once(tmp_path):
    t = Throttle(tmp_path / "t.json", start=8, hi=8, cooldown_s=10)
    for _ in range(5):  # five tabs fail during the same block
        t.blocked()
    assert t.limit == 4 and t._until - time.monotonic() <= 10


def test_failed_level_needs_twice_the_clean_streak_before_next_try(tmp_path):
    t = Throttle(tmp_path / "t.json", start=1, hi=4, grow_after=2, cooldown_s=0)
    t.success(); t.success()
    assert t.limit == 2  # first try at 2 after 2 clean items
    t.blocked()
    assert t.limit == 1
    for _ in range(3):
        t.success()
    assert t.limit == 1  # 2 failed once: now needs 4
    t.success()
    assert t.limit == 2
    t.blocked()
    for _ in range(7):
        t.success()
    assert t.limit == 1  # failed twice: needs 8
    t.success()
    assert t.limit == 2


def test_holding_a_level_forgives_its_failures(tmp_path):
    t = Throttle(tmp_path / "t.json", start=1, hi=4, grow_after=2, cooldown_s=0)
    t.success(); t.success()
    t.blocked()  # 2 failed once
    for _ in range(4):
        t.success()
    assert t.limit == 2
    t.success(); t.success()  # held 2 for a full streak: grows to 3, and 2 is trusted again
    assert t.limit == 3
    t.blocked()  # back to 1 (3 // 2)
    t.success(); t.success()
    assert t.limit == 2  # 2's old failure was forgiven: normal streak
