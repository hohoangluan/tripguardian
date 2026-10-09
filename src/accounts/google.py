"""Google OAuth 2.0 boundary: authorization URL (code + PKCE), code exchange, ID token check, refresh, revoke."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REVOKE = "https://oauth2.googleapis.com/revoke"
LOGIN_SCOPES = ("openid", "email", "profile")
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.app.created"
TIMEOUT_S = 15


class GoogleError(RuntimeError):
    pass


class GoogleClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri

    @classmethod
    def from_env(cls) -> "GoogleClient":
        return cls(os.environ.get("GOOGLE_CLIENT_ID", ""), os.environ.get("GOOGLE_CLIENT_SECRET", ""),
                   os.environ.get("GOOGLE_REDIRECT_URI", ""))

    def auth_url(self, state: str, challenge: str, scopes: tuple[str, ...], offline: bool = False) -> str:
        params = {"client_id": self.client_id, "redirect_uri": self.redirect_uri, "response_type": "code",
                  "scope": " ".join(scopes), "state": state, "code_challenge": challenge,
                  "code_challenge_method": "S256"}
        if offline:  # Calendar: a refresh token, granted on top of the login scopes
            params |= {"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"}
        else:
            params["prompt"] = "select_account"
        return AUTH + "?" + urllib.parse.urlencode(params)

    def _post(self, url: str, form: dict) -> dict:
        req = urllib.request.Request(url, urllib.parse.urlencode(form).encode(),
                                     {"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
                body = res.read()
        except urllib.error.HTTPError as exc:
            raise GoogleError(f"google {exc.code}: {exc.read()[:200]!r}") from exc
        except OSError as exc:
            raise GoogleError(f"google unreachable: {exc}") from exc
        return json.loads(body or b"{}")

    def exchange(self, code: str, verifier: str) -> dict:
        """The token response: id_token, access_token, maybe refresh_token and scope."""
        return self._post(TOKEN, {"code": code, "code_verifier": verifier, "client_id": self.client_id,
                                  "client_secret": self.client_secret, "redirect_uri": self.redirect_uri,
                                  "grant_type": "authorization_code"})

    def verify(self, id_token: str) -> dict:
        """Signature, audience, issuer and expiry checked by google-auth; returns the claims."""
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token as idt
        try:
            return idt.verify_oauth2_token(id_token, Request(), self.client_id)
        except ValueError as exc:
            raise GoogleError(f"bad id_token: {exc}") from exc

    def access_token(self, refresh_token: str) -> str:
        return self._post(TOKEN, {"refresh_token": refresh_token, "client_id": self.client_id,
                                  "client_secret": self.client_secret, "grant_type": "refresh_token"})["access_token"]

    def revoke(self, token: str) -> None:
        self._post(REVOKE, {"token": token})
