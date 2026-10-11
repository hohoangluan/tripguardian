# Paired quiz-chat (song song 2 phase): implementation plan, ready to apply

User đã duyệt: quiz ↔ chat qua lại tự do, agent được hỏi ở paused nhưng chống trùng bằng state hiện tại.
Trạng thái: CHƯA implement (session bị chặn edit ngoài file này). Mọi patch dưới đã chốt nội dung, chỉ việc áp dụng.

## 0. Quy ước

- `phase="paused"`: tạm nghỉ quiz để chat, tiến độ quiz giữ nguyên trong `asked` + values. Không thêm field Meta nào khác.
- Resume = lượt `more` sẵn có (không thêm kind mới ngoài `pause`).
- Web không đọc `phase`; frontend tự giữ cờ `paused`.

## 1. Backend: `src/trip/domain/state.py` (1 dòng)

- `Meta.phase`: `Literal["chat", "quiz", "review"]` → `Literal["chat", "quiz", "review", "paused"]`, comment: `paused: quiz on hold, chatting with its progress kept`.

## 2. Backend: `src/trip/api/engine.py` (5 điểm)

2.1. `TurnInput.kind` thêm `"pause"` (Literal + comment).
2.2. Thêm hằng (cạnh `DECLINE_SAY`):
`PAUSE_SAY = "Ok, mình để trắc nghiệm ở đây. Bạn cứ kể tiếp, muốn quay lại thì bấm Quay lại trắc nghiệm nhé."`
2.3. Thêm method `_pause` (đặt cạnh `_more`):
```python
def _pause(self, s: Session, inp: TurnInput, emit: Emit) -> None:
    """"Thoát" giữa quiz: về chat nhưng giữ nguyên tiến độ (asked + values). Thẻ quiz đang mở rớt khỏi màn
    hình nhưng `_quiz_next` dựng lại được vì `asked` không đổi; câu đang làm rõ dở (`other_qid`) thì bỏ."""
    if s.state.meta.phase != "quiz":
        emit("card", self._card(s.state, s.card))
        return
    turn = self._open_turn(s, "Tạm nghỉ trắc nghiệm", "answer")
    s.state = with_meta(s.state, turn=turn, phase="paused", other_qid=None, other_text=None)
    s.card = conversation_card()
    s.transcript.append({"role": "agent", "text": PAUSE_SAY, "turn": turn, "kind": "say"})
    emit("say", {"replace": PAUSE_SAY})
    emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
    emit("card", self._card(s.state, s.card))
```
2.4. `_run`: `clarify = may_ask and (not s.state.meta.told or s.state.meta.phase == "paused")`.
Lý do: paused cho agent hỏi bằng lời; khối auto-resume (phase == "chat") không chạm paused nên không bị lôi về quiz.
2.5. `_more`: `if s.state.meta.phase not in ("chat", "paused"):` + sửa comment (paused resume được).

Không đổi: `_text` (paused rơi xuống `_run` mặc định), `_show`, `_requiz`, `_close_turn` (nhánh else an toàn), `view()`.

## 3. Agent: `src/trip/agent/tools/core.py` (2 chỗ)

3.1. `specs().show`: `reopen_quiz` → `self.interactive and self.state.meta.phase in ("quiz", "review", "paused")`.
3.2. `_reopen_quiz` guard: `("quiz", "review")` → `("quiz", "review", "paused")` (về quiz từ paused = resume).

## 4. Prompt: `src/trip/agent/prompts.py` (2 chỗ)

4.1. Dòng `reopen_quiz`: phase thêm paused.
4.2. Thêm đoạn (sau đoạn foundation_complete):
`phase paused means the quiz is on hold and the user chats freely: you MAY ask in words here (unlike post-telling chat), but ONLY about what the state does not know yet. Read CURRENT CONTEXT state, still_needed and declined_questions first; never re-ask anything known, declined, or just asked (the quiz cards own those).`
(Cơ chế chống trùng đã có: `_already_known` + `judge.repeats` + declined_questions — prompt chỉ việc trỏ vào.)

## 5. Web: `tu/types.ts` + `Understand.tsx` + `TripChat.tsx`

5.1. `TurnInput` thêm `| { kind: 'pause' }`.
5.2. `Understand.tsx`:
- `const [paused, setPaused] = useState(false)` + `pausedRef` mirror (effect cần).
- effect card: nhánh `!asks(card)` thêm `if (pausedRef.current) return` trước `setChat(!quizzed)` (giữ chat khi backend trả conversation lúc pause).
- `talk = chat || paused || (!questioning && !quizzed)` (summary tự tắt khi paused).
- Nút "Thoát" ở header flashcard khi quiz card (asks && !ask: && qid!=='review'): `onClick = () => { send({kind:'pause'}); setPaused(true); setChat(true) }`.
- Resume = `more()` sẵn có + `setPaused(false)` (thẻ quiz về → effect lật deck; thêm `setPaused(false)` vào effect khi quiz card tới cho chắc).
- `reset()`: `setPaused(false)`.
5.3. `TripChat.tsx`: prop `onResume: () => void`; trong `.tg-chat__go`, khi `paused` hiện nút ghost "Quay lại trắc nghiệm" (cạnh "Bắt đầu tìm"). (`more` khi paused vẫn là `more` → resume, giữ nguyên.)

## 6. Test: `tests/trip/test_phases.py` (thêm)

- `test_pause_keeps_quiz_progress_and_chat_continues`: quiz giữa chừng → pause → phase paused + card conversation + asked giữ; text turn với ScriptedChat ask → thẻ `ask:`; trả lời xong vẫn paused (không bị lôi về quiz).
- `test_resume_continues_where_paused`: pause → more → đúng thẻ quiz dở (không hỏi lại thẻ đã xong).
- `test_pause_drops_pending_other`: other_qid đang set → pause → cleared.
- `test_pause_outside_quiz_reemits`: pause ở review/chat → trả card cũ.
- `test_reopen_tool_in_paused_goes_to_quiz`: tool ở paused → quiz.

## 7. Docs

- `TRIP_UNDERSTANDING.md` §4 (dòng phases + chỗ review): thêm `paused` + 2 câu về pause/resume.
- `UI_SPEC_USER_WEB.md` § tóm tắt/review: thêm bullets nút Thoát / Quay lại trắc nghiệm.

## 8. Verify

- `pytest tests/trip/` xanh full (engine cũ không đổi hành vi khi không pause).
- `npx tsc --noEmit` trong `web/`, `build:prod`, curl local+public.
- Restart harness `:8769` (backend đổi), test tay: quiz → Thoát → chat (agent hỏi không trùng) → Quay lại → đúng thẻ dở → xong → review.
- Không commit (quy ước hiện tại: giữ WIP).
