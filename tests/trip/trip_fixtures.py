"""Helpers shared by tests/trip (a module, not a package: tests/trip has no __init__)."""

import json

from trip.agent import Assistant, Call


def rec(i, name, feats, hours=None, status="signal", needs_review=False):
    """One data/intel/places record; feats: {feature: (top_value, n) or (top_value, n, by_context)}."""
    return {"place_fid": f"0x{i:x}:0x1", "place_name": name,
            "identity": {"category": "Quán cà phê", "lat": 11.94, "lng": 108.45},
            "operation": {"hours": hours},
            "features": {f: {"n": v[1], "top_value": v[0], "status": status, "needs_review": needs_review,
                             "by_context": v[2] if len(v) > 2 else {}} for f, v in feats.items()}}


MONDAY_CLOSED = {"mon": [], "tue": [["07:00", "22:00"]], "wed": [["07:00", "22:00"]], "thu": [["07:00", "22:00"]],
                 "fri": [["07:00", "22:00"]], "sat": [["07:00", "22:00"]], "sun": [["07:00", "22:00"]]}


def say(text):
    """A model reply with text and no tool call."""
    return Assistant(content=text)


def call(name, **args):
    return Call(id=f"call_{name}", name=name, arguments=json.dumps(args, ensure_ascii=False))


def reply(*calls, text=""):
    return Assistant(content=text, calls=list(calls))


def fact(field, value, quote, op="set", how="said"):
    return call("record_fact", field=field, op=op, value=value, quote=quote, how=how)


def ask(text, *options, multi=False):
    if options:
        return call("ask_choice", text=text, options=list(options), multi=multi, reason="vì sao")
    return call("ask_text", text=text)


class ScriptedChat:
    """A Chat that plays the given replies in order (one per model call); out of replies it raises AgentError."""

    def __init__(self, *replies, error=None):
        self.replies, self.error, self.calls, self.seen = list(replies), error, 0, []

    async def __call__(self, messages, tools, on_say):
        self.calls += 1
        self.seen.append((list(messages), [t["function"]["name"] for t in tools]))
        if self.error:
            raise self.error
        if not self.replies:
            from trip.agent import AgentError
            raise AgentError("script ended")
        r = self.replies.pop(0)
        if r.content:
            on_say(r.content)
        return r
