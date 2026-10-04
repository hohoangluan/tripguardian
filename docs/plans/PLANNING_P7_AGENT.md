# Plan P7 — agent, guard, policy: one call per typed turn

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A free-text box on the Planning screen, like the one Place Decision already has: one message in, one agent call, a streamed `say`, and zero or more of the session's existing `act`s applied — grounded so the agent can never invent a place, a lodging candidate, a variant or a number that was not actually on screen or in the user's own words, and falling back to a dumb keyword policy when the model is slow, down or wrong. `POST .../turn` streams `say(delta|replace) · view · done · error` over SSE, exactly the event shape P6 already reserved for it.

**Architecture:** `agent.py`, `guard.py` and `policy.py` mirror `src/decision/agent.py`, `src/decision/guard.py` and `src/decision/policy.py` almost line for line — same `SayStream` incremental JSON-string extractor, same one-call-with-one-retry-on-a-whitespace-loop shape, same "quote must be real, alias must be real, a risky pick must be named" guard discipline. What differs is the vocabulary: Place Decision's agent only ever points at a place; Planning's agent points at a place, a day, a lodging candidate or a variant, so `guard.py` defines its own `Op` literal and its own alias namespace (`P#` places, `L#` lodging candidates, `V#` variants) instead of reusing Decision's. `engine.py` gains a `turn()` method that builds the prompt's fields and the alias table from the session's *current* laid-out `Schedule` (the same `results: list[DayResult]` `act()` already keeps per session), calls the agent, runs `guard()`, and then replays each produced action through the **existing** `self.act()` — so a turn can never do anything a chip click could not already do, and every action it applies gets exactly the same scope-correct relayout, locked-place protection and undo entry a chip click gets. No new state, no new act types, no new relayout path.

**Tech Stack:** Python 3.12, stdlib (`asyncio`, `re`, `json`), `pydantic` (already a dependency), `openai` async client via `corpus.llm` (already a dependency), `pytest`. No new dependency.

**Spec:** `docs/specs/PLANNING_SPEC.md` (§Vòng người dùng sửa và góp ý, §Guardrail, §API và web, §Giới hạn đã biết, bảng phase P7). Plan trước: `docs/plans/PLANNING_P6_SESSION.md` — **phải xong cả plan đó** (this plan calls `Engine.act`, `Engine._view`, `Engine._ensure_base`, `act_scope`, `Session`/`State`, `ActionError` unchanged; it adds to `engine.py`/`scope.py`/`server.py`/`__main__.py`/`settings.py` only, it does not touch their existing methods' signatures). Blueprint, read directly, not reimported (`src/decision` cannot be imported by `src/planning`, per `RULE.md` §2 and `PLANNING_P6_SESSION.md`'s own "Khác với spec" entry on this): `src/decision/agent.py`, `src/decision/guard.py`, `src/decision/policy.py`, `src/decision/engine.py`'s `turn()`/`_aliases`/`_fields`, `src/decision/server.py`'s `/turn` route, `src/decision/__main__.py`'s agent bootstrap. `src/corpus/llm/tasks.py`'s `DECISION_TURN` is the template for the new `PLANNING_TURN` task.

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh (`RULE.md` §0). Chuỗi hiển thị người dùng (`say`, policy's fallback text) tiếng Việt.
- Module chỉ giao tiếp qua public API (`__init__.py`). `planning` vẫn **không import `decision`** (RULE §2, như P6 đã chốt). `planning` **được** import `corpus.llm` (`AGENT`, `Task`) và `trip` (`contains`, `squash`) trực tiếp — đây là tiền lệ đã có: `src/decision/agent.py` và `src/decision/guard.py` làm đúng việc này, hai module đó không phải `decision`-domain nội bộ mà là hạ tầng dùng chung.
- Không thêm dependency vào `pyproject.toml`.
- Mọi bước tất định (RULE chung của dự án): khi một update cần một **permutation cụ thể** (`reorder_edge`), `guard.py` tự tính nó từ thứ tự hiện tại của ngày đó — không bao giờ để agent phát sinh một danh sách thứ tự.
- Physical constraint không nới: `guard.py` không cần tự kiểm nhóm `effort` của feature — `session.apply_act`'s `relax` đã ném `ActionError` cho feature nhóm đó (`PLANNING_P6_SESSION.md` Task 2); guard chỉ cần feature đó có tồn tại trong ontology, việc từ chối nới vật lý xảy ra đúng một chỗ như Guardrail bảng yêu cầu.
- Không xáo lịch âm thầm: `turn()` không tự viết lại `Schedule` — nó chỉ gọi `self.act(sid, action)` cho từng action đã qua guard, y hệt một chip click; scope, repair_day, undo entry đều đi qua đường có sẵn của P6.
- Thay đổi tối thiểu (`RULE.md` §4): `build.py`, `variants.py`, `objectives.py`, `robustness.py`, `backup.py`, `validate.py`, `route.py`, `days.py`, `schedule.py`, `lodging.py`, `places.py`, `travel.py`, `frame.py`, `model.py`, `session.py`, `repair.py`, `output.py` của P3–P6 **không đổi chữ ký** trong plan này. Mọi thứ mới nằm ở `guard.py`, `agent.py`, `policy.py` (mới), cộng các điểm nối tối thiểu trong `engine.py`, `scope.py`, `server.py`, `__main__.py`, `settings.py`, `config/planning.yaml`, `src/corpus/llm/tasks.py`, `src/corpus/llm/__init__.py`.
- File test mới dưới `tests/planning/`, tiền tố `test_planning_`; không tạo `tests/planning/__init__.py`. `tests/planning/plan_fixtures.py` (đã có từ P3-P6) cung cấp `CFG`, `FakeLive`, `fake_matrix`, `no_geocode`, `fake_lodging`, `sample_trip`, `small_trip` — dùng lại nguyên trạng, không sửa.
- Chạy test: `python -m pytest -q` ở gốc repo.
- Giờ trong code là phút sau nửa đêm; `day` trong act/API là chỉ số 0-based như `Day.index`. Alias hiển thị cho người (trong `say`, trong field text) dùng "Ngày N" 1-based.

## Khác với spec (đã chốt, ghi để khỏi tranh luận lại)

| Spec nói | Plan này làm | Vì sao |
|---|---|---|
| "Gõ chữ = một call agent → plan of acts → guard → cùng các act đó" (không định nghĩa hình dạng `TurnPlan`/op) | `Op = Literal["drop","move_day","reorder_edge","pick_lodging","lodging_near","pace","relax","variant","unmapped"]`, mỗi update là `{op, ref, value, quote}` | Spec để hình dạng này mở, như nó đã để mở cho P5 (lodging schema) và P6 (`State`/`apply_act`). 9 op phủ đúng các dòng của bảng "Agent quyết phần con người" cộng switch-variant; không phủ các act chỉ-chip (`add_from_backup`, `swap`, `lock_slot`, `unlock`, `set_day_window`, `set_lodging_budget`, `undo`, `redo`, `confirm`) vì không dòng nào trong bảng đó mô tả chúng đến từ câu tự do. |
| "'ngày 2 nhiều quá' → `drop_place` nơi có điểm xếp hạng Place Decision thấp nhất trong cụm xa nhất của ngày đó, hoặc hỏi một câu khi hai nơi sát điểm" | Agent tự chọn `ref` (một alias `P#`) từ FIELDS đã liệt kê mỗi nơi cùng ngày nó đang ở và phút di chuyển từ chỗ ở của riêng nó; `guard` không tự tính "cụm xa nhất" bằng Python — nó chỉ xác nhận `ref` là một alias có thật, đang có mặt trong lịch, chưa bị khoá. Khi FIELDS không đưa ra một lựa chọn rõ ràng (vd. mọi nơi trong ngày đều cách đều), prompt dạy agent để `updates` rỗng và `say` hỏi lại. | Đây chính là ranh giới "Agent chỉ hiểu câu tự do và giải thích; mọi thứ cần đúng là rule" (§Nguyên tắc 3): *con số đúng hay sai* (alias có thật không, `quote` có thật không, nơi đã khoá có bị động không) là rule; *chọn nơi nào trong số hợp lệ* là phần agent được giao, y như Decision's `guard.py` không tự tính "nơi nào hợp lý nhất để bỏ" — nó chỉ kiểm `place` có thật. Việc Python tự tính "cụm xa nhất, điểm thấp nhất" sẽ là một thuật toán mới, tất định, không theo tinh thần "Agent quyết phần con người" của chính bảng đó (nếu rule tự quyết hộ, bảng đã không cần liệt kê các dòng này là *agent* quyết). |
| "'sáng muốn cà phê trước' → `reorder` ngày đó, nêu cái giá nếu phá giờ mở của nơi khác" | Op `reorder_edge`, `value` là `"first"` hay `"last"`; `guard` tính permutation = đưa `ref` ra đầu (hoặc cuối) ngày hiện tại của nó, giữ thứ tự tương đối của các nơi còn lại, rồi gọi act `reorder` với permutation đó. "Nêu cái giá" không nằm trong `say` của turn này — nó đã có sẵn trong `diff`/`view` mà `act()` trả về (P6 `scope: "relayout"` kéo theo một `repair_day` có thể đổi giờ các nơi khác; UI tự hiện) | Giữ "mọi bước tất định" (Global Constraints): một permutation cụ thể từ agent sẽ không tất định (guided decoding có thể trả hai thứ tự khác nhau cho cùng một câu ở hai lần gọi). Chuyển "nêu cái giá" sang `diff`/`view` tránh agent phải tóm tắt một con số nó không tính ra, đúng guardrail "không bịa". |
| "'chỗ ở gần chợ đêm hơn' → đổi tâm vùng tìm → `lodging_near` lại → diff" | Op `lodging_near`, `value` = từ ngữ gốc chỉ khu vực; guard phát hành động `set_lodging(text=value)` — act đã có từ P6, geocode văn bản thành một điểm thủ công rồi đặt nó làm anchor, **không** tính lại trung tâm vùng tìm hay chạy lại `lodging_near(...)` để lấy một danh sách ứng viên mới quanh đó | `lodging.py` (P5) không đổi chữ ký trong plan này (Global Constraints); dựng một "tìm lại K ứng viên quanh một tâm mới" cần sửa `lodging.py`/`build.py`, không thuộc phạm vi P7 (agent/guard/policy). `set_lodging(text)` là act gần nhất đã có sẵn cho đúng ý "đặt chỗ ở theo một địa danh người dùng nói" — ghi vào Giới hạn đã biết: chưa có "tìm lại ứng viên quanh tâm mới", người dùng được một điểm neo thủ công đúng địa danh thay vì K lựa chọn mới. |
| "bỏ nhiều nơi qua nhiều lượt → dừng sửa lẻ, đề nghị quay về Place Decision chọn lại" | Chỉ trong `turn()` (không áp cho act do chip gửi): khi guard tạo ra một `drop` mới và `len(state.dropped) >= cfg.rethink_drops`, `turn()` **không** gọi `self.act()` cho action đó — nó bỏ qua, ghi log, và thay `say` bằng câu gợi ý quay lại Place Decision | Planning's `State`/`apply_act` không có cơ chế `Pending` (câu hỏi mở) như `decision.Session` có — xây một cơ chế `Pending` đầy đủ (state field mới, view field mới, luồng trả lời bằng chip) là việc lớn hơn nhiều so với phần còn lại của P7 và không có dòng spec nào khác cần nó. Giới hạn trong kênh `turn` (nơi có `say` để nói câu đó) là nơi duy nhất hành vi này có ý nghĩa; chip `drop_place` liên tiếp **không** bị chặn — ghi vào Giới hạn đã biết. |
| "'đổi hết đi' → không tự xoá; hỏi xác nhận, nêu hệ quả" | Không có op riêng cho việc này: prompt dạy agent rằng một yêu cầu không chỉ rõ nơi nào / rộng hơn một nơi một lượt thì trả `say` hỏi lại, `updates` rỗng — guard không cần thêm rule gì, vì không `ref` nào được tạo ra thì không có action nào được guard thông qua | Đúng hành vi "hỏi một câu" đã có sẵn trong guard hiện tại (một `say` không `updates` là kết quả hợp lệ, như Decision's turn vẫn trả lời khi `plan.updates == ()`) — không cần một op `confirm_all` giữ chỗ cho một hành vi không bao giờ tạo action. |
| "`place_live_status`..." (không liên quan P7) | — | ngoài phạm vi |

## Review Focus

Năm lớp input spec hàm ý nhưng dễ bị bỏ; mỗi dòng đã có test ở task sở hữu code:

1. **`drop` không nêu nơi nào, và mọi nơi trong ngày đó đều là `anchor`/`locked`** — mong đợi: `guard` vẫn cho qua alias agent chọn (guard không biết gì về locked), nhưng `Engine.act()`'s `apply_act` ném `ActionError("... is locked to its day")`; `turn()`'s vòng lặp áp action phải bắt lỗi đó, ghi log skip, **không** crash cả turn và vẫn phát `say`/`view`/`done`. → Task 7 (`test_an_action_a_later_action_in_the_same_turn_invalidates_is_skipped_not_fatal`, dùng một action nhắm một nơi đã bị action trước đó trong cùng turn khoá/bỏ).
2. **Hai lượt `drop` liên tiếp vượt `rethink_drops`** — mong đợi: lượt thứ N bị chặn, `say` là câu gợi ý quay lại Place Decision, state **không** đổi thêm (action không được áp), nhưng turn trước đó (dưới ngưỡng) vẫn áp bình thường. → Task 7 (`test_crossing_rethink_drops_in_a_turn_suggests_going_back_instead_of_dropping_again`).
3. **`reorder_edge` nhắm một nơi đã ở đúng đầu (hoặc cuối) ngày của nó** — mong đợi: `guard` vẫn trả về một `reorder` hợp lệ với permutation **không đổi** (không phải lỗi, không phải bị bỏ qua) — act đó chạy nhưng vô hại, `repair_day`'s phạt lệch bằng 0 cho đúng trật tự cũ. → Task 3 (`test_reorder_edge_on_a_place_already_at_that_edge_is_a_no_op_order`).
4. **Quote của agent không khớp nguyên văn tin nhắn (kể cả lệch một dấu câu)** — mong đợi: update đó bị `guard` bỏ, ghi log, không phải bị validate ở tầng `Engine.act()` (chặn sớm nhất có thể, như Decision's `contains(text, u.quote)` chặn ngay đầu vòng lặp). → Task 3 (`test_a_quote_not_actually_in_the_message_is_dropped`).
5. **Agent lỗi (timeout / JSON hỏng / không cấu hình) khi state đã có vài nơi `dropped` và người dùng gõ một từ khoá policy nhận ra ("xa quá") cùng tên một nơi đang hiển thị** — mong đợi: `policy()` áp đúng một `drop_place` dựa vào alias hiện có, `say` là câu cố định, và `turn()`'s "agent lỗi → policy" fallback hoạt động giống hệt luồng chính (cùng một `self.act()` loop, cùng SSE events). → Task 5 + Task 7 (`test_turn_falls_back_to_policy_when_the_agent_is_unavailable`).

## Cấu trúc file

| File | Việc |
|---|---|
| `src/corpus/llm/tasks.py` | thêm `PLANNING_OPS`, `PLANNING_TURN` (Task) |
| `src/corpus/llm/__init__.py` | export `PLANNING_TURN` |
| `config/planning.yaml` | thêm `first_token_s`, `total_s`, `rethink_drops` |
| `src/planning/settings.py` | thêm 3 trường trên vào `Settings` |
| `src/planning/guard.py` | mới: `Op`, `PlanUpdate`, `TurnPlan`, `Guarded`, `names_in`, `guard` |
| `src/planning/agent.py` | mới: `AgentError`, `SayStream`, `run_agent`, `gemma_stream` |
| `src/planning/policy.py` | mới: `policy`, `DONE`, `NONE` |
| `src/planning/scope.py` | thêm: `widest(scopes: list[str]) -> str` |
| `src/planning/engine.py` | `Engine.__init__` nhận `agent`; thêm `turn()`, `_turn_aliases`, `_turn_fields`, `_turn_screen_text` |
| `src/planning/server.py` | thêm route `POST .../turn`, SSE, mirror `decision/server.py` |
| `src/planning/__main__.py` | `serve`: dựng `agent` từ biến môi trường `AGENT_*`, giống `decision/__main__.py` |
| `tests/planning/test_planning_agent.py` | mới |
| `tests/planning/test_planning_guard.py` | mới |
| `tests/planning/test_planning_turn.py` | mới (engine.turn, end-to-end với agent giả) |
| `tests/planning/test_planning_server.py` | thêm test cho route `/turn` |

---

### Task 1: `PLANNING_TURN` task trong `corpus.llm`

**Files:**
- Modify: `src/corpus/llm/tasks.py` (thêm sau `DECISION_TURN`, dòng ~662)
- Modify: `src/corpus/llm/__init__.py`
- Test: `tests/test_llm_task.py` (thêm một test vào file đã có, không tạo file mới)

**Interfaces:**
- Produces: `PLANNING_TURN: Task` (import được từ `corpus.llm`), schema `{say: str, updates: [{op, ref, value, quote}]}`.

- [ ] **Step 1: Write the failing test**

Thêm vào cuối `tests/test_llm_task.py`:

```python
def test_planning_turn_renders_with_every_field():
    from corpus.llm import PLANNING_TURN
    text = PLANNING_TURN.render(features="noise: quiet|loud", days="Ngày 1: ...", variants="V1 | ...",
                                lodging="L1 | ...", text="bỏ chỗ này đi")
    assert "bỏ chỗ này đi" in text and "V1" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_task.py::test_planning_turn_renders_with_every_field -v`
Expected: FAIL with `ImportError: cannot import name 'PLANNING_TURN'`

- [ ] **Step 3: Write minimal implementation**

In `src/corpus/llm/tasks.py`, right after the `DECISION_TURN` task (after its closing `)` around line 662), add:

```python
PLANNING_OPS = ["drop", "move_day", "reorder_edge", "pick_lodging", "lodging_near", "pace", "relax", "variant",
                "unmapped"]

PLANNING_TURN = Task(
    name="planning_turn",
    role=AGENT,
    max_tokens=700,
    temperature=0.2,
    parallel=4,
    # `say` first: the server streams it before the updates arrive (src/planning/agent.py).
    schema={
        "type": "object",
        "properties": {
            "say": {"type": "string"},
            "updates": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": PLANNING_OPS},
                    "ref": {"type": "string"},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["op", "ref", "value", "quote"],
                "additionalProperties": False,
            }},
        },
        "required": ["say", "updates"],
        "additionalProperties": False,
    },
    prompt="""You help a traveller edit a day-by-day itinerary for a trip to Đà Lạt, Vietnam. DAYS lists every place
already in the plan grouped by day (alias P1, P2, ...), with how far it is from today's lodging. VARIANTS lists the
2-3 plan options on screen (alias V1, V2, ...). LODGING lists the lodging candidates on screen (alias L1, L2, ...).
In this turn: understand the user's latest message, turn what it asks into updates, and reply.

`say` (Vietnamese): 1-2 short sentences, warm but not chummy, "mình" for yourself and "bạn" for the user, no slang,
no emoji. Say what you changed or understood, using only names and numbers from DAYS / VARIANTS / LODGING or the
user's own message. If the request names no clear place, day or candidate, or asks for something bigger than one
change (e.g. "đổi hết đi"), do not guess -- ask a short clarifying question instead and leave updates empty.

`updates`: one entry per request in the message.
- drop: the user does not want `ref` (a P# place) in the plan; value = the reason if stated: far | crowded | pricey
  | dislike | visited, else "". If they mean a whole day ("ngày 2 nhiều quá") without naming a place, pick the P#
  in DAYS for that day that is farthest from the lodging and not already locked -- unless two are close enough that
  you are not sure, in which case ask instead (empty updates).
- move_day: move `ref` (a P# place) to a different day; value = the day number as the user said it ("2" for "ngày 2").
- reorder_edge: put `ref` (a P# place) first or last within its own day; value = "first" or "last".
- pick_lodging: the user wants `ref` (an L# lodging candidate) as the stay; value = "". Only use this when the
  user clearly means one of the candidates actually listed in LODGING.
- lodging_near: the user wants the lodging near a place or area they name; ref = "", value = that place or area in
  their own words.
- pace: the user wants to go slower, more relaxed, or pack in more stops; value = slow | normal | packed.
- relax: the user is fine with `ref` (a P# place) despite a constraint they set earlier (e.g. stairs); value = the
  feature id from FEATURES. Only use this for a place clearly named.
- variant: the user wants a different plan option already on screen (`ref` = a V# alias); value = "". Only use this
  when the user clearly means one of the options actually listed in VARIANTS.
- unmapped: a request none of the above fits; ref = "", value = the user's words.
- quote: the exact words from the user's message that support the update, copied, not paraphrased.
- When unsure, leave it out. Never invent a place, a day, a candidate or a plan option.

FEATURES (id: values)
{features}

DAYS (day | alias | name | minutes from lodging)
{days}

VARIANTS (alias | objective | score summary)
{variants}

LODGING (alias | name | price)
{lodging}

USER MESSAGE:
{text}""",
)
```

- [ ] **Step 4: Export it**

In `src/corpus/llm/__init__.py`:

```python
from .roles import AGENT, EXTRACTOR, JUDGE, Role
from .tasks import (ASR_CHECK, DECISION_TURN, PLACE_FILTER, PLACE_QC, PLACE_VIDEO_FILTER, PHOTO_OBSERVE, PHOTO_VERIFY,
                    PLACE_VIDEO_VERIFY, PLANNING_TURN, REVIEW_OBSERVE, REVIEW_VERIFY,
                    TRIP_TURN, VIDEO_FILTER, VIDEO_OBSERVE, VIDEO_VERIFY, Task)

__all__ = ["AGENT", "ASR_CHECK", "DECISION_TURN", "EXTRACTOR", "JUDGE", "PLACE_FILTER", "PLACE_QC", "PLACE_VIDEO_FILTER", "PHOTO_OBSERVE", "PHOTO_VERIFY", "PLACE_VIDEO_VERIFY",
           "PLANNING_TURN", "REVIEW_OBSERVE", "REVIEW_VERIFY", "Role", "TRIP_TURN", "Task", "VIDEO_FILTER", "VIDEO_OBSERVE", "VIDEO_VERIFY"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_task.py -v`
Expected: PASS, all tests in the file green

- [ ] **Step 6: Commit**

```bash
git add src/corpus/llm/tasks.py src/corpus/llm/__init__.py tests/test_llm_task.py
git commit -m "feat(corpus/llm): planning_turn task, the prompt a typed turn calls"
```

---

### Task 2: Settings — `first_token_s`, `total_s`, `rethink_drops`

**Files:**
- Modify: `config/planning.yaml`
- Modify: `src/planning/settings.py`
- Test: `tests/planning/test_planning_settings.py` (file exists; add to it)

**Interfaces:**
- Produces: `Settings.first_token_s: float`, `Settings.total_s: float`, `Settings.rethink_drops: int`.

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_planning_settings.py`:

```python
def test_turn_settings_are_loaded():
    from planning.settings import load
    cfg = load()
    assert cfg.first_token_s > 0 and cfg.total_s > cfg.first_token_s and cfg.rethink_drops > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_settings.py -v`
Expected: FAIL with `TypeError: Settings.__init__() got an unexpected keyword argument` (yaml has fields the dataclass does not) -- or an `AttributeError` once the yaml keys below are added without the dataclass fields. Add the yaml first so the failure is the clean `AttributeError`.

- [ ] **Step 3: Write minimal implementation**

In `config/planning.yaml`, append after the P6 `# Sessions (P6, ...)` block:

```yaml
# Agent turn (P7, docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp ý). Same shape as config/decision.yaml.
first_token_s: 6.0            # the first streamed token must arrive by this long, or the turn falls back to policy
total_s: 20.0                 # the whole answer must arrive by this long
rethink_drops: 4              # dropping this many places in one planning session: a turn's next drop is refused,
                               # the user is told to go back to Place Decision instead (not a chip-level limit)
```

In `src/planning/settings.py`, add three fields to the `Settings` dataclass, right after `decision_url: str`:

```python
    decision_url: str
    first_token_s: float
    total_s: float
    rethink_drops: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_settings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/planning.yaml src/planning/settings.py tests/planning/test_planning_settings.py
git commit -m "feat(planning): settings for the agent turn's timeout and rethink threshold"
```

---

### Task 3: `guard.py` — aliases, grounding, deterministic reorder

**Files:**
- Create: `src/planning/guard.py`
- Test: `tests/planning/test_planning_guard.py`

**Interfaces:**
- Consumes: nothing from earlier planning tasks (pure, no imports from `planning.*` except `trip.contains`/`squash` and `corpus.ontology.load`).
- Produces: `Op` (literal), `PlanUpdate`, `TurnPlan` (pydantic models, mirrors `decision.guard`), `Guarded` (dataclass: `actions: list[dict]`, `say: str`, `log: list[str]`), `names_in(text, name) -> bool`, `guard(plan, text, aliases, day_order, screen_text) -> Guarded`.
  - `aliases: dict[str, dict]` — `"P1" -> {"kind": "place", "id", "name", "day": int}`, `"L1" -> {"kind": "lodging", "id", "name"}`, `"V1" -> {"kind": "variant", "id", "label"}`.
  - `day_order: dict[int, list[str]]` — day index -> place ids in that day's **current** order (for `reorder_edge`).

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_planning_guard.py`:

```python
from planning.guard import PlanUpdate, TurnPlan, guard, names_in

ALIASES = {
    "P1": {"kind": "place", "id": "a", "name": "Đồi Chè Cầu Đất", "day": 0},
    "P2": {"kind": "place", "id": "b", "name": "Quán Mộc Lan Viên", "day": 0},
    "P3": {"kind": "place", "id": "c", "name": "Thác Datanla", "day": 1},
    "L1": {"kind": "lodging", "id": "h1", "name": "Homestay Mây"},
    "V1": {"kind": "variant", "id": "v1", "label": "Ít di chuyển"},
}
DAY_ORDER = {0: ["a", "b"], 1: ["c"]}


def plan(*updates, say="Mình đã cập nhật."):
    return TurnPlan(say=say, updates=tuple(PlanUpdate(op=o, ref=r, value=v, quote=q) for o, r, v, q in updates))


def test_names_in_full_or_last_two_words():
    assert names_in("bỏ cầu đất đi", "Đồi Chè Cầu Đất")
    assert not names_in("bỏ đồi chè", "Đồi Chè Cầu Đất")


def test_drop_does_not_require_the_name_in_the_quote():
    text = "ngày 1 nhiều quá"
    g = guard(plan(("drop", "P2", "", "ngày 1 nhiều quá")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "drop_place", "place": "b", "reason": None}]


def test_move_day_resolves_the_one_based_day_the_user_said():
    text = "chuyển Datanla sang ngày 1"
    g = guard(plan(("move_day", "P3", "1", "chuyển Datanla sang ngày 1")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "move_place", "place": "c", "day": 0}]


def test_reorder_edge_moves_the_place_to_the_front_keeping_the_rest_in_order():
    text = "muốn Lan Viên đi trước"
    g = guard(plan(("reorder_edge", "P2", "first", "muốn Lan Viên đi trước")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "reorder", "day": 0, "order": ["b", "a"]}]


def test_reorder_edge_on_a_place_already_at_that_edge_is_a_no_op_order():
    text = "Cầu Đất đi trước nhé"
    g = guard(plan(("reorder_edge", "P1", "first", "Cầu Đất đi trước nhé")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "reorder", "day": 0, "order": ["a", "b"]}]


def test_pick_lodging_and_variant_need_the_name_in_the_quote():
    g = guard(plan(("pick_lodging", "L1", "", "chọn luôn")), "chọn Homestay Mây luôn", ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "pick_lodging", "id": "h1"}]
    bad = guard(plan(("pick_lodging", "L1", "", "chọn luôn")), "chọn luôn", ALIASES, DAY_ORDER, "")
    assert bad.actions == [] and len(bad.log) == 1


def test_lodging_near_free_text_needs_no_alias():
    g = guard(plan(("lodging_near", "", "chợ đêm Đà Lạt", "gần chợ đêm hơn")), "gần chợ đêm hơn", ALIASES,
              DAY_ORDER, "")
    assert g.actions == [{"type": "set_lodging", "text": "chợ đêm Đà Lạt"}]


def test_relax_needs_a_known_feature_and_the_place_named():
    g = guard(plan(("relax", "P1", "steep_or_stairs", "Cầu Đất có bậc thang cũng được")),
              "Cầu Đất có bậc thang cũng được", ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "relax", "place_id": "a", "feature": "steep_or_stairs"}]
    bad = guard(plan(("relax", "P1", "not_a_feature", "bậc thang cũng được")), "bậc thang cũng được", ALIASES,
               DAY_ORDER, "")
    assert bad.actions == []


def test_a_quote_not_actually_in_the_message_is_dropped():
    g = guard(plan(("drop", "P1", "", "không có câu này")), "chào bạn", ALIASES, DAY_ORDER, "")
    assert g.actions == [] and len(g.log) == 1


def test_unknown_alias_or_unmapped_is_dropped_without_an_action():
    text = "P9 bỏ đi, nhạc nhẹ chút"
    g = guard(plan(("drop", "P9", "", "P9 bỏ đi"), ("unmapped", "", "nhạc nhẹ chút", "nhạc nhẹ chút")), text,
              ALIASES, DAY_ORDER, "")
    assert g.actions == [] and len(g.log) == 1  # the unmapped update logs nothing bad, drop P9 does


def test_say_with_an_unseen_number_is_replaced():
    # Planning's aliases, unlike Decision's, never carry a place outside the current plan -- so a say naming any
    # alias's own place is never a hallucination by itself; only a number nobody said or showed is.
    assert guard(plan(say="Còn 45 phút trống."), "bỏ đi", ALIASES, DAY_ORDER, "").say == ""
    assert guard(plan(say="Còn 45 phút trống."), "bỏ đi", ALIASES, DAY_ORDER, "dư 45 phút").say == "Còn 45 phút trống."
    assert guard(plan(say="Thử Thác Datanla nhé"), "bỏ đi", ALIASES, DAY_ORDER, "").say == "Thử Thác Datanla nhé"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'planning.guard'`

- [ ] **Step 3: Write minimal implementation**

Create `src/planning/guard.py`:

```python
"""Checks an agent TurnPlan before it reaches Engine.act (docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp
ý): quotes come from the message, aliases are on screen, a risky pick (lodging, variant) is named by the user.
Mirrors src/decision/guard.py in shape, not in import -- planning may not import decision (RULE.md §2)."""

from dataclasses import dataclass, field
from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict

from corpus.ontology import load
from trip import contains, squash

Op = Literal["drop", "move_day", "reorder_edge", "pick_lodging", "lodging_near", "pace", "relax", "variant",
            "unmapped"]
PLACE_OPS = {"drop", "move_day", "reorder_edge", "relax"}
NAMED_OPS = {"pick_lodging", "variant", "relax"}         # risky picks: the quote must name the target
REASONS = ("far", "crowded", "pricey", "dislike", "visited")
PACES = ("slow", "normal", "packed")


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PlanUpdate(Frozen):
    op: Op
    ref: str
    value: str
    quote: str


class TurnPlan(Frozen):
    say: str
    updates: tuple[PlanUpdate, ...] = ()


@dataclass
class Guarded:
    actions: list[dict]
    say: str
    log: list[str] = field(default_factory=list)


@cache
def _ontology():
    return load()


def names_in(text: str, name: str) -> bool:
    """The user named this place: its whole name, or its last two words (the distinctive part of most names)."""
    words = squash(name).split()
    return contains(text, name) or (len(words) >= 2 and contains(text, " ".join(words[-2:])))


def _reorder_edge(ref: dict, value: str, day_order: dict) -> dict | None:
    order = list(day_order.get(ref["day"], []))
    if ref["id"] not in order:
        return None
    rest = [i for i in order if i != ref["id"]]
    new = [ref["id"], *rest] if value == "first" else [*rest, ref["id"]] if value == "last" else None
    return {"type": "reorder", "day": ref["day"], "order": new} if new else None


def guard(plan: TurnPlan, text: str, aliases: dict[str, dict], day_order: dict[int, list[str]],
         screen_text: str) -> Guarded:
    log, actions = [], []
    for u in plan.updates:
        if not contains(text, u.quote):
            log.append(f"drop {u.op}: quote {u.quote!r} not in the message")
            continue
        ref = aliases.get(u.ref) if u.ref else None
        if u.ref and ref is None:
            log.append(f"drop {u.op}: unknown alias {u.ref!r}")
            continue
        if u.op in PLACE_OPS and (ref is None or ref["kind"] != "place"):
            log.append(f"drop {u.op}: needs a place")
            continue
        if u.op in NAMED_OPS and ref is not None and ref["kind"] != "variant" and not names_in(u.quote, ref["name"]):
            log.append(f"drop {u.op}: the user did not name {ref['name']!r}")
            continue
        if u.op == "drop":
            reason = u.value if u.value in REASONS else None
            actions.append({"type": "drop_place", "place": ref["id"], "reason": reason})
        elif u.op == "move_day":
            try:
                day = int(u.value.strip()) - 1
            except ValueError:
                log.append(f"drop move_day: bad day {u.value!r}")
                continue
            actions.append({"type": "move_place", "place": ref["id"], "day": day})
        elif u.op == "reorder_edge":
            act = _reorder_edge(ref, u.value, day_order)
            if act is None:
                log.append(f"drop reorder_edge: {u.value!r} on {ref['id']!r} has no order to build")
                continue
            actions.append(act)
        elif u.op == "pick_lodging":
            if ref is None or ref["kind"] != "lodging":
                log.append("drop pick_lodging: needs a lodging candidate")
                continue
            if not names_in(u.quote, ref["name"]):
                log.append(f"drop pick_lodging: the user did not name {ref['name']!r}")
                continue
            actions.append({"type": "pick_lodging", "id": ref["id"]})
        elif u.op == "lodging_near":
            if not u.value.strip():
                log.append("drop lodging_near: empty area")
                continue
            actions.append({"type": "set_lodging", "text": u.value.strip()})
        elif u.op == "pace":
            if u.value not in PACES:
                log.append(f"drop pace: unknown level {u.value!r}")
                continue
            actions.append({"type": "set_pace", "level": u.value})
        elif u.op == "relax":
            if u.value not in _ontology().features:
                log.append(f"drop relax: unknown feature {u.value!r}")
                continue
            actions.append({"type": "relax", "place_id": ref["id"], "feature": u.value})
        elif u.op == "variant":
            if ref is None or ref["kind"] != "variant":
                log.append("drop variant: needs a plan option")
                continue
            actions.append({"type": "pick_variant", "id": ref["id"]})
        elif u.op == "unmapped" and u.value.strip():
            log.append(f"note: {u.value.strip()}")
    say = plan.say.strip()
    why = _bad_say(say, f"{text} {screen_text}", aliases)
    if why:
        log.append(f"say replaced: {why}")
        say = ""
    return Guarded(actions, say, log)


def _bad_say(say: str, heard: str) -> str | None:
    """Unlike Decision's own `_bad_say`, there is no name check here: every alias `guard` is ever given (Task 7
    builds them from the session's current Schedule and lodging candidates) already names something genuinely in
    the user's plan, so a `say` naming a place is never by itself a hallucination -- only a number nobody said or
    showed is (a minute count, a price, a day number invented instead of read off screen)."""
    said = set(_NUM.findall(heard))
    extra = [n for n in _NUM.findall(say) if n not in said]
    return f"numbers {extra} not said or shown" if extra else None
```

Add `import re` to the top-level imports and `_NUM = re.compile(r"\d+")` as a module-level constant next to the other constants (`REASONS`, `PACES`), rather than compiling the pattern inside the function on every call.

Update the call site in `guard()` to match the new signature (it no longer takes `aliases`):

```python
    say = plan.say.strip()
    why = _bad_say(say, f"{text} {screen_text}")
    if why:
        log.append(f"say replaced: {why}")
        say = ""
    return Guarded(actions, say, log)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_guard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planning/guard.py tests/planning/test_planning_guard.py
git commit -m "feat(planning): guard -- grounds a turn's updates into real acts"
```

---

### Task 4: `agent.py` — one streamed call, with the whitespace-loop retry

**Files:**
- Create: `src/planning/agent.py`
- Test: `tests/planning/test_planning_agent.py`

**Interfaces:**
- Consumes: `planning.guard.TurnPlan`, `corpus.llm.AGENT`, `corpus.llm.PLANNING_TURN`.
- Produces: `AgentError`, `SayStream`, `run_agent(fields: dict, on_say, cfg, open_stream=gemma_stream) -> TurnPlan` (async).

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_planning_agent.py` (byte-identical in structure to `tests/decision/test_decision_agent.py`, swapped to Planning's module and schema):

```python
import asyncio
import json

import pytest

from planning.agent import AgentError, SayStream, run_agent
from planning.settings import load

CFG = load()
PLAN = {"say": "Mình đã bỏ Cầu Đất.", "updates": [{"op": "drop", "ref": "P1", "value": "far", "quote": "xa"}]}


def stream_of(chunks, delay=0.0, first_delay=0.0):
    async def gen():
        await asyncio.sleep(first_delay)
        for c in chunks:
            await asyncio.sleep(delay)
            yield c
    return lambda fields: gen()


def chunks(obj, n=7):
    s = json.dumps(obj, ensure_ascii=False)
    return [s[i:i + n] for i in range(0, len(s), n)]


def test_say_stream_extracts_text_as_it_arrives():
    s = SayStream()
    got = "".join(s.feed(c) for c in chunks(PLAN, 3))
    assert got == "Mình đã bỏ Cầu Đất."


def test_run_agent_streams_say_and_returns_plan():
    said = []
    p = asyncio.run(run_agent({}, said.append, CFG, stream_of(chunks(PLAN))))
    assert "".join(said) == PLAN["say"] and p.updates[0].ref == "P1"


def test_errors_become_agent_error():
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, CFG, stream_of(['{"say": "x"'])))  # broken JSON
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, CFG, stream_of([" " * 40, " " * 40])))  # whitespace loop twice
    slow = type(CFG)(**{**CFG.__dict__, "first_token_s": 0.05})
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, slow, stream_of(chunks(PLAN), first_delay=0.3)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'planning.agent'`

- [ ] **Step 3: Write minimal implementation**

Create `src/planning/agent.py` (copied from `src/decision/agent.py`, swapping the import and the plan type; the streaming/looping/retry logic is identical on purpose -- the two turns share the same model role and the same guided-decoding failure modes):

```python
"""One agent call per typed message on the Planning screen (docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp
ý): prompt from the session's current laid-out trip, streamed `say`, typed plan. Same streaming guards as
src/decision/agent.py and src/trip/agent.py, kept here: modules only meet through public APIs."""

import asyncio
import json
import re
from typing import AsyncIterator, Callable

from pydantic import ValidationError

from corpus.llm import AGENT, PLANNING_TURN

from .guard import TurnPlan

LOOP_WS = 32  # guided decoding now and then emits whitespace until max_tokens; this many in a row means it started


class AgentError(Exception):
    """No usable plan in time; the turn falls back to the policy."""


class SayStream:
    """Pulls the "say" string out of a JSON object while it streams in."""

    def __init__(self):
        self.buf = ""
        self.sent = 0

    def feed(self, delta: str) -> str:
        self.buf += delta
        m = re.search(r'"say"\s*:\s*"', self.buf)
        if not m:
            return ""
        raw = self.buf[m.end():]
        end = _closing_quote(raw)
        raw = raw[:end] if end is not None else _trim_partial_escape(raw)
        try:
            text = json.loads('"' + raw + '"')
        except json.JSONDecodeError:
            return ""
        new, self.sent = text[self.sent:], max(self.sent, len(text))
        return new


def _closing_quote(raw: str) -> int | None:
    i = 0
    while i < len(raw):
        if raw[i] == "\\":
            i += 2
            continue
        if raw[i] == '"':
            return i
        i += 1
    return None


def _trim_partial_escape(raw: str) -> str:
    m = re.search(r"\\u[0-9a-fA-F]{0,3}$", raw)
    if m:
        return raw[:m.start()]
    tail = len(raw) - len(raw.rstrip("\\"))
    return raw[:-1] if tail % 2 else raw


def gemma_stream(fields: dict) -> AsyncIterator[str]:
    async def gen():
        client, model = AGENT.client()
        try:
            async for d in PLANNING_TURN.stream(client, model, **fields):
                yield d
        finally:
            await client.close()
    return gen()


class _Looping(AgentError):
    pass


async def run_agent(fields: dict, on_say: Callable[[str], None], cfg,
                    open_stream: Callable[[dict], AsyncIterator[str]] = gemma_stream) -> TurnPlan:
    """One call, or two when the first loops on whitespace; the second does not stream its say again."""
    deadline = asyncio.get_running_loop().time() + cfg.total_s
    try:
        return await _attempt(fields, on_say, cfg, open_stream, deadline)
    except _Looping:
        try:
            return await _attempt(fields, lambda s: None, cfg, open_stream, deadline)
        except _Looping as e:
            raise AgentError("output looped on whitespace twice") from e


async def _attempt(fields, on_say, cfg, open_stream, deadline) -> TurnPlan:
    loop = asyncio.get_running_loop()
    it = open_stream(fields).__aiter__()
    say, buf, first = SayStream(), [], True
    try:
        while True:
            timeout = cfg.first_token_s if first else deadline - loop.time()
            if timeout <= 0:
                raise AgentError(f"no complete answer in {cfg.total_s:.0f} s")
            try:
                delta = await asyncio.wait_for(it.__anext__(), timeout)
            except StopAsyncIteration:
                break
            first = False
            buf.append(delta)
            if new := say.feed(delta):
                on_say(new)
            tail = "".join(buf[-LOOP_WS:])[-LOOP_WS:]
            if len(tail) == LOOP_WS and not tail.strip():
                raise _Looping("whitespace loop")
    except asyncio.TimeoutError as e:
        raise AgentError("first token too slow" if first else "answer too slow") from e
    except AgentError:
        raise
    except Exception as e:  # openai errors, and httpx / OS errors a dropped stream raises unwrapped
        raise AgentError(f"{type(e).__name__}: {e}") from e
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass
    try:
        return TurnPlan.model_validate_json("".join(buf))
    except ValidationError as e:
        raise AgentError(f"bad plan: {str(e).splitlines()[0]}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planning/agent.py tests/planning/test_planning_agent.py
git commit -m "feat(planning): agent -- one streamed call per typed turn"
```

---

### Task 5: `policy.py` — the keyword fallback

**Files:**
- Create: `src/planning/policy.py`
- Test: `tests/planning/test_planning_policy.py`

**Interfaces:**
- Consumes: `planning.guard.names_in`.
- Produces: `policy(text: str, aliases: dict[str, dict]) -> tuple[list[dict], str]`, `DONE: str`, `NONE: str`.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_planning_policy.py`:

```python
from planning.policy import NONE, policy

ALIASES = {"P1": {"kind": "place", "id": "a", "name": "Đồi Chè Cầu Đất", "day": 0},
          "P2": {"kind": "place", "id": "b", "name": "Quán Mộc Lan Viên", "day": 0}}


def test_policy_matches_a_reason_and_a_named_place():
    actions, say = policy("Cầu Đất xa quá", ALIASES)
    assert actions == [{"type": "drop_place", "place": "a", "reason": "far"}]
    assert say


def test_policy_matches_pace_keywords():
    assert policy("đi chậm lại thôi", ALIASES)[0] == [{"type": "set_pace", "level": "slow"}]
    assert policy("đi nhiều nơi hơn nữa", ALIASES)[0] == [{"type": "set_pace", "level": "packed"}]


def test_policy_with_nothing_recognised_asks_to_use_the_chips():
    actions, say = policy("ừm", ALIASES)
    assert actions == [] and say == NONE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'planning.policy'`

- [ ] **Step 3: Write minimal implementation**

Create `src/planning/policy.py`:

```python
"""Fallback when the agent fails (docs/specs/PLANNING_SPEC.md §Guardrail: "Agent lỗi, timeout hoặc JSON hỏng ->
policy.py từ khóa làm lượt đó"). Mirrors src/decision/policy.py in shape, not in import."""

from trip import contains

from .guard import names_in

DROP_KEYWORDS = (("visited", ("di roi", "den roi", "toi roi", "da di")),
                 ("pricey", ("dat qua", "mac qua", "gia cao", "dat do")),
                 ("crowded", ("dong qua", "dong nguoi", "it nguoi", "vang hon")),
                 ("far", ("xa qua", "xa", "gan hon")),
                 ("dislike", ("khong thich", "chan")))
PACE_KEYWORDS = (("slow", ("cham lai", "thong tha", "it nho")), ("packed", ("nhanh len", "nhieu noi hon", "day hon")))
DONE = "Mình đã ghi nhận, lịch đã cập nhật."
NONE = "Mình chưa hiểu ý bạn. Bạn bấm trên thẻ hoặc gõ lại rõ hơn giúp mình nhé."


def policy(text: str, aliases: dict[str, dict]) -> tuple[list[dict], str]:
    reason = next((r for r, keys in DROP_KEYWORDS if any(contains(text, k) for k in keys)), None)
    place = next((a for a in aliases.values() if a["kind"] == "place" and names_in(text, a["name"])), None)
    if place and reason:
        return [{"type": "drop_place", "place": place["id"], "reason": reason}], DONE
    level = next((lv for lv, keys in PACE_KEYWORDS if any(contains(text, k) for k in keys)), None)
    if level:
        return [{"type": "set_pace", "level": level}], DONE
    return [], NONE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_policy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planning/policy.py tests/planning/test_planning_policy.py
git commit -m "feat(planning): policy -- keyword fallback when the agent is unavailable"
```

---

### Task 6: `scope.widest` — the one new helper `engine.turn` needs

**Files:**
- Modify: `src/planning/scope.py`
- Test: `tests/planning/test_planning_scope.py` (file exists; add to it)

**Interfaces:**
- Produces: `widest(scopes: list[str]) -> str` — the scope that implies the most rebuilding, among `NONE < RELAYOUT < VARIANT < LODGING_HOME < LODGING_FETCH`, for a turn's `diff` to report honestly when it applied more than one action.

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_planning_scope.py`:

```python
def test_widest_picks_the_scope_that_implies_the_most_rebuilding():
    from planning.scope import LODGING_FETCH, NONE, RELAYOUT, VARIANT, widest
    assert widest([]) == NONE
    assert widest([NONE, RELAYOUT]) == RELAYOUT
    assert widest([RELAYOUT, VARIANT, NONE]) == VARIANT
    assert widest([VARIANT, LODGING_FETCH]) == LODGING_FETCH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_scope.py -v`
Expected: FAIL with `ImportError: cannot import name 'widest'`

- [ ] **Step 3: Write minimal implementation**

In `src/planning/scope.py`, append:

```python
_ORDER = [NONE, RELAYOUT, VARIANT, LODGING_HOME, LODGING_FETCH]


def widest(scopes: list[str]) -> str:
    """The scope among `scopes` that implies the most rebuilding -- what a turn's diff reports when it applied more
    than one act (docs/specs/PLANNING_SPEC.md §Guardrail: "không xáo lịch âm thầm" -- the diff must say honestly
    how much a turn actually touched, not just the last action's own scope)."""
    return max(scopes, key=_ORDER.index, default=NONE)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_scope.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planning/scope.py tests/planning/test_planning_scope.py
git commit -m "feat(planning): scope.widest -- the honest scope of a multi-action turn"
```

---

### Task 7: `Engine.turn` — build fields, call the agent, replay through `act`

**Files:**
- Modify: `src/planning/engine.py`
- Test: `tests/planning/test_planning_turn.py`

**Interfaces:**
- Consumes: `planning.guard.guard`, `planning.agent.AgentError`, `planning.policy.policy`/`DONE`/`NONE`, `planning.scope.widest`, everything `Engine` already has (Task 6 of P6: `self.act`, `self._ensure_base`, `self._get`, `self._schedules`, `self.store.lock`).
- Produces: `Engine.__init__(..., agent: Agent | None = None)` (new keyword, default `None`, so every existing call site -- tests, `__main__.py` before Task 9 -- keeps working unchanged); `Engine.turn(sid: str, text: str, emit: Callable[[str, dict], None]) -> None`. `Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]`.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_planning_turn.py`:

```python
import pytest
from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, small_trip

from planning.engine import Engine
from planning.guard import TurnPlan, PlanUpdate
from planning.session import Store


def fake_agent(plan: TurnPlan):
    async def run(fields, on_say):
        on_say(plan.say)
        return plan
    return run


def engine(agent=None, budget=None):
    d, recs = small_trip(budget=budget)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False, agent=agent)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    return e, sid


def events(e, sid, text):
    out = []
    e.turn(sid, text, lambda ev, data: out.append((ev, data)))
    return out


def test_a_drop_update_runs_through_the_same_act_as_a_chip():
    plan = TurnPlan(say="Mình đã bỏ nơi đó.",
                    updates=(PlanUpdate(op="drop", ref="P2", value="far", quote="b xa quá"),))
    e, sid = engine(agent=fake_agent(plan))
    ev = events(e, sid, "b xa quá")
    kinds = [k for k, _ in ev]
    assert kinds == ["say", "view", "done"]
    assert e.load(sid)["view"]["state"]["dropped"][0]["place_id"] == "b"


def test_an_action_a_later_action_in_the_same_turn_invalidates_is_skipped_not_fatal():
    plan = TurnPlan(say="Mình đã cập nhật.",
                    updates=(PlanUpdate(op="drop", ref="P2", value="", quote="bỏ b"),
                            PlanUpdate(op="move_day", ref="P2", value="1", quote="bỏ b")))  # b no longer in the plan
    e, sid = engine(agent=fake_agent(plan))
    ev = events(e, sid, "bỏ b")
    assert [k for k, _ in ev] == ["say", "view", "done"]       # no exception escapes the turn
    assert e.load(sid)["view"]["state"]["dropped"][0]["place_id"] == "b"  # the first action still applied


def test_crossing_rethink_drops_in_a_turn_suggests_going_back_instead_of_dropping_again():
    e, sid = engine(agent=None)  # policy fallback: no named place, but we drop directly via act() to seed state
    for pid in ():
        pass
    # Seed rethink_drops - 1 drops via chip acts (not through turn), then let the Nth come from a turn.
    cfg_n = e.cfg.rethink_drops
    # small_trip only has 3 places; lower the threshold on this engine's cfg copy instead of dropping 4 real places.
    import dataclasses
    e.cfg = dataclasses.replace(e.cfg, rethink_drops=1)
    e.act(sid, {"type": "drop_place", "place": "a"})
    plan = TurnPlan(say="Mình đã bỏ nơi đó.", updates=(PlanUpdate(op="drop", ref="P3", value="", quote="bỏ c luôn"),))
    e.agent = fake_agent(plan)
    ev = events(e, sid, "bỏ c luôn")
    say = next(data["delta"] if "delta" in data else data.get("replace") for k, data in ev if k == "say")
    assert "Place Decision" in say or "chọn lại" in say
    assert e.load(sid)["view"]["state"]["dropped"] == [{"place_id": "a", "reason": None}]  # c was NOT dropped


def test_turn_falls_back_to_policy_when_the_agent_is_unavailable():
    e, sid = engine(agent=None)
    ev = events(e, sid, "a xa quá")
    assert [k for k, _ in ev] == ["say", "view", "done"]
    assert e.load(sid)["view"]["state"]["dropped"][0]["place_id"] == "a"


def test_turn_falls_back_to_policy_when_the_agent_raises():
    async def boom(fields, on_say):
        raise RuntimeError("agent host down")
    e, sid = engine(agent=boom)
    ev = events(e, sid, "a xa quá")
    assert [k for k, _ in ev] == ["say", "view", "done"]
    assert e.load(sid)["view"]["state"]["dropped"][0]["place_id"] == "a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_turn.py -v`
Expected: FAIL with `TypeError: Engine.__init__() got an unexpected keyword argument 'agent'`

- [ ] **Step 3: Write minimal implementation**

In `src/planning/engine.py`:

1. Add imports near the top, alongside the existing ones:

```python
from typing import Awaitable, Callable

from .agent import AgentError
from .guard import TurnPlan, guard
from .policy import DONE, NONE, policy
from .scope import widest
```

2. Add the `Agent` type alias right after the existing `_http_post` helper (near line 30):

```python
Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]
```

3. In `Engine.__init__`, add the `agent` parameter and store it:

```python
    def __init__(self, records: list[dict], cfg: Settings | None = None, live_cfg=None, store: Store | None = None,
                geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None,
                decision_url: str | None = None, http_post=None, background: bool = True,
                agent: "Agent | None" = None):
        self.by_id = {r["id"]: r for r in records}
        self.records = records
        self.cfg = cfg or load_settings()
        self.live_cfg = live_cfg or live.load_settings()
        self.store = store or Store(None)
        self.geocode_fn = geocode_fn
        self.matrix_fn = matrix_fn
        self.sun_fn = sun_fn
        self.lodging_fn = lodging_fn or live.lodging_near
        self.route_fn = route_fn or live.route_shape
        self.decision_url = decision_url or self.cfg.decision_url
        self.http_post = http_post or _http_post
        self.background = background
        self.agent = agent
        self._base: dict[str, _Base] = {}
        self._schedules: dict[str, list] = {}
```

4. Add `turn()` and its three helpers at the end of the class, after `confirm()`:

```python
    # ---------- turn (docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp ý) ----------

    def _turn_aliases(self, s: Session, base: _Base) -> dict[str, dict]:
        """P# for every place currently in the plan (from the active Schedule, or the first variant's own schedule
        before a pick), L# for every lodging candidate on screen, V# for every variant on screen."""
        out: dict[str, dict] = {}
        results = self._schedules.get(s.id, [None] * len(s.states))[s.position] if s.state.chosen_variant else None
        if results is None and base.variants:
            results = base.variants[0]["_results"]
        by_place = self._places_for(s, base)
        for day, r in enumerate(results or []):
            for pid in r.order:
                p = by_place.get(pid)
                if p is not None:
                    out[f"P{len(out) + 1}"] = {"kind": "place", "id": pid, "name": p.rec["identity"]["name"],
                                               "day": day}
        for c in self._offered_lodging(base, s.state):
            out[f"L{sum(1 for v in out.values() if v['kind'] == 'lodging') + 1}"] = {
                "kind": "lodging", "id": c["id"], "name": c["name"]}
        for v in base.variants:
            out[f"V{sum(1 for x in out.values() if x['kind'] == 'variant') + 1}"] = {
                "kind": "variant", "id": v["id"], "label": v["label"]}
        return out

    def _turn_day_order(self, s: Session, base: _Base) -> dict[int, list[str]]:
        results = self._schedules.get(s.id, [None] * len(s.states))[s.position] if s.state.chosen_variant else None
        if results is None and base.variants:
            results = base.variants[0]["_results"]
        return {i: list(r.order) for i, r in enumerate(results or [])}

    def _turn_fields(self, aliases: dict, text: str) -> dict:
        from corpus.ontology import load as load_ontology
        features = "\n".join(f"{f.id}: {'|'.join(f.values)}" for f in load_ontology().features.values())
        places = [(k, v) for k, v in aliases.items() if v["kind"] == "place"]
        by_day: dict[int, list[str]] = {}
        for k, v in places:
            by_day.setdefault(v["day"], []).append(f"{k} {v['name']}")
        days = "\n".join(f"Ngày {d + 1}: " + ", ".join(items) for d, items in sorted(by_day.items())) or "none"
        variants = "\n".join(f"{k} | {v['label']}" for k, v in aliases.items() if v["kind"] == "variant") or "none"
        lodging = "\n".join(f"{k} | {v['name']}" for k, v in aliases.items() if v["kind"] == "lodging") or "none"
        return {"features": features, "days": days, "variants": variants, "lodging": lodging, "text": text}

    def _turn_screen_text(self, fields: dict) -> str:
        return f"{fields['days']} {fields['variants']} {fields['lodging']}"

    def turn(self, sid: str, text: str, emit: Callable[[str, dict], None]) -> None:
        s = self._get(sid)
        base = self._ensure_base(sid)
        with self.store.lock(sid):
            aliases = self._turn_aliases(s, base)
            day_order = self._turn_day_order(s, base)
            fields = self._turn_fields(aliases, text)
            streamed: list[str] = []

            def on_say(d: str) -> None:
                streamed.append(d)
                emit("say", {"delta": d})

            try:
                if self.agent is None:
                    raise AgentError("no agent configured")
                import asyncio
                plan = asyncio.run(self.agent(fields, on_say))
                g = guard(plan, text, aliases, day_order, self._turn_screen_text(fields))
                actions, say, log = g.actions, g.say, g.log
            except AgentError as e:
                (actions, say), log = policy(text, aliases), [f"agent_fallback: {e}"]

            done, skipped, scopes = [], [], []
            drops_before = len(s.state.dropped)
            for action in actions:
                if action.get("type") == "drop_place" and drops_before + len(done) >= self.cfg.rethink_drops:
                    skipped.append(f"skip {action}: rethink_drops reached")
                    say = ("Bạn đã bỏ khá nhiều nơi trong lượt này. Có thể lịch đang không hợp với bạn ngay từ đầu "
                          "-- quay lại Place Decision để chọn lại nơi sẽ hợp hơn là bỏ từng chỗ một.")
                    continue
                try:
                    out = self.act(sid, action)
                    done.append(action)
                    scopes.append(out["diff"]["scope"])
                    s = self._get(sid)
                except ActionError as e:
                    skipped.append(f"skip {action}: {e}")

            say = say or (DONE if done else NONE)
            if say != "".join(streamed):
                emit("say", {"replace": say})
            s.log.append({"action": {"type": "turn", "text": text, "actions": done, "log": log + skipped}})
            self.store.save(s)
            emit("view", {"view": self._view(s), "diff": {"scope": widest(scopes)}})
            emit("done", {})
```

Note: `turn()` re-fetches `s = self._get(sid)` after every applied `self.act(...)` call because `act()` mutates and saves its own `Session` object in the `Store`; re-reading keeps `s.state.dropped` (used by the `rethink_drops` check) current across actions in the same turn.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_turn.py -v`
Expected: PASS

- [ ] **Step 5: Run the full planning suite to catch a signature-change regression**

Run: `python -m pytest tests/planning -q`
Expected: PASS (the new `agent` keyword on `Engine.__init__` defaults to `None`, so every existing construction in `tests/planning/test_planning_engine.py`, `test_planning_server.py` etc. is unaffected)

- [ ] **Step 6: Commit**

```bash
git add src/planning/engine.py tests/planning/test_planning_turn.py
git commit -m "feat(planning): Engine.turn -- one agent call, replayed through the existing act()"
```

---

### Task 8: `/turn` SSE route

**Files:**
- Modify: `src/planning/server.py`
- Test: `tests/planning/test_planning_server.py` (file exists; add to it)

**Interfaces:**
- Produces: `POST /api/planning/sessions/<id>/turn` streaming `text/event-stream`, same framing as `src/decision/server.py`'s `/turn`.

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_planning_server.py` (match whatever HTTP test harness the existing file already uses -- it already drives `do_POST`/`do_GET` against a running `ThreadingHTTPServer` on a free port, reuse that helper rather than re-deriving one):

```python
def test_turn_streams_say_view_and_done(client):  # `client` fixture already defined in this file for act/confirm tests
    sid = client.create()
    client.act(sid, {"type": "pick_variant", "id": client.variants(sid)[0]["id"]})
    events = client.turn(sid, "a xa quá")  # the running server's Engine has agent=None in this test fixture -> policy
    kinds = [e["event"] for e in events]
    assert kinds == ["say", "view", "done"]
```

If the file's existing fixture (`client`) has no `turn` helper yet, add one next to its existing `act`/`confirm` helpers, following the exact SSE-parsing shape `tests/decision/test_decision_server.py` already uses for Decision's own `/turn` test (read that file first to match the harness instead of inventing a second one).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_server.py -v`
Expected: FAIL (404 not found, or `AttributeError` on the missing `client.turn` helper)

- [ ] **Step 3: Write minimal implementation**

In `src/planning/server.py`:

1. Extend the `SUB` pattern to include `turn`:

```python
SUB = re.compile(BASE + r"/([0-9a-f]{12})/(act|confirm|variants|lodging|turn)")
MAX_TEXT = 1000
```

2. In `do_POST`, after the existing `confirm` branch and before the final `self._json(404, ...)`, add:

```python
            if m and m[2] == "turn":
                text = body.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                    return self._json(400, {"error": f"text must be 1-{MAX_TEXT} characters"})
                try:
                    engine.store.get(m[1])
                except KeyError:
                    return self._json(404, {"error": "no such session"})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                def emit(event: str, data: dict) -> None:
                    self.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()

                try:
                    engine.turn(m[1], text.strip(), emit)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    emit("error", {"message": "Máy chủ gặp lỗi, bạn thử lại nhé."})
                return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planning/server.py tests/planning/test_planning_server.py
git commit -m "feat(planning): POST .../turn, SSE -- the typed-message endpoint P6 reserved the shape for"
```

---

### Task 9: `python -m planning serve` wires the real agent

**Files:**
- Modify: `src/planning/__main__.py`

**Interfaces:**
- No new public interface; wires `planning.agent.run_agent` + `AGENT_*` env vars into the `Engine` the `serve` subcommand constructs, mirroring `src/decision/__main__.py` exactly.

- [ ] **Step 1: There is no new unit to test here**

This task is bootstrap wiring identical in shape to `decision/__main__.py`'s existing, already-tested pattern (`run_agent` and the env-var gate are both covered by Task 4's and Task 7's tests); a manual smoke check closes the loop (Step 3 below). Proceed straight to implementation.

- [ ] **Step 2: Write the implementation**

In `src/planning/__main__.py`, add the imports:

```python
from dotenv import load_dotenv

from .agent import run_agent
from .settings import ROOT
```

(`.settings.ROOT` already exists; `dotenv` is already a dependency, used the same way in `src/decision/__main__.py`.)

Change the `serve` branch of `main()`:

```python
    if args.cmd == "serve":
        load_dotenv(ROOT / ".env")
        store = Store(data_root() / "planning" / "sessions")
        cfg = load_settings() if "load_settings" in dir() else None  # see note below
        missing = [k for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL") if not os.environ.get(k)]
        agent = None
        if missing:
            print(f"warning: {', '.join(missing)} missing in .env: typed turns use the keyword fallback",
                 file=sys.stderr)
        else:
            from .settings import load as load_settings
            cfg = load_settings()
            agent = lambda fields, on_say: run_agent(fields, on_say, cfg)  # noqa: E731
        engine = Engine(load_records(), store=store, agent=agent)
        print(f"Planning: http://127.0.0.1:{args.port} (agent {os.environ.get('AGENT_MODEL') if agent else 'off'})")
        run_server(engine, port=args.port)
        return 0
```

Clean this up (the `cfg = load_settings() if "load_settings" in dir() else None` line is dead scaffolding from drafting -- delete it, the `else` branch below already imports and assigns `cfg` only when it is actually used):

```python
    if args.cmd == "serve":
        load_dotenv(ROOT / ".env")
        store = Store(data_root() / "planning" / "sessions")
        missing = [k for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL") if not os.environ.get(k)]
        agent = None
        if missing:
            print(f"warning: {', '.join(missing)} missing in .env: typed turns use the keyword fallback",
                 file=sys.stderr)
        else:
            from .settings import load as load_settings
            agent = lambda fields, on_say: run_agent(fields, on_say, load_settings())  # noqa: E731
        engine = Engine(load_records(), store=store, agent=agent)
        print(f"Planning: http://127.0.0.1:{args.port} (agent {os.environ.get('AGENT_MODEL') if agent else 'off'})")
        run_server(engine, port=args.port)
        return 0
```

- [ ] **Step 3: Manual smoke check**

Run: `python -m planning serve --port 8768` (no `.env` present, or `AGENT_*` unset)
Expected: prints `Planning: http://127.0.0.1:8768 (agent off)` and the server answers `GET /api/planning/sessions/<id>` for a session created via `POST`, same as before this task -- confirms the new `agent=` wiring did not break the existing bootstrap. Ctrl-C to stop.

- [ ] **Step 4: Commit**

```bash
git add src/planning/__main__.py
git commit -m "feat(planning): serve wires the real agent when AGENT_* is configured, like decision does"
```

---

### Task 10: Whole-turn golden test + self-review pass

**Files:**
- Test: `tests/planning/test_planning_golden.py` (file exists; add to it) or a new `tests/planning/test_planning_turn_golden.py` if the existing golden file is about `build`/CLI output specifically (check its current scope first; put this next to it only if it already mixes concerns, otherwise keep it in `test_planning_turn.py` from Task 7 as one more test).

**Interfaces:**
- No new production code; this task only adds coverage that exercises Tasks 1-9 together end to end and re-reads the spec with fresh eyes.

- [ ] **Step 1: Write a session-shaped end-to-end test**

Add to `tests/planning/test_planning_turn.py`:

```python
def test_a_full_turn_session_create_pick_turn_confirm():
    """One pass through everything this plan built: create, pick a variant, two turns (one agent op, one policy
    fallback), confirm -- the same path the web Itinerary screen (P8) will drive."""
    plan = TurnPlan(say="Mình đã đưa nơi đó lên đầu buổi sáng.",
                    updates=(PlanUpdate(op="reorder_edge", ref="P1", value="first", quote="a đi trước nhé"),))
    e, sid = engine(agent=fake_agent(plan))
    events(e, sid, "a đi trước nhé")
    e.agent = None  # second turn: agent "goes down", policy takes over
    events(e, sid, "b xa quá")
    out = e.confirm(sid)
    assert out["itinerary"] and "b" not in {i.get("place_id") for day in out["itinerary"] for i in day["items"]}
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `python -m pytest tests/planning/test_planning_turn.py -v`
Expected: FAIL first only if `confirm`'s output shape assumption (`day["items"]`, `i.get("place_id")`) does not match `output.build`'s real shape -- check `src/planning/output.py` / an existing `test_planning_output.py` assertion and adjust the assertion to match the real field names before treating this as a real failure. Once aligned: PASS.

- [ ] **Step 3: Self-review against the spec**

Re-read `docs/specs/PLANNING_SPEC.md`'s §Vòng người dùng sửa và góp ý and §Guardrail tables with this plan's "Khác với spec" table open side by side. Confirm:
- Every row of "Agent quyết phần con người" maps to an `Op` (Task 3's table in the prompt) or is explicitly listed as out of scope in "Khác với spec".
- Every row of §Guardrail that mentions the agent ("Agent lỗi, timeout hoặc JSON hỏng -> policy.py", "Không bịa ... số live phải mang source") has a test: the first is Task 7's `test_turn_falls_back_to_policy_when_the_agent_raises`; the second is Task 3's `test_say_with_unseen_numbers_or_names_is_replaced` (no live numbers are introduced by `turn()` itself, since `fields` only ever carries data already in `aliases`/`day_order`, themselves built from the session's own `Schedule` and `base.lodging_candidates` -- nothing agent-reachable is unlabelled live data).
- Run the full suite once more: `python -m pytest -q` at repo root. Expected: PASS, no regressions in `tests/decision`, `tests/trip`, `tests/corpus`.

- [ ] **Step 4: Update the spec's known limitations**

Add to `docs/specs/PLANNING_SPEC.md`'s §Giới hạn đã biết (append, do not reorder existing bullets):

```markdown
- `lodging_near` (câu nói tới một địa danh) đặt chỗ ở thủ công đúng địa danh đó (`set_lodging`), chưa tìm lại K ứng
viên chỗ ở quanh một tâm mới -- cần sửa `lodging.py`/`build.py`, để lại cho một phase sau.
- "Bỏ nhiều nơi qua nhiều lượt -> đề nghị quay về Place Decision" chỉ hoạt động trong kênh gõ chữ (`turn`); các act
`drop_place` gửi qua chip không bị chặn bởi `rethink_drops` -- Planning chưa có cơ chế `Pending`/câu hỏi mở như
`decision.Session` có.
```

- [ ] **Step 5: Commit**

```bash
git add tests/planning/test_planning_turn.py docs/specs/PLANNING_SPEC.md
git commit -m "test(planning): a full turn session end to end; record P7's known limitations in the spec"
```

---

## Execution note

`agent.py` (Task 4) is close enough to `decision/agent.py` that an implementer should open both side by side rather than retype from this plan's listing blind -- the plan's code block is the source of truth for what must exist, but diffing against `src/decision/agent.py` is the fastest way to catch a transcription slip (a missed `except json.JSONDecodeError` vs a bare `except`, for instance).
