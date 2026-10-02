"""Dev check, needs the UIT network: the shipped REVIEW_OBSERVE prompt on 16 hand-picked review sentences (known
v4 errors + positive cases). Run from the repo root: python scripts/observe_prompt_eval.py"""
import asyncio, sys
sys.path.insert(0, "src")
from corpus.observe.gmaps import extract
from corpus.ontology import load

CASES = [
 ("Ko đặt bàn trước được, đồ ăn chờ lâu, ko ngon", {"bad": [("booking_needed", "yes")]}),
 ("Mình đặt bàn trước nhưng đến vẫn hết bàn ngoài vườn, phải vào lều.", {"bad": [("booking_needed", "yes")]}),
 ("Đường đi có hơi xa 1 chút nhưng không khí rất tuyệt.", {"bad": [("long_walk", "present")]}),
 ("Đi hơi xa nhưng trải nghiệm rất tuyệt, mát lạnh", {"bad": [("long_walk", "present")]}),
 ("Vườn có mái che kín nên không sợ mưa gió, lầy lội", {"bad": [("weather_exposed", "present")], "good": [("weather_exposed", "sheltered")]}),
 ("View rừng cực chill ko sợ nắng gắt.", {"bad": [("weather_exposed", "present")]}),
 ("Giá cao, không gian chật chội, rất nóng trên tầng 2.", {"bad": [("weather_exposed", "present")]}),
 ("Quá đông khách, bao nhiêu khách cũng nhận, quá tải, khó chụp hình.", {"bad": [("photo_spot", "present")]}),
 ("Xe mới, xịn, đủ chinh chiến mấy con dốc Đà Lạt", {"bad": [("condition_change", "improved")]}),
 ("Quán ở lưng chừng dốc nên cẩn thận khi tới quán. Bánh rất thơm.", {"bad": [("steep_or_stairs", "present")]}),
 ("Đông lắm, cuối tuần tới là hết bàn, nên đặt trước", {"good": [("booking_needed", "yes")]}),
 ("Phải leo hơn 300 bậc thang mới lên tới đỉnh, mỏi chân", {"good": [("steep_or_stairs", "present")]}),
 ("Đậu xe ngay cổng, đi vài bước là tới, đường bằng phẳng nên ông bà đi được", {"good": [("long_walk", "absent"), ("steep_or_stairs", "absent")]}),
 ("Đi tham quan một vòng mất khoảng 2 tiếng", {"good": [("visit_duration", "1_to_2h")]}),
 ("Trời mưa là đường đất lầy, không chơi được, nên đi mùa khô", {"good": [("weather_exposed", "present")]}),
 ("Vé vào cổng 50k, gửi xe xong phải đi bộ gần 2km mới tới thác", {"good": [("long_walk", "present")]}),
]

async def main():
    ont = load()
    slots = extract.Slots(await extract._providers())
    place = {"name": "Địa điểm thử", "category": "Điểm thu hút khách du lịch"}
    refs = {f"r{i}": {"review_id": f"R{i}", "text": t} for i, (t, _) in enumerate(CASES, 1)}
    kept, _, dropped = await extract.ask_checked(slots, "Đà Lạt", place, ont, list(refs.items()))
    final = []
    for ref, o in kept:
        v = await extract.check_span(slots, place, refs[ref]["text"], ont, o) if ont.features[o["feature"]].span_check else "supports"
        final.append((ref, o["feature"], o["value"], o["quote"], v))
    ok = 0; total = 0
    for i, (t, exp) in enumerate(CASES, 1):
        got = {(f, v) for r, f, v, q, verdict in final if r == f"r{i}" and verdict == "supports"}
        for pair in exp.get("bad", []):
            total += 1; ok += pair not in got
            print(("OK  " if pair not in got else "FAIL"), "no", pair, "|", t[:50])
        for pair in exp.get("good", []):
            total += 1; ok += pair in got
            print(("OK  " if pair in got else "FAIL"), "has", pair, "|", t[:50])
    print(f"\n{ok}/{total}")
    for row in final: print(row)
    print(dict(dropped))

asyncio.run(main())
