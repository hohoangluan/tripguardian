# Ideas & Methods — "Too many places" and the Three Plans

> Replaces my earlier `PLANNING_OVERLOAD_AND_PROFILES_PROPOSAL.md`. That one was written from the technical report only. This one is written after reading the repo (commit `173d81e`): `src/decision/feasibility.py`, `src/planning/{variants,objectives,days,build,validate,session}.py`, `config/planning.yaml`, `config/decision.yaml`, `docs/plans/*`.
> It is a list of **ideas and methods to choose from**, not a spec. Section 1 says what the code does today, section 2 lists the gaps I found, sections 3–7 are the ideas.
> **Mục 5 (định nghĩa ba kế hoạch) viết bằng tiếng Việt** vì đây là phần chốt định nghĩa: 5 điều kiện của kế hoạch trải nghiệm tốt nhất, định nghĩa kế hoạch tiết kiệm và kế hoạch gọn tuyến.

---

## 1. What the code does today (verified in source)

| Area | Behaviour | Where |
|---|---|---|
| Overload detection | Decision compares `needed = Σ typical visit + buffer + travel` with `available = Σ day windows`. `needed > available` → a `time` conflict. `needed > 1.35 × available` → status `infeasible`; other conflicts → `partial`. Also checks `per_day` cap, `far_areas`, `budget`, `time_windows`, closed days, hard-filter relax | `decision/feasibility.py` `evaluate()`, `infeasible_ratio: 1.35` |
| Warning content | Each conflict carries `fixes`. For `time` the fixes are **the 2 lowest-score droppable places** ("Bớt khoảng N phút"). Anchors and locked are never offered | `feasibility.py` `removable[:2]` |
| Spare capacity | `room()` returns `usable / free / more / filled` ("Đủ cho chuyến đi" at `fill_share` 0.8) | `feasibility.room` |
| Planning variants | Up to 3 of 5 objectives (`least_travel, low_cost, weather_robust, diverse, preference_fit`), chosen by `choose()`. Each objective = **different day-split weights** (`objective_weights`) + a different score | `variants.py`, `objectives.py` |
| Membership | Every variant schedules **all** confirmed places (`schedule_trip` uses `sorted(trip.by_place)`). No code path drops a place to make a plan fit | `build.schedule_trip` |
| Day split | Exact DP over subsets of clusters (≤ 7 days, ≤ 8 clusters), greedy fallback (`days_fallback`). Every cluster must land on a day | `days.assign_days` |
| Overload at planning time | Kept as-is; `validate()` reports `day_window` etc. A variant that fails is dropped; **no valid variant → `back_to_decision`** with the places and reasons | `variants.build_variants`, `validate.blockers` |
| Drops by the user | `State.dropped` with reason, restore path, and `rethink_drops: 4` ("go back to Place Decision") | `planning/session.py`, `planning.yaml` |
| Never silent | Locked / anchor never droppable; `validate` is the only judge | `validate.py` |

So: **the system warns, but it can only warn and suggest ≤ 2 drops; it never offers a ready-made trimmed plan.** The skeleton for the fix (variants, dropped-list, validator, route cache keyed independent of weights) is already in place.

---

## 2. Gaps found (these explain "my system can't do that")

| # | Gap | Evidence |
|---|---|---|
| G1 | **`low_cost` cannot produce a cheaper plan.** Its day-split weights are `{}` (= the defaults) and its score is `Σ cost_vnd` of placed places. With the same set of places, that sum is identical in every variant. Only the tie-break (travel) can differ. | `planning.yaml: low_cost: {}`; `objectives.metrics/score` |
| G2 | The cost measure ignores **transport** and meals-as-estimate; only per-place cost | `objectives.metrics` |
| G3 | `diverse` is **5th** in `objective_order` and `max_variants` is 3, so with a budget and some preferences set it is cut. It is also only a *within-day* repeat count (`repeats`), not trip-level variety or novelty | `choose()`, `days.repeats` |
| G4 | `low_cost` appears only if `budget_vnd` is known | `choose()` |
| G5 | "Routing" (`least_travel`) only re-splits days. It cannot use the saved minutes for more places, because membership is fixed | `schedule_trip` |
| G6 | Overload fixes are 2 single-place drops ranked by score only. No "smallest set of drops that makes it fit", no alternatives | `feasibility.evaluate` |
| G7 | Decision's `needed` uses `typical` visit time and `2 × distance-to-area`; Planning can shrink visits to `short` (`DayCtx.allow_shrink`) and uses the real matrix. The two can disagree (`infeasible_ratio 1.35` is a hand-set starting value) | `feasibility._visit`, `days.can_start` / `route.py` |
| G8 | Your 98-places-in-14-days probe shows the outcome: all 98 kept, `ok=false` (`day_window`). Correct and fail-closed, but the user gets "no", not "here are 3 ways to make it work" | `PLANNING_PERFORMANCE.md` |

G1 is worth fixing even if you do nothing else: the "Chi phí thấp" label currently over-promises.

---

## 3. Core idea: a variant is `(weights, kept-set)`, not just `weights`

Today: `variant = schedule_trip(all_places, objective_weights)`.
Proposed: `variant = schedule_trip(subset(all_places, kept), objective_weights)`, where `kept` is chosen **per preset** by a small selector run *before* scheduling.

Why this fits the code well:

- `trip.routes` is keyed by `route_key(...)`, which **excludes the day-split weights**, so orderings found for one preset are reused by the others and by later retries on subsets.
- A variant already carries what the UI needs: `itinerary`, `metrics`, `robustness`, `backups`, `warnings`. Add `kept`, `dropped[]`, `preset`.
- The user-facing "dropped" list already exists in the session (`State.dropped` + reason + restore). A composer variant can be expressed as a *pre-applied dropped set*, so "restore this place" needs no new mechanism.
- `must = anchors ∪ locked ∪ priority-must` is already the untouchable set (`feasibility.removable`, `validate` anchor check).

Presets map onto existing names:

| Preset (user label) | Objective id | Change needed |
|---|---|---|
| 💰 Tiết kiệm | `low_cost` | Make it choose a subset (G1/G2). |
| ✨ Trải nghiệm nhất | `diverse` (+ novelty) | Trip-level coverage; always shown when overloaded (G3). |
| 🧭 Gọn tuyến, đi được nhiều nơi | `least_travel` | Subset by "most places per travel minute" + refill with saved time (G5). |

Rule: when Decision status is `partial/infeasible` because of `time`/`per_day`, or the load level is ≥ *tight* (below), **force these three presets** instead of `choose()`. Otherwise keep today's behaviour.

---

## 4. Methods for choosing the kept set (pick one; they can be layered)

All of them treat `validate()` as the oracle, so a bug in the selector cannot produce an invalid plan that looks valid.

### Method A — Reverse delete with batch drop (simplest, good first version)

```text
kept = all
while load(kept) > rho * available:            # cheap estimate, no scheduling
    drop the optional place with the best (time_saved / regret_p)   # regret depends on preset
verify: schedule_trip(kept) ; validate
while violations and optional left:            # usually 0–2 rounds
    drop next-best, reschedule
```

- `time_saved` = visit + buffer + marginal detour (use the cluster/area estimate Decision already computes).
- Batch-dropping with the estimate first keeps the number of `schedule_trip` calls small.
- Weak spot: greedy, so it can strand a cluster with one place left. Fix: when a cluster drops to one place, re-score that place with the whole detour charged to it.

### Method B — Forward greedy from the must-set (better for the routing preset)

```text
kept = must
repeat: add the optional place with best (gain_p / marginal_time_p)   # cheapest insertion
        stop when no place fits within rho * available
verify with schedule_trip + validate
```

Feasible by construction, and naturally produces "as many places as fit". `marginal_time_p` = visit + buffer + cheapest-insertion detour from the existing tours.

### Method C — Add a "skip" bin to the existing DP (exact at cluster level, tiny change)

`assign_days` already searches subsets of clusters over `d` days. Add one extra layer, "not visited", whose cost for a cluster is the preset's *regret* of its optional places. Clusters containing `must` places cannot go to the skip bin.

- Cost stays O(d·3ⁿ) with n ≤ 8, plus the dummy layer. No new dependency.
- Exact over clusters; a second pass trims individual places inside kept clusters (per day, enumerate subsets of ≤ ~10 optional places, ordering each with the existing `order_day`; hits `trip.routes` cache).
- Reuses `day_cost` (which already has `overflow`), so the DP *itself* pays for overload.

### Method D — OR-Tools orienteering (only if A–C prove too weak)

Optional nodes with a skip penalty = prize (OR-Tools routing "disjunction with penalty"), or CP-SAT. This is the optimizer that `docs/plans/PLANNING_IMPROVEMENT_PROPOSAL.md` §7 already suggests (`x_i = visited`). Costs: a new dependency, integer scaling of minutes, and determinism/tie-break work (the repo promises "same input → same output"). I would not start here: n is small enough that A+C is exact or near-exact.

**Recommendation:** C for the day split (it is a ~30-line change to a function you already trust), A for the place-level trim, B for the routing preset. D stays on the shelf.

---

## 5. Định nghĩa ba kế hoạch

### 5.0 Cái chung và cái khác

Cả ba là **đề xuất** lấy từ cùng danh sách người dùng đã chọn (`selection`); chỉ có hiệu lực khi người dùng xác nhận. Điểm chung (ràng buộc cứng, không kế hoạch nào được phá):

- `must ⊆ kept ⊆ selection`. `must` = anchor + nơi đã khóa + nơi ưu tiên bắt buộc. Không thêm nơi mới.
- `validate()` sạch: giờ mở cửa, hard filter, ghim giờ, thời tiết nặng, chồng lấn, ngân sách (đúng như hiện có).
- Tổng tải ≤ ρ × thời gian có (ρ ≈ 0,9) và số nơi mỗi ngày ≤ `per_day_max[pace]`.
- Mọi nơi bị bỏ được liệt kê kèm lý do và khôi phục được; không bỏ lặng lẽ.

Ba kế hoạch khác nhau ở **giữ nơi nào** và **chấp nhận hy sinh gì**:

| | 💰 Tiết kiệm | ✨ Trải nghiệm tốt nhất | 🧭 Gọn tuyến |
|---|---|---|---|
| Câu hỏi nó trả lời | Rẻ nhất mà vẫn giữ phần lớn điều tôi muốn? | Chuyến đáng nhớ nhất mà không bị vội? | Ít thời gian trên đường nhất, đi được nhiều nơi nhất? |
| Tối ưu chính | Tổng chi phí ước tính | Mong muốn được đáp ứng, đa dạng, mới, đúng giờ | Số nơi, rồi tỷ lệ thời gian ở nơi |
| Thời gian ở mỗi nơi | Như hiện tại (được rút xuống `short` khi cần) | **Đủ ước lượng, không rút** (`allow_shrink=False`) | Được rút xuống `short`, ghi rõ trên thẻ |
| Sẵn sàng hy sinh | Nơi đắt, điểm thấp | Số nơi, tiền, quãng đường | Độ đa dạng, thời gian ở mỗi nơi |
| Tên trong code hiện có | `low_cost` | `diverse` (mở rộng) | `least_travel` |

Ba kế hoạch có thể trùng nhau nếu dữ liệu quá hẹp (ví dụ nơi đắt cũng là nơi xa). Khi đó gộp thẻ, ghi hai nhãn, và dùng chỗ trống cho kế hoạch `balanced` (mục 5.4).

---

### 5.1 ✨ Trải nghiệm tốt nhất

**Định nghĩa một câu:** lịch đáp ứng nhiều nhất điều người dùng đã nói muốn, đi ở nhịp không vội, đa dạng, đúng giờ đẹp, và còn vững khi có sự cố.

Không định nghĩa là "nhiều nơi nhất" (đó là kế hoạch Gọn tuyến, và sẽ bị vội) và cũng không phải "tổng điểm cao nhất" (sẽ chọn 5 quán cà phê giống nhau).

#### Năm điều kiện, mỗi điều kiện đo được

| # | Điều kiện | Định nghĩa đo được | Lấy từ đâu | Hiện trên thẻ |
|---|---|---|---|---|
| 1 | **Đáp ứng mong muốn** | `W` = tập mong muốn của chuyến (feature trong `soft_weights`, hoạt động đã nêu, anchor loại `want`). Mong muốn `w` được *đáp ứng* khi có nơi trong `kept` mang feature `w` ở trạng thái `present` với bằng chứng đã xác minh, và, nếu feature có ghim giờ, nơi đó được xếp đúng khung giờ. `coverage = đáp ứng / |W|`. Mong muốn chưa có bằng chứng: không tính là đáp ứng nhưng cũng không phạt, ghi "chưa xác minh" | Search Input, serving record (`experience`), `pins` trong `planning.yaml` | "Đáp ứng 4/5 mong muốn" |
| 2 | **Không bị vội** | (a) mỗi nơi `p`: `r_p = phút ở p / thời lượng theo visit_key của nhịp độ ≥ 0,9` (ngưỡng trong config); (b) lịch hợp lệ khi chạy với `allow_shrink=False`; (c) số nơi mỗi ngày ≤ `per_day[pace]` (3/4/6), trừ nơi `must`; (d) không chặng nào vượt `max_leg_min` của người dùng, và ≤ 1 chặng dài hơn `long_leg_min` (30 phút) mỗi ngày *(đề xuất)*; (e) không phải cắt nghỉ (`max_consecutive_min`, `rest_min`) | `DayCtx.allow_shrink`, `visit_key`, `per_day`, `validate` | "Mỗi nơi ở đủ lâu" |
| 3 | **Đa dạng cả chuyến** | `V(S) = số kind_group khác nhau + Σ_kind √n_kind` (thưởng giảm dần khi lặp loại); trừ `repeats` trong ngày (đã có) và nơi cùng `near_duplicate_group` | `traits.kind_group`, `days.repeats`, serving record | "6 loại trải nghiệm" |
| 4 | **Mới lạ theo gu** | `N(S) = w_nov · Σ nov_p`, `nov_p` là thành phần novelty của điểm Decision. `w_nov` theo lựa chọn của người dùng: "theo gu quen" → 0, "trộn" → vừa, "thử mới" → cao. `visited` chỉ giảm bonus, không phạt nơi người dùng đã chọn hoặc khóa rõ ràng (đã đến ≠ đã thích) | Trip State (`novelty`, `visited`), Decision score | "3 nơi mới" |
| 5 | **Đúng giờ đẹp, ít rủi ro** | `T(S)` = tỷ lệ nơi có ghim giờ được xếp đúng khung + điểm `time_suitability`. `R(S)` = `rain_exposed` + `crowd_risk` (nhân hệ số khi người dùng tránh đông) + số nơi giờ mở cửa `UNCERTAIN/OUTDATED`. Độ vững phải ≥ "Khả thi" | `pins`, `objectives.metrics`, `days.crowd_risk`, `robustness` | "3/3 điểm hoàng hôn đúng giờ" |

#### Cách kết hợp: thứ tự ưu tiên, không cộng điểm

Cộng điểm với trọng số khiến một tiêu chí lấn át mong muốn thật và phải chỉnh trọng số mãi. So sánh hai lịch theo thứ tự từ điển:

```text
E(S) = (  ràng buộc cứng  ∧  không_vội(S)  ∧  độ_vững(S) ≥ "Khả thi",     # tầng 1: điều kiện cần
          coverage(S),                                                       # tầng 2: mong muốn
          w_var·V(S) + w_nov·N(S) + w_time·T(S) − w_risk·R(S) + Σ utility,  # tầng 3: chất lượng
          − travel_min(S) )                                                  # tầng 4: hòa → ít di chuyển hơn, rồi id
```

- **Không vội thắng mong muốn** khi hai thứ xung đột: nếu giữ nơi cuối cùng đáp ứng một mong muốn mà làm cả lịch bị vội thì bỏ nơi đó. Thẻ phải nói rõ: "Chưa đáp ứng: săn mây (nơi duy nhất cần buổi sáng sớm, ngày 2 đã đầy)".
- **Nơi duy nhất đáp ứng một mong muốn** (trong `selection`) chỉ bị bỏ khi không còn cách nào khác.
- Trọng số tầng 3 lấy từ Trip State, không cố định: `w_nov` theo gu mới/quen, `w_risk` tăng khi `crowd_tolerance=avoid`, `w_time` tăng khi mục đích là chụp ảnh.
- Tìm lịch: tham lam tiến từ tập `must` (Method B, mục 4), mỗi lượt thêm nơi làm `E` tăng nhiều nhất trên thời gian cần thêm, rồi `schedule_trip` với `allow_shrink=False` và `validate`. Nếu độ vững chỉ "Mong manh" thì bỏ bớt một nơi và thử lại.
- Cái giá nêu thẳng: kế hoạch này thường tốn hơn và đi nhiều hơn hai kế hoạch kia; thẻ ghi chênh lệch so với "Giữ tất cả".

---

### 5.2 💰 Tối ưu chi phí

**Định nghĩa một câu:** lịch có tổng chi phí ước tính thấp nhất trong các lịch còn giữ được ít nhất `α` giá trị mà người dùng đặt vào danh sách đã chọn.

- **Chi phí `C(S)` mỗi người** gồm: vé/giá ước tính của các nơi giữ (`cost_vnd`) **+** đi lại ước tính = `phút di chuyển × giá mỗi phút theo phương tiện` (đặt trong `planning.yaml`, ghi "ước lượng"; dùng phút vì OSRM trả phút, dùng km cần thêm độ dài tuyến) **+** chỗ ở nếu có biến thể chỗ ở (`add_lodging_cost`; v1 giữ nguyên chỗ ở đã chọn nên là hằng số, không ảnh hưởng việc chọn nơi). Bữa ăn tự chọn trong khung trống **chưa được tính**; ghi rõ như vậy.
- **Giá chưa biết** không phải 0: đếm riêng (`cost_unknown`), khi xếp hạng dùng khoảng theo trung vị loại hình, hiển thị "+N nơi chưa có giá". Nếu số nơi chưa biết giá nhiều thì không gọi là "rẻ nhất" mà ghi "rẻ nhất trong phần đã biết giá".
- **Ràng buộc giữ giá trị:** `Σ utility(kept) ≥ α · Σ utility(selection)`, bắt đầu `α = 0,7`. Có `budget_vnd` thì thêm ràng buộc ngân sách theo ngày như `validate` đang làm; không có thì vẫn cho kế hoạch này (hiện `low_cost` chỉ xuất hiện khi biết ngân sách).
- **Thứ tự bỏ:** tỷ lệ `tiền tiết kiệm / utility mất`, cao nhất bỏ trước. Nơi miễn phí và nơi đã khóa bỏ cuối cùng. Nơi vé đắt mà điểm thấp bỏ đầu tiên.
- **Khác Gọn tuyến:** tiết kiệm có thể chấp nhận đi xa hơn nếu rẻ hơn; Gọn tuyến thì không.
- **Hiện trên thẻ:** tổng chi phí đã biết mỗi người, chênh so với "Giữ tất cả", số nơi chưa có giá, ngân sách còn lại nếu có.
- **Vì sao cần chọn tập con:** hiện `low_cost` dùng trọng số chia ngày mặc định và chấm bằng tổng giá các nơi đã xếp; với cùng tập nơi, tổng đó như nhau ở mọi phương án, nên không thể rẻ hơn. Chỉ khi được bỏ nơi, hoặc tính thêm chi phí đi lại, kế hoạch này mới thật sự rẻ hơn.

---

### 5.3 🧭 Tối ưu lộ trình

**Định nghĩa một câu:** lịch đi được nhiều nơi nhất trong thời gian có, và trong cùng số nơi thì dành tỷ lệ thời gian lớn nhất cho việc *ở* nơi đó thay vì ngồi trên xe.

- **Hai đại lượng:** `T_travel` = tổng phút di chuyển (`travel_min` đã có); `T_visit` = tổng phút ở các nơi; `mật độ D = T_visit / (T_visit + T_travel)`; `N` = số nơi giữ.
- **Thứ tự ưu tiên:** (1) tối đa `N`; (2) trong cùng `N`, tối đa `D` (tức giảm `T_travel`); (3) hòa → tổng utility lớn hơn, rồi id.
- **Làm thế nào để đi ít mà được nhiều:** ưu tiên cụm dày (cụm theo thời gian di chuyển thật, đường kính ≤ 25 phút), nơi gần điểm xuất phát và anchor; mỗi ngày một khu, tránh đi về giữa hai khu xa nhau (`far_areas`); chia ngày với trọng số di chuyển cao (hiện `least_travel: {travel: 2.0}`); tìm tập nơi bằng tham lam tiến theo `lợi / phút thêm`, trong đó phút thêm gồm cả quãng vòng thêm.
- **Chấp nhận gì:** thời gian ở mỗi nơi được rút xuống mức `short` (đã có `allow_shrink`) nên có thể ngắn hơn thường; thẻ ghi rõ "thời gian ở mỗi nơi: ngắn hơn bình thường". Kế hoạch này không đảm bảo đa dạng.
- **Giới hạn:** vẫn tuân thủ `per_day_max`, ρ và `validate`, nên không nhồi mỗi ngày kín 100%.
- **Dùng phần thời gian dư:** sau khi cắt, nếu `room().more > 0` thì có thể gợi ý thêm nơi từ nhóm dự phòng (chỉ khi người dùng bấm, có validate), đúng ý "dùng thời gian tiết kiệm để đi thêm nơi".
- **Hiện trên thẻ:** tổng phút di chuyển, % thời gian ở nơi (`D`), số nơi giữ, chênh so với "Giữ tất cả".

---

### 5.4 Hai kế hoạch bổ sung

- **🧰 Giữ tất cả** (thu gọn): toàn bộ danh sách người dùng chọn, kèm kết luận thật ("Mong manh" hoặc không xác nhận được, và quy tắc nào vi phạm). Giữ cho người dùng quyền quyết định, đúng nguyên tắc không bỏ lặng lẽ.
- **⚖️ Cân bằng** (`balanced`): chỉ xuất hiện khi hai kế hoạch trên trùng ≥ 85% và cùng cách chia ngày. Tối đa tổng ba mục tiêu đã chuẩn hóa (chi phí thấp, trải nghiệm cao, di chuyển ít). Điền chỗ trống để người dùng luôn có đủ lựa chọn khác nhau.

### 5.5 Ví dụ minh họa (giả định, chưa đo)

2 ngày, chọn 12 nơi (3 nơi `must`), nhịp cân bằng, 4 mong muốn.

| | 💰 Tiết kiệm | ✨ Trải nghiệm | 🧭 Gọn tuyến | 🧰 Giữ tất cả |
|---|---|---|---|---|
| Số nơi giữ | 8 | 8 | 10 | 12 |
| Mong muốn đáp ứng | 3/4 | 4/4 | 3/4 | 4/4 |
| Chi phí đã biết | thấp nhất | cao nhất | trung bình | cao nhất |
| Di chuyển | trung bình | nhiều | **ít nhất** | nhiều |
| Thời gian ở mỗi nơi | bình thường | đủ | ngắn hơn | — |
| Độ vững | Khả thi | Khả thi | Khả thi | Mong manh |

Điểm cần thấy: ba kế hoạch khác nhau ở **nơi nào còn lại**, mỗi cái ghi rõ cái giá phải trả.

### 5.6 Nói thẳng "không thể đi hết" và đặt ba kế hoạch theo điều người dùng đã cho biết

#### A. Thông báo: chỉ nói "không thể" khi đã kiểm chứng

Ước tính của Decision (`needed` so với `available`) có thể lệch với Planning, nên ba mức câu chữ khác nhau:

| Tình huống | Mức | Câu nói | Hiện ở |
|---|---|---|---|
| `needed > available` theo ước tính Decision, chưa dựng lịch | "có vẻ không đủ" | "Bạn đã chọn 14 nơi, cần khoảng 16 giờ mà chuyến có khoảng 15 giờ. Có vẻ không đi hết được." | Thanh "Đã chọn" (Decision) |
| Planning dựng "Giữ tất cả" và `validate` báo lỗi vật lý (giờ mở cửa, hết khung ngày) | **"không thể"** | "Không thể đi hết 14 nơi này: ngày 2 vượt khung ngày 90 phút. Mình đưa 3 lịch theo 3 hướng, dựa trên điều bạn đã cho mình biết." | Bước Lịch trình |
| "Giữ tất cả" hợp lệ nhưng độ vững "Mong manh" | "rất chặt" | "Đi hết được nhưng rất sát giờ: trễ 15 phút là mất 1 nơi. Bạn muốn giữ hay xem 3 lịch thoải mái hơn?" | Bước Lịch trình |

Mỗi câu phải có: (1) hai con số cần/có, (2) quy tắc nào chặn, (3) hướng giải quyết là ba lịch. Không bao giờ dùng "không thể" cho một ước tính chưa qua `validate`.

#### B. Ba kế hoạch ứng với điều người dùng đã nói (câu hỏi, chip, hồ sơ)

Nguồn: Trip State, mỗi giá trị có `source` (người dùng nói / chip / suy ra / hồ sơ) và bằng chứng. Hai quy tắc giữ nguyên từ hệ thống: lời người dùng trong chuyến này thắng hồ sơ, và `unknown` ≠ không thích.

Từ tín hiệu, quyết định **kế hoạch nào đứng đầu** và **câu "vì sao"** trên thẻ:

| Tín hiệu người dùng đã cho biết | Đẩy lên đầu | Câu "vì sao" (ví dụ) |
|---|---|---|
| Có `budget_vnd`, hoặc đã chọn mục tiêu "tiết kiệm" (`set_objective`) | 💰 Tiết kiệm | "Vì bạn đặt ngân sách 1,5 triệu." |
| Nhịp "thong thả"; hoặc novelty "thử mới"; hoặc mục đích chụp ảnh / chill; hoặc nêu ≥ 3 mong muốn cụ thể | ✨ Trải nghiệm tốt nhất | "Vì bạn chọn nhịp thong thả và muốn thử nơi mới." |
| Nhịp "đi nhiều"; hoặc có `max_leg_min` thấp; hoặc đã khai say xe / đau chân; hoặc chuyến ≤ 2 ngày | 🧭 Gọn tuyến | "Vì bạn muốn đi nhiều nơi và ít ngồi xe." |
| Chưa có tín hiệu nào | Không đoán: xếp theo độ vững | "Mình chưa biết bạn ưu tiên gì nên xếp theo độ vững." kèm 3 nút "Mình ưu tiên: Tiết kiệm / Trải nghiệm / Ít đi lại" (gọi `set_objective`) |
| Hai tín hiệu mâu thuẫn (ngân sách chặt nhưng muốn thử mới) | Hai kế hoạch đứng đầu | Nói rõ cái giá của từng hướng |

- Tín hiệu có `source = suy ra` hoặc `hồ sơ` nhẹ hơn lời người dùng; không suy đoán tuổi, giới tính (đúng nguyên tắc sản phẩm). Dữ liệu sức khỏe chỉ dùng trong phiên.
- Mỗi thẻ ghi những điều của chính người dùng mà kế hoạch đó đáp ứng, không phải mô tả chung chung: 💰 "trong ngân sách ≤ 1,5 triệu", ✨ "đáp ứng 4/5 mong muốn bạn nêu, chưa đáp ứng: săn mây", 🧭 "tiết kiệm 70 phút ngồi xe cho 2 nơi nữa".
- Cách làm: cùng kiểu với `objectives.choose()` hiện có (đọc `budget_vnd`, nhịp, dự báo mưa, sở thích từ `trip_context`), thêm một hàm xếp thứ tự theo bảng trên. Tất định, bảng nằm trong `planning.yaml`, không gọi model.

---

### 5.7 Chỉnh một kế hoạch đã chọn (người dùng thích nhưng muốn đổi vài nơi)

Người dùng hiếm khi chấp nhận nguyên một kế hoạch. Luồng chỉnh phải cho thấy **cái giá của từng thay đổi trước khi áp dụng**, và không phá phần họ đã hài lòng.

#### Đã có sẵn trong code (`planning/session.py`, `repair.py`)

`pick_variant`, `move_place`, `reorder`, `drop_place` (kèm lý do: xa / đông / đắt / không thích / đã đi), `add_from_backup`, `swap`, `lock_slot` / `unlock`, `set_objective`, `set_pace`. Khôi phục một nơi đã bỏ chính là `move_place` vào một ngày (`_place` gỡ nó khỏi `dropped`). `repair_day` chỉ sắp xếp lại ngày bị chạm và phạt việc xáo trộn nơi đã có ("không xáo lịch âm thầm"); nơi đã khóa không rời ngày của nó.

#### Còn thiếu và đề xuất

| Việc người dùng muốn | Hiện thiếu | Đề xuất |
|---|---|---|
| **Thêm lại một nơi đã bị bỏ** | Chỉ áp dụng được rồi mới biết lịch hỏng | **Xem trước cái giá:** "+45 phút ngày 2, độ vững Khả thi → Mong manh, vẫn hợp lệ / không hợp lệ vì giờ đóng cửa". Dùng lại `preview` / lịch ngầm đang có |
| Thêm nơi mà lịch không đủ chỗ | Không có gợi ý thay thế | **Tạo chỗ trống:** "Muốn thêm A thì bỏ B (ít hợp bạn nhất, tiết kiệm 60 phút)". Chọn tập nhỏ nhất cần bỏ để `validate` sạch, dùng lại bộ chọn ở mục 4, không bỏ nơi đã khóa / bắt buộc |
| **Đổi một nơi lấy nơi khác** | `swap` chỉ nhận nơi trong nhóm dự phòng (`ctx.backup_ids`) | Cho `swap` nhận cả nơi **bị kế hoạch bỏ** và nơi người dùng đã chọn; xếp ứng viên theo cùng loại / gần / hợp khung giờ của ngày đó |
| **Bỏ một nơi** | Thời gian trống không được dùng | Hiện số phút trống và hỏi "dùng thời gian này thêm một nơi gần đó?" (`add_from_backup`, dựa trên `room().more`) |
| Giữ nơi mình thích | Phải tự khóa từng nơi | Nơi người dùng khôi phục hoặc khóa thành `must`, nơi họ bỏ kèm lý do thành "loại ra" cho lần tối ưu lại |
| Sau vài lần chỉnh | Phải tự dò | Nút **"Tối ưu lại quanh lựa chọn của tôi"**: chạy lại bộ chọn mục 4 với `must` = nơi đã khôi phục / khóa, `banned` = nơi đã bỏ, các nơi còn lại tự thích nghi |
| So với lúc đầu | Không thấy tổng thể | Thanh chênh lệch luôn hiện, "so với danh sách bạn chọn": ±số nơi, ±phút di chuyển, ±chi phí, mong muốn đáp ứng (mở rộng bảng `comparison` đã có trong `variants.py`) |

#### Quy tắc

1. Mọi chỉnh sửa vẫn qua `validate`. Thay đổi làm lịch hỏng được **hiển thị kèm quy tắc vi phạm nhưng không xác nhận được** (bất biến hiện có).
2. Không xáo lịch âm thầm: `repair_day` giữ thứ tự cũ của các nơi đã có.
3. **Bỏ do kế hoạch và bỏ do người dùng là hai việc khác nhau.** `pick_variant` hiện giữ các chỉnh sửa theo mã nơi (`assignment` / `dropped` / `locked`) khi đổi kế hoạch. Nếu ghi các nơi bị *bộ chọn* bỏ vào `State.dropped`, chúng sẽ dính sang kế hoạch khác. Cách an toàn: mỗi kế hoạch mang `dropped_by_plan` riêng; chỉ khi người dùng `pick_variant` mới đổi thành trạng thái phiên, và đổi sang kế hoạch khác thì bỏ phần `dropped_by_plan` cũ nhưng giữ những gì người dùng tự bỏ.
4. Các lần bỏ do bộ chọn không tính vào `rethink_drops` (giới hạn bỏ nhiều trong một lượt trợ lý).
5. Lý do bỏ của người dùng (xa / đông / đắt / không thích) tiếp tục cập nhật Session Profile như hiện nay, để lần tối ưu lại thấy rõ ý họ.

---

## 6. Better overload warning in Decision (cheap, no Planning call)

Decision's `select` is already the slowest step in the 14-day / 56-place probe (≈ 14.5 s vs 1.2 s for Planning), so the check must stay O(n) and must not call Planning.

1. **Show the numbers** that already exist: `needed`, `available`, `slack`, and a ratio. Levels reuse today's thresholds: `< 0.8` fine (the existing `fill_share`), `0.8–1.0` tight, `> 1.0` overloaded (existing `time` conflict), `> 1.35` infeasible (existing). Mostly a naming/UI change.
2. **Replace `removable[:2]` with a trim plan**: the smallest set of droppable places that brings `needed ≤ ρ·available`, chosen by `time_saved / regret` (knapsack-cover, greedy is fine). One click: `{"type": "drop_many", "place_ids": [...]}` (a new act; check what the act contract allows).
3. **Name the binding reason** (time / per_day / far_areas / time_windows / budget), the conflict ids already exist.
4. **Offer "Xem 3 lịch"** when level ≥ tight; it just calls the Planning composer in the background (same debounce as the existing "lịch ngầm" preview).
5. **Calibrate G7** once: run Decision `evaluate` and Planning `validate` over `config/eval_trips.yaml` with inflated selections and tabulate agreement. If Decision says "infeasible" but Planning finds a valid plan with shrunk visits (or the reverse), adjust `infeasible_ratio` or switch `needed` to the `short` estimate for a true lower bound. A confusion matrix is more convincing than a tuned constant.

---

## 7. Latency and long trips

- Fixture timings in `PLANNING_PERFORMANCE.md` (fake matrix, no Agent): 0.06 s for 28 places / 7 days, 0.93 s for 49 / 7, 1.19 s for 56 / 14. A naive composer is *k* schedule runs × 3 presets, so dense trips could take several seconds. Mitigations: (1) estimate-based batch drop before the first verify, (2) shared `trip.routes` across presets, (3) run the three presets in the background and stream them, with the revision check the preview already uses, (4) cap trim rounds (≈ 5) and report `profile_unavailable` instead of looping.
- Long trips: `PLANNING_PERFORMANCE.md` describes 7-day chunks (`chunk_days`, `chunk_assignments`) and a per-`order_day` route cache. **None of that is in the GitHub commit I read** (`173d81e` has `max_days: 7` and no `chunk_days`), so it must live in your local/shared checkout. Assuming it lands as described, run the composer **per chunk**, using the chunk assignment from Decision, so one overloaded week does not force drops in a light week; the budget check is already per day. The timings above also come from that unpushed work, so treat them as indicative.
- Everything stays deterministic and LLM-free: Agent never picks presets or drops places (consistent with the `proposal.py` guard: only `move_place` / `reorder`).

---

## 8. Output additions (small)

```text
variants[i]: preset, labels[], kept[], dropped[{place_id, reason, saved_min, saved_vnd?, regret}],
             metrics + {places, categories_covered, novelty_share, travel_share},
             delta_vs_selection {places, travel_min, cost_vnd}
overload:    {level, needed, available, binding, trim_plan[]}
```

`dropped[].reason` should reuse the session's existing `Drop.reason` so the restore flow and the dropped chips need no new state.

---

## 9. Evaluation (reuse what exists)

- **Fixtures:** `config/eval_trips.yaml` (30 trips) with the selection forced to 1.5×, 2×, 3× `per_day_max × days`, with and without a locked place; plus your 98-places / 14-days synthetic case as a regression ("today `ok=false`; after: ≥ 1 valid trimmed variant + a flagged keep-all").
- **Invariants (each a test):**
  - `must` never dropped; every shown-as-valid variant passes `validate`; kept ⊆ selection.
  - **Dominance (definitions in §5):** among valid variants, Economical has the lowest known cost (this test **fails today**, which is the point of G1), Routing has the most places and the lowest `T_travel`, Experience has the highest wish coverage among variants with no rushed visit (dwell ratio ≥ 0.9, valid with `allow_shrink=False`).
  - Monotone: a larger time budget never lowers kept utility.
  - **Honest wording (§5.6):** "không thể" is shown only when `validate` rejects keep-all; an estimate alone says "có vẻ không đủ". Card order follows the signals table; with no signals the order is by robustness and says so.
  - **Tweaks (§5.7):** a restore/swap that breaks `validate` is shown with its rule and cannot be confirmed; plan-made drops never leak into another variant on `pick_variant`; plan-made drops do not count toward `rethink_drops`.
  - Same input ⇒ same output.
- **Metrics:** share of overloaded cases with ≥ 1 valid variant; Decision-vs-Planning agreement (§6.5); variant distinctness; composer p50/p95 on the shared matrix cache. Report them as simulated (like the report's other numbers), not as user benefit.

---

## 10. Suggested order of work

| Step | Work | Why first |
|---|---|---|
| 0 | Test that exposes G1 (`low_cost` equal cost in all variants); decide whether `diverse` must outrank `low_cost` in `objective_order` | Free, shows the gap |
| 1 | Decision: trim plan + levels + numbers + binding reason (§6) | Biggest UX gain, no Planning change |
| 2 | Planning: `subset` parameter + skip bin in `assign_days` + three presets (§3–5, Method C) | Delivers the three plans |
| 3 | Place-level trim, Method A/B for refill, de-dup + `balanced` + `keep_all` | Makes plans sharp |
| 4 | UI cards, personalised order + "vì sao" line, honest "không thể" wording (§5.6); evaluation set; docs (`P3`/`P4`) | Finish and measure |
| 5 | Tweak flow: cost preview, make-room, wider `swap` pool, re-optimise around my choices (§5.7) | Lets users adjust a plan they mostly like |

## 11. Open questions for you

1. Should the three presets **replace** `choose()` only when overloaded, or always? (I'd say only when `time`/`per_day` conflicts or level ≥ tight.)
2. Is a per-travel-minute transport cost acceptable for "economical", or do you want real km from OSRM routes?
3. α (keep ≥ 70% of utility) and ρ (0.9): start values only; tune after a pilot.
4. Does the act contract allow a batch `drop_many`, or should it be several `drop` acts applied atomically?
5. Should "Chọn giúp phần còn lại" (listed in `OPEN_TASKS.md`) reuse this selector? It is the same "which subset" question.
6. For §5.6, which signals should move a plan to the top? The table is a first guess; confirm it (e.g. should a stated health signal such as say xe really favour 🧭?).
7. For §5.7, may `swap` accept any place from the user's own selection, not only the backup pool?
