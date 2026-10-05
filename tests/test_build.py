from corpus import build


def test_build_runs_steps_in_order_skips_and_survives_a_failure():
    ran = []

    async def observe(city):
        ran.append(("observe", city))

    def judge(city):
        raise SystemExit("no LLM endpoint reachable")

    steps = (("gmaps qc", lambda c: ran.append(("qc", c))), ("gmaps observe", observe), ("judge audit", judge),
             ("tiktok observe", lambda c: ran.append(("tiktok", c))), ("aggregate", lambda c: ran.append(("agg", c))))
    out = build.once("dalat", {"tiktok"}, steps)
    assert ran == [("qc", "dalat"), ("observe", "dalat"), ("agg", "dalat")]
    assert out == {"gmaps qc": "ok", "gmaps observe": "ok", "judge audit": "failed", "tiktok observe": "skipped",
                   "aggregate": "ok"}
