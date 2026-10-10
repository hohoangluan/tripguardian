"""Small Streamlit client for exercising the Trip Understanding harness boundary."""

from __future__ import annotations

import http.client
import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import streamlit as st


DEFAULT_BASE_URL = "http://127.0.0.1:8769"


def auth_headers(url: str) -> dict:
    """The harness needs a signed-in cookie and, for writes, an Origin that matches its Host."""
    parts = urlparse(url)
    headers = {"Origin": f"{parts.scheme}://{parts.netloc}"}
    if cookie := st.session_state.get("cookie"):
        headers["Cookie"] = cookie
    return headers


def sign_in(base_url: str, email: str) -> None:
    """Harness started with TG_TEST_LOGIN=1 and an http APP_BASE_URL: GET /api/auth/test/login sets the session cookie."""
    parts = urlparse(base_url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=30)
    try:
        conn.request("GET", f"/api/auth/test/login?{urlencode({'email': email, 'name': 'Tester'})}")
        response = conn.getresponse()
        cookie = (response.getheader("Set-Cookie") or "").split(";")[0]
    except OSError as exc:
        raise RuntimeError(f"Cannot reach Harness: {exc}") from exc
    finally:
        conn.close()
    if not cookie:
        raise RuntimeError("Sign-in refused: start Harness with TG_TEST_LOGIN=1 and an http APP_BASE_URL.")
    st.session_state.cookie = cookie


def request_json(url: str, method: str = "GET", payload: dict | None = None) -> dict | list:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {**auth_headers(url), **({"Content-Type": "application/json"} if body else {})}
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=30) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"Harness returned {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach Harness: {exc.reason}") from exc


def stream_request(url: str, payload: dict) -> tuple[dict, list[dict]]:
    body = json.dumps(payload).encode()
    headers = {**auth_headers(url), "Content-Type": "application/json", "Accept": "text/event-stream"}
    events: list[dict] = []
    receipt: dict | None = None
    try:
        with urlopen(Request(url, data=body, headers=headers, method="POST"), timeout=90) as response:
            for line in response:
                if not line.startswith(b"data: "):
                    continue
                event = json.loads(line[6:])
                if event.get("event") == "error":
                    data = event.get("data", {})
                    raise RuntimeError(data.get("message", "Harness could not process the request."))
                if event.get("event") == "journey":
                    receipt = event["data"]
                else:
                    events.append(event)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Harness returned {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach Harness: {exc.reason}") from exc
    if receipt is None:
        raise RuntimeError("Harness stream ended without a journey receipt.")
    return receipt, events


def reset_session() -> None:
    for key in ("journey", "events", "search_input"):
        st.session_state.pop(key, None)


def trip_view(journey: dict) -> dict:
    result = journey.get("result", {})
    return result.get("view", result) if isinstance(result, dict) else {}


def create_journey(base_url: str, experience: str | None, start_with: str | None, email: str) -> None:
    sign_in(base_url, email)
    journey = request_json(
        f"{base_url}/api/harness/sessions",
        "POST",
        {"experience": experience, "start_with": start_with},
    )
    st.session_state.journey = journey
    st.session_state.events = []
    st.session_state.pop("search_input", None)


def submit_turn(base_url: str, turn: dict) -> None:
    journey = st.session_state.journey
    request = {
        "request_id": str(uuid.uuid4()),
        "stage": "trip",
        "operation": "turn",
        "expected_revision": journey["revision"],
        "payload": turn,
    }
    receipt, events = stream_request(f"{base_url}/api/harness/sessions/{journey['id']}/request", request)
    st.session_state.journey = receipt
    st.session_state.events.extend(events)
    for event in events:
        if event.get("event") == "done":
            st.session_state.search_input = event.get("data", {}).get("search_input")


def render_card(base_url: str, view: dict) -> None:
    card = view.get("card")
    if not card:
        st.success("Trip Understanding is done.")
        return
    if card.get("text"):
        st.subheader(card["text"])
    if card.get("reason"):
        st.caption(card["reason"])
    chips = card.get("chips", [])
    labels = {chip["label"]: chip["id"] for chip in chips}
    with st.form("trip-answer", clear_on_submit=True):
        selected: list[str] = []
        if chips:
            if card.get("multi"):
                selected = st.multiselect("Choices (pick several, then Send)", list(labels),
                                          key=f"chips-{card['qid']}")
            else:
                picked = st.radio("Choices", list(labels), index=None, key=f"chips-{card['qid']}")
                selected = [picked] if picked else []
        text = st.text_input("Other answer (typed text wins over picked chips)" if chips else "Your answer",
                             key=f"answer-{card['qid']}")
        if card.get("input") == "date":
            day = st.date_input("Ngày khởi hành", value=None, key=f"day-{card['qid']}")
        else:
            day = None
        cols = st.columns(3)
        with cols[0]:
            sent = st.form_submit_button("Send")
        with cols[1]:
            skipped = st.form_submit_button("Bỏ qua", disabled=not card.get("exits", True))
        with cols[2]:
            unsure = st.form_submit_button("Chưa chắc", disabled=not card.get("exits", True))
    if sent:
        if day is not None:
            try:
                submit_turn(base_url, {"kind": "answer", "qid": card["qid"], "value": day.isoformat()})
                st.rerun()
            except RuntimeError as exc:
                st.error(str(exc))
            return
        if text.strip():
            turn: dict = {"kind": "answer", "qid": card["qid"], "text": text.strip()}
        elif selected:
            turn = {"kind": "answer", "qid": card["qid"], "chips": [labels[label] for label in selected]}
        else:
            st.warning("Choose an option or enter text.")
            return
        try:
            submit_turn(base_url, turn)
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))
    elif skipped or unsure:
        try:
            submit_turn(base_url, {"kind": "answer", "qid": card["qid"],
                                   "chips": ["skip" if skipped else "unsure"]})
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))


def main() -> None:
    st.set_page_config(page_title="Trip Understanding Tester", layout="wide")
    st.title("Trip Understanding Tester")
    st.caption("A minimal Streamlit client for the Harness HTTP/SSE boundary.")

    with st.sidebar:
        base_url = st.text_input("Harness URL", DEFAULT_BASE_URL).rstrip("/")
        email = st.text_input("Test sign-in email", "tester@test.local")
        experience = st.selectbox("Experience", ["", "first", "returning"])
        start_with = st.selectbox("Start with", ["", "nothing", "saved", "must", "itinerary"])
        if st.button("New Trip", type="primary"):
            try:
                create_journey(base_url, experience or None, start_with or None, email)
                st.rerun()
            except RuntimeError as exc:
                st.error(str(exc))
        if st.button("Clear local session"):
            reset_session()
            st.rerun()

    journey = st.session_state.get("journey")
    if not journey:
        st.info("Start Harness, then create a new Trip session.")
        st.code("python -m harness serve\nstreamlit run tools/trip_tester.py", language="sh")
        return

    view = trip_view(journey)
    st.caption(f"Journey `{journey['id']}` | revision `{journey['revision']}` | stage `{journey['stage']}`"
               f" | phase `{view.get('phase', '?')}` | card `{view.get('card', {}).get('qid', '-')}`")
    left, right = st.columns((3, 2))
    with left:
        transcript = view.get("transcript", [])
        if transcript and transcript[-1].get("role") == "agent":  # the reply to the last turn, if there was one
            with st.chat_message("assistant"):
                st.write(transcript[-1].get("text", ""))
        render_card(base_url, view)
    with right:
        understanding = view.get("understanding", {})
        missing = [m["label"] for m in understanding.get("missing", [])]
        if st.button("Next: xem gợi ý", type="primary", disabled=not understanding.get("ready")):
            try:
                submit_turn(base_url, {"kind": "show"})
                st.rerun()
            except RuntimeError as exc:
                st.error(str(exc))
        if missing:
            st.caption("Còn thiếu: " + ", ".join(missing))
        st.subheader("Understanding")
        st.json(understanding, expanded=False)
        if st.session_state.get("search_input"):
            st.subheader("Search Input")
            st.json(st.session_state.search_input, expanded=False)
        with st.expander("Place lookup"):
            query = st.text_input("Place name")
            if query:
                try:
                    places = request_json(f"{base_url}/api/harness/places?{urlencode({'q': query})}")
                    st.json(places)
                except RuntimeError as exc:
                    st.error(str(exc))
        with st.expander("SSE events"):
            st.json(st.session_state.get("events", []), expanded=False)


if __name__ == "__main__":
    main()
