"""Spotify Web API search helpers."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SPOTIFY_TOKEN_ENDPOINT = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_ENDPOINT = "https://api.spotify.com/v1/search"


class SpotifySearchError(RuntimeError):
    """Raised when Spotify Web API search fails."""


@dataclass
class PlaylistCandidate:
    name: str
    owner: str
    uri: str
    external_url: str
    tracks_total: int
    description: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "owner": self.owner,
            "uri": self.uri,
            "external_url": self.external_url,
            "tracks_total": self.tracks_total,
            "description": self.description,
        }


def _get_client_credentials_token() -> str:
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SpotifySearchError("SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET is not set")

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    req = Request(
        SPOTIFY_TOKEN_ENDPOINT,
        method="POST",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SpotifySearchError(f"Failed to get Spotify access token: {exc}") from exc

    token = str(payload.get("access_token", "")).strip()
    if not token:
        raise SpotifySearchError(f"Spotify token response missing access_token: {payload}")
    return token


def search_spotify_playlists(
    query: str,
    limit: int = 8,
    market: str = "JP",
) -> list[PlaylistCandidate]:
    """Search playlists from Spotify Web API."""
    q = query.strip()
    if not q:
        raise SpotifySearchError("query is empty")

    limit = max(1, min(20, int(limit)))
    token = _get_client_credentials_token()
    params = urlencode(
        {
            "q": q,
            "type": "playlist",
            "limit": limit,
            "market": market,
        }
    )
    url = f"{SPOTIFY_SEARCH_ENDPOINT}?{params}"
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SpotifySearchError(f"Spotify search request failed: {exc}") from exc

    items = payload.get("playlists", {}).get("items", [])
    results: list[PlaylistCandidate] = []
    for item in items:
        if not item:
            continue
        results.append(
            PlaylistCandidate(
                name=str(item.get("name", "")),
                owner=str(item.get("owner", {}).get("display_name", "")),
                uri=str(item.get("uri", "")),
                external_url=str(item.get("external_urls", {}).get("spotify", "")),
                tracks_total=int(item.get("tracks", {}).get("total", 0)),
                description=str(item.get("description", "")),
            )
        )
    return results
