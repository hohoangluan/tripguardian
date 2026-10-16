"""The seven required tabs, built from missing user answers rather than model text."""

from .deck import Option, Tab, exits
from .readiness import TITLE, missing
from .state import Draft, TripState


def tabs(state: TripState, cfg) -> tuple[Tab, ...]:
    def answered(f):
        return f.known and f.source == "user"

    def option(id, label, field=None, value=None, writes=(), current=None, description=""):
        guessed = current is not None and current.known and current.source != "user"
        selected = guessed and current.value == (id if value is None else value) and field not in state.meta.conflicts
        quote = next((e.quote for e in reversed(current.evidence) if e.quote), "") if selected else ""
        return Option(id=id, label=label, description=description,
                      writes=tuple(writes) or ((Draft(field=field, value=id if value is None else value),) if field else ()),
                      prefilled=selected, because=f"vì bạn nói '{quote}'" if quote else "theo thông tin dự kiến" if selected else "")

    out = []
    for key, _ in missing(state, cfg.required):
        inputs, options, multi = (), (), False
        if key == "trip":
            header, question, why = TITLE["trip"], "Bạn đi ngày nào, bắt đầu và kết thúc lúc mấy giờ?", "Để biết thời gian có thể đi chơi."
            inputs = tuple(k for k, ok in (
                ("dates", answered(state.start_date) and answered(state.days)),
                ("start", any(answered(f) for f in (state.checkin_at, state.frame.arrive, state.inbound))),
                ("end", any(answered(f) for f in (state.checkout_at, state.frame.leave, state.outbound)))) if not ok)
            from datetime import datetime, timedelta
            from .frame import FrameDefaults, compile_frame
            frame = compile_frame(state, cfg.arrival_buffer_min, cfg.entry_min, FrameDefaults(**cfg.frame))
            questions = []
            if "dates" in inputs:
                questions.append("Bạn ở Đà Lạt từ ngày nào đến ngày nào?")
            if "start" in inputs and "end" in inputs:
                questions.append("Ngày đầu bắt đầu và ngày cuối xong lúc mấy giờ?")
            elif "start" in inputs:
                questions.append("Ngày đầu bạn bắt đầu chơi lúc mấy giờ?")
            elif "end" in inputs:
                questions.append("Ngày cuối bạn cần xong lúc mấy giờ?")
            question = " ".join(questions)
            if state.start_date.known and state.days.known:
                start = state.start_date.value
                end = start + timedelta(days=state.days.value - 1)
                def day(d):
                    return f"{'CN' if d.weekday() == 6 else 'T' + str(d.weekday() + 2)} {d:%d/%m}"
                why = f"Bạn đi {day(start)} – {day(end)}. Mình dùng giờ để chia lịch."
            opts = []
            for slot, label, field, moment, transit, default in (
                    ("start", "Bắt đầu", "checkin_at", state.frame.arrive, state.inbound, cfg.frame["first_start"]),
                    ("end", "Kết thúc", "checkout_at", state.frame.leave, state.outbound, cfg.frame["last_end"])):
                if slot not in inputs:
                    continue
                current = getattr(state, field)
                physical = moment.value
                at = physical.at if physical else (
                    (transit.value.arrive_at if slot == "start" else transit.value.depart_at) if transit.known else None)
                clock = current.value or default
                if frame:
                    clock = frame.days[0].start if slot == "start" else frame.days[-1].end
                description = ("Giờ nhận phòng thường gặp; mình xếp lịch từ giờ này." if slot == "start" else
                               "Giờ trả phòng thường gặp; mình xếp lịch xong trước giờ này.")
                because = "Giờ nhận phòng thường gặp" if slot == "start" else "Giờ trả phòng thường gặp"
                if at:
                    if frame is None:
                        delta = timedelta(minutes=cfg.arrival_buffer_min + cfg.entry_min)
                        bound = datetime.fromisoformat(at) + (delta if slot == "start" else -delta)
                        clock = bound.strftime("%H:%M")
                    mode = physical.how if physical else transit.value.mode
                    verb = "bay" if mode == "plane" else "xe" if mode == "bus" else "bạn"
                    because = f"vì {verb} {'tới' if slot == 'start' else 'về'} {at[11:].lstrip('0')}"
                    description = ("Mình chừa giờ xuống xe, lấy đồ và vào thành phố." if slot == "start" else
                                   "Mình chừa giờ ra bến, sân bay và làm thủ tục.")
                elif current.known or clock != default:
                    description = "Mình chia lịch theo giờ bạn xác nhận."
                    because = next((e.quote for e in reversed(current.evidence) if e.quote), "Giờ dự kiến")
                if slot != "end" or clock >= "05:30":
                    opts.append(option(f"{slot}.default", f"{label} {clock}", field, clock,
                                   current=current, description=description).model_copy(update={
                                       "prefilled": not {"trip", field} & set(state.meta.conflicts),
                                       "because": because if not {"trip", field} & set(state.meta.conflicts) else ""}))
                for id, part, hour in (("early", "Sáng sớm (5–7h)", "05:30"), ("morning", "Sáng", "08:00"),
                                       ("midday", "Trưa", "12:00"), ("afternoon", "Chiều", "14:00"),
                                       ("evening", "Tối", "18:00")):
                    if slot == "end" and id == "early":
                        continue
                    opts.append(option(f"{slot}.{id}", part, field, hour,
                        description=f"{'Ngày đầu chơi từ' if slot == 'start' else 'Ngày cuối xong trước'} {hour}; bạn có thể sửa giờ."))
            options = tuple(opts)
            if "dates" in inputs and state.start_date.known and state.days.known:
                end = state.start_date.value + timedelta(days=state.days.value - 1)
                quote = next((e.quote for f in (state.start_date, state.days) for e in f.evidence if e.quote), "")
                options += (Option(id="dates.prefilled", label=f"{state.start_date.value:%d/%m} – {end:%d/%m}",
                    description="Mình chia ngày và kiểm giờ mở cửa theo khoảng này.",
                    writes=(Draft(field="start_date", value=state.start_date.value), Draft(field="days", value=state.days.value)),
                    prefilled="trip" not in state.meta.conflicts, because=f"vì bạn nói '{quote}'" if quote else "theo ngày dự kiến"),)
        elif key == "companions":
            from .questions import WHO
            header, question, why = TITLE["companions"], "Ai đi cùng bạn, tổng cộng mấy người?", "Để chọn nơi và tính chi phí cho cả nhóm."
            inputs = tuple(k for k, f in (("who", state.companions), ("people", state.people)) if not answered(f))
            if "people" not in inputs:
                question = f"Nhóm bạn có {state.people.value} người. Ai đi cùng bạn?"
            elif "who" not in inputs:
                question = "Nhóm bạn có tổng cộng mấy người?"
            multi = True
            if "who" in inputs:
                chosen = set(state.companions.value or ()) | {who for who, _ in state.meta.companion_hints}
                quote = next((e.quote for e in reversed(state.companions.evidence) if e.quote), "")
                hints = dict(state.meta.companion_hints)
                opts = []
                for who, (label, drafts) in WHO.items():
                    guess = who in chosen and state.companions.source != "user" and "companions" not in state.meta.conflicts
                    reason = hints.get(who, quote)
                    description = {"solo": "Mình tính chi phí cho một người.",
                        "partner": "Ưu tiên nơi phù hợp đi đôi.", "friends": "Ưu tiên nơi phù hợp nhóm bạn.",
                        "kids": "Mình kiểm nơi phù hợp trẻ nhỏ và giờ nghỉ.",
                        "parents": "Mình kiểm sức đi bộ, bậc thang và giờ nghỉ.",
                        "baby": "Mình tránh nơi không phù hợp em bé.",
                        "pet": "Mình kiểm nơi cho phép mang thú cưng.",
                        "coworkers": "Mình chọn nơi phù hợp cả nhóm đồng nghiệp."}[who]
                    opts.append(Option(id=who, label=label, description=description, writes=drafts, prefilled=guess,
                                       because=f"vì bạn nói '{reason}'" if guess and reason else ""))
                options = tuple(opts)
            if "people" in inputs and state.people.known:
                options += (option("people.prefilled", f"{state.people.value} người", "people", state.people.value,
                                   current=state.people, description="Mình dùng số người để tính chi phí cho nhóm."),)
        elif key == "mobility":
            header, question, why = TITLE["mobility"], "Bạn đi lại bằng gì ở Đà Lạt?", "Để tính đường đi và thời gian di chuyển."
            opts = []
            for id, label, vehicle, driver in (("motorbike", "Xe máy", "motorbike", None),
                    ("car_self", "Ô tô tự lái", "car", "self"), ("car_hired", "Taxi, Grab, thuê tài xế", "car", "hired"),
                    ("walk", "Đi bộ", "walk", None)):
                current = state.mobility
                opts.append(option(id, label, "mobility", vehicle, writes=(Draft(field="mobility", value=vehicle),
                    Draft(field="driver", value=driver)), current=current, description={
                        "motorbike": "Mình tính giờ chạy xe máy và lưu ý đường tối.",
                        "car_self": "Mình tính giờ lái ô tô và kiểm chỗ đỗ.",
                        "car_hired": "Mình tính đường ô tô, bạn không cần tự lái.",
                        "walk": "Mình gom các nơi gần nhau để bạn đi bộ."}[id]).model_copy(update={"prefilled":
                    current.known and current.source != "user" and current.value == vehicle
                    and (vehicle != "car" or state.driver.value == driver) and "mobility" not in state.meta.conflicts}))
            options = tuple(opts)
        elif key == "care":
            from .questions import care_q, c_effort
            header, question, why = TITLE["care"], "Có điều gì về sức khỏe, đi lại hay ăn uống cần lưu ý?", "Để tránh nơi không phù hợp với người trong nhóm."
            multi = True
            chips = {c.id: c.drafts for c in care_q().chips}
            inferred = tuple(s.kind for s in state.signals if not s.handled and (s.source == "inferred" or s.from_companion))
            options = (Option(id="none", label="Không có", description="Không thêm điều cần tránh từ câu này.",
                        writes=(Draft(field="signal_handled", value=inferred),
                        Draft(field="care", value="none"))),) + tuple(
                Option(id=id, label=label, description={
                    "steps": "Mình tránh nơi nhiều dốc, bậc thang hoặc phải đi bộ xa.",
                    "wheelchair": "Mình kiểm lối xe lăn và tránh dốc, bậc thang.",
                    "pregnant": "Mình kiểm điều kiện đi lại phù hợp người mang bầu.",
                    "motion_sick": "Mình ghi lại để hỏi thêm về chặng xe và đường đèo.",
                    "height": "Mình ghi lại để hỏi thêm những nơi bạn cần tránh.",
                    "vegetarian": "Mình chọn nơi ăn uống có món chay.",
                    "vegan": "Mình chọn nơi ăn uống có món thuần chay."}[id],
                       writes=((next(c.drafts for c in c_effort(state).chips if c.id == "both")
                       if id == "steps" else chips[alias] + (next(c.drafts for c in c_effort(state).chips if c.id == "both")
                       if id == "wheelchair" else ())) + (Draft(field="care", value="listed"),)))
                for id, alias, label in (("steps", "steps", "Tránh dốc, bậc thang"), ("wheelchair", "wheelchair", "Xe lăn"),
                    ("pregnant", "pregnant", "Có người mang bầu"), ("motion_sick", "motion", "Say xe"),
                    ("height", "height", "Sợ độ cao"), ("vegetarian", "veg", "Ăn chay"), ("vegan", "vegan", "Thuần chay")))
        elif key == "pace":
            header, question, why = TITLE["pace"], "Bạn muốn đi thong thả hay ghé nhiều nơi?", "Để chia số nơi mỗi ngày."
            options = tuple(option(id, label, "pace", current=state.pace).model_copy(update={
                "description": f"Khoảng {cfg.pace_per_day[id]} nơi mỗi ngày"})
                for id, label in (("slow", "Thong thả"), ("normal", "Vừa phải"), ("packed", "Đi nhiều nơi")))
        elif key == "budget":
            header, question, why = TITLE["budget"], "Bạn muốn chi khoảng bao nhiêu và tính cho ai?", "Mình chọn nơi theo khoản chi, chưa gồm vé tới Đà Lạt."
            inputs = tuple(k for k, f in (("amount", state.budget_vnd), ("scope", state.budget_scope)) if not answered(f))
            if "amount" not in inputs:
                question = f"Khoản {state.budget_vnd.value:,} đồng tính cho ai, trong bao lâu?"
            elif "scope" not in inputs:
                question = "Bạn muốn chi khoảng bao nhiêu?"
            options = (option("unlimited", "Không giới hạn", "budget_unlimited", True, current=state.budget_unlimited,
                              description="Mình không đặt trần chi phí cho lịch."),)
            if "amount" in inputs and state.budget_vnd.known:
                options += (option("amount.prefilled", f"{state.budget_vnd.value:,} đồng", "budget_vnd", state.budget_vnd.value,
                                   current=state.budget_vnd, description="Mình chọn nơi và chỗ ở trong khoản này."),)
            if "scope" in inputs:
                options += tuple(option(id, label, "budget_scope", current=state.budget_scope,
                                        description=f"Mình tính khoản chi cho {label.lower()}.") for id, label in (
                    ("trip_total", "Cả nhóm, cả chuyến"), ("per_day", "Cả nhóm mỗi ngày"),
                    ("per_person", "Mỗi người cả chuyến"), ("per_person_day", "Mỗi người mỗi ngày")))
        else:
            header, question, why = TITLE["lodging"], "Bạn ở đâu trong chuyến đi?", "Mỗi ngày bắt đầu và kết thúc ở chỗ ở. Chưa đặt thì tìm khu bạn muốn ở."
            inputs = ("lodging",)
            if state.lodging.known:
                options = (option("lodging.prefilled", state.lodging.value.text[:40], "lodging", state.lodging.value,
                                  current=state.lodging, description="Mình dùng chỗ ở này làm điểm đi và về mỗi ngày."),)
        if key in state.meta.conflicts:
            why = "Bạn nói cả hai; chọn điều bạn muốn cho chuyến này."
        out.append(Tab(qid=key, kind="required", header=header, question=question, why=why, multi=multi,
                       inputs=inputs, options=options + exits()))
    return tuple(out)
