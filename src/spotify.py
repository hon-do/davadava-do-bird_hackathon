"""Spotify control via AppleScript (macOS) + Web API (spotipy)."""

import os
import subprocess
import time

import spotipy
from spotipy.oauth2 import SpotifyOAuth


# ---------------------------------------------------------------------------
# Spotify Web API client (spotipy)
# ---------------------------------------------------------------------------

def _get_spotify_client() -> spotipy.Spotify:
    """Get an authenticated Spotify client."""
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.environ["SPOTIPY_CLIENT_ID"],
        client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
        redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback"),
        scope="user-modify-playback-state user-read-playback-state user-read-currently-playing playlist-read-private playlist-read-collaborative user-top-read",
        cache_path=os.path.join(os.path.dirname(__file__), ".spotify_cache"),
    ))


# ---------------------------------------------------------------------------
# AppleScript helpers
# ---------------------------------------------------------------------------

def osascript(cmd: str) -> str:
    """Execute an AppleScript command targeting Spotify."""
    result = subprocess.run(
        ["osascript", "-e", f'tell application "Spotify" to {cmd}'],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip() or "Done"


def osascript_raw(script: str) -> str:
    """Execute a raw AppleScript snippet."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip() or "Done"


# ---------------------------------------------------------------------------
# User taste profile & Recommendations API
# ---------------------------------------------------------------------------

# キャッシュ（セッション中に何度も API を叩かないため）
_user_id_cache: str | None = None
_top_artists_cache: list[dict] | None = None
_top_tracks_cache: list[dict] | None = None
_genre_seeds_cache: list[str] | None = None


def _get_current_user_id() -> str:
    """Get the current user's Spotify ID (cached)."""
    global _user_id_cache
    if _user_id_cache is None:
        try:
            sp = _get_spotify_client()
            _user_id_cache = sp.current_user()["id"]
        except Exception:
            _user_id_cache = ""
    return _user_id_cache


def get_top_artists(limit: int = 20) -> list[dict]:
    """Get user's top artists with genres (cached)."""
    global _top_artists_cache
    if _top_artists_cache is not None:
        return _top_artists_cache[:limit]
    try:
        sp = _get_spotify_client()
        results = sp.current_user_top_artists(limit=limit, time_range="medium_term")
        _top_artists_cache = [
            {
                "id": a["id"],
                "name": a["name"],
                "genres": a.get("genres", []),
                "uri": a["uri"],
            }
            for a in results.get("items", [])
        ]
        return _top_artists_cache
    except Exception:
        return []


def get_top_tracks(limit: int = 20) -> list[dict]:
    """Get user's top tracks (cached)."""
    global _top_tracks_cache
    if _top_tracks_cache is not None:
        return _top_tracks_cache[:limit]
    try:
        sp = _get_spotify_client()
        results = sp.current_user_top_tracks(limit=limit, time_range="medium_term")
        _top_tracks_cache = [
            {
                "id": t["id"],
                "name": t["name"],
                "artist": t["artists"][0]["name"] if t["artists"] else "",
                "uri": t["uri"],
            }
            for t in results.get("items", [])
        ]
        return _top_tracks_cache
    except Exception:
        return []


def get_available_genre_seeds() -> list[str]:
    """Get valid genre seeds for Recommendations API (cached)."""
    global _genre_seeds_cache
    if _genre_seeds_cache is not None:
        return _genre_seeds_cache
    try:
        sp = _get_spotify_client()
        _genre_seeds_cache = sp.recommendation_genre_seeds()["genres"]
        return _genre_seeds_cache
    except Exception:
        # Spotify が genre seeds endpoint を廃止した場合のフォールバック
        _genre_seeds_cache = [
            "acoustic", "ambient", "alternative", "anime", "blues",
            "chill", "classical", "club", "country", "dance",
            "disco", "edm", "electronic", "folk", "funk",
            "gospel", "happy", "hip-hop", "house", "indie",
            "indie-pop", "j-pop", "j-rock", "jazz", "k-pop",
            "latin", "metal", "party", "piano", "pop",
            "punk", "r-n-b", "reggae", "rock", "romance",
            "sad", "singer-songwriter", "sleep", "soul", "study",
            "summer", "techno", "trance", "trip-hop", "work-out",
        ]
        return _genre_seeds_cache


def get_user_seed_artists(limit: int = 3) -> list[str]:
    """Get artist IDs from user's top artists for use as seeds."""
    artists = get_top_artists(limit)
    return [a["id"] for a in artists]


def get_user_seed_tracks(limit: int = 2) -> list[str]:
    """Get track IDs from user's top tracks for use as seeds."""
    tracks = get_top_tracks(limit)
    return [t["id"] for t in tracks]


def get_user_top_genres(limit: int = 5) -> list[str]:
    """Get user's top genres from their top artists, filtered to valid seeds."""
    artists = get_top_artists(20)
    valid_seeds = set(get_available_genre_seeds())

    genre_count: dict[str, int] = {}
    for a in artists:
        for g in a["genres"]:
            # 完全一致 or 部分一致で有効なシードにマッピング
            if g in valid_seeds:
                genre_count[g] = genre_count.get(g, 0) + 1
            else:
                for vs in valid_seeds:
                    if vs in g or g in vs:
                        genre_count[vs] = genre_count.get(vs, 0) + 1
                        break

    if not genre_count:
        # アーティストジャンルが空の場合、日本のアーティストが多いなら推定
        artist_names = [a["name"].lower() for a in artists]
        # J-pop/J-rock をデフォルトに
        return ["j-pop", "j-rock", "anime", "pop", "rock"][:limit]

    sorted_genres = sorted(genre_count, key=genre_count.get, reverse=True)
    return sorted_genres[:limit]


def recommend_tracks(
    seed_artists: list[str] | None = None,
    seed_tracks: list[str] | None = None,
    seed_genres: list[str] | None = None,
    limit: int = 20,
    **audio_features,
) -> list[dict]:
    """Call Spotify Recommendations API with seeds and audio feature targets.

    audio_features examples:
        target_energy=0.8, target_valence=0.7, min_tempo=120, target_danceability=0.6
    """
    sp = _get_spotify_client()

    # 合計 seed は最大5つ
    all_seeds = (
        (len(seed_artists) if seed_artists else 0)
        + (len(seed_tracks) if seed_tracks else 0)
        + (len(seed_genres) if seed_genres else 0)
    )
    if all_seeds == 0:
        # シードがなければユーザーのトップから自動取得
        seed_artists = get_user_seed_artists(2)
        seed_genres = get_user_top_genres(2)

    try:
        results = sp.recommendations(
            seed_artists=seed_artists or [],
            seed_tracks=seed_tracks or [],
            seed_genres=seed_genres or [],
            limit=limit,
            **audio_features,
        )
        return [
            {
                "id": t["id"],
                "name": t["name"],
                "artist": t["artists"][0]["name"] if t["artists"] else "",
                "uri": t["uri"],
                "album": t["album"]["name"] if t.get("album") else "",
            }
            for t in results.get("tracks", [])
        ]
    except Exception:
        return []


def play_recommended_tracks(
    seed_artists: list[str] | None = None,
    seed_tracks: list[str] | None = None,
    seed_genres: list[str] | None = None,
    limit: int = 20,
    **audio_features,
) -> str:
    """Get recommendations and play the first track, queue the rest."""
    tracks = recommend_tracks(
        seed_artists=seed_artists,
        seed_tracks=seed_tracks,
        seed_genres=seed_genres,
        limit=limit,
        **audio_features,
    )
    if not tracks:
        return "No recommendations found"

    # 最初の曲を再生
    first = tracks[0]
    osascript(f'play track "{first["uri"]}"')
    time.sleep(1)

    info = current_track_summary()
    track_list = ", ".join(f'{t["name"]}' for t in tracks[:5])
    return f"Now playing: {info}\nUp next: {track_list}..."


# ---------------------------------------------------------------------------
# Search (Web API) - data only, no playback
# ---------------------------------------------------------------------------

def search_playlists(query: str, limit: int = 5) -> list[dict]:
    """Search Spotify for playlists and return metadata (no playback).

    Returns list of dicts with keys: uri, name, description, tracks_total, is_own.
    Returns empty list if search fails or nothing found.
    """
    try:
        sp = _get_spotify_client()
        results = sp.search(q=query, type="playlist", limit=limit)
        playlists = results.get("playlists", {}).get("items", [])
        user_id = _get_current_user_id()
        return [
            {
                "uri": p["uri"],
                "name": p["name"],
                "description": p.get("description", ""),
                "tracks_total": p.get("tracks", {}).get("total", 0),
                "is_own": p.get("owner", {}).get("id") == user_id,
            }
            for p in playlists
            if p is not None
        ]
    except Exception:
        return []



def get_my_playlists(limit: int = 50) -> list[dict]:
    """Get the current user's own playlists.

    Returns list of dicts with keys: uri, name, description, tracks_total.
    """
    try:
        sp = _get_spotify_client()
        results = sp.current_user_playlists(limit=limit)
        playlists = results.get("items", [])
        return [
            {
                "uri": p["uri"],
                "name": p["name"],
                "description": p.get("description", ""),
                "tracks_total": p.get("tracks", {}).get("total", 0),
            }
            for p in playlists
            if p is not None
        ]
    except Exception:
        return []


def search_my_playlists(query: str) -> list[dict]:
    """Search the user's own playlists by keyword matching on name/description."""
    all_playlists = get_my_playlists()
    query_lower = query.lower()
    keywords = query_lower.split()

    scored: list[tuple[int, dict]] = []
    for p in all_playlists:
        name_lower = p["name"].lower()
        desc_lower = p["description"].lower()
        score = 0
        for kw in keywords:
            if kw in name_lower:
                score += 2
            if kw in desc_lower:
                score += 1
        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


# ---------------------------------------------------------------------------
# Search & Play (Web API)
# ---------------------------------------------------------------------------

def search_and_play_track(query: str) -> str:
    """Search for a track and play it."""
    sp = _get_spotify_client()
    results = sp.search(q=query, type="track", limit=5)
    tracks = results["tracks"]["items"]
    if not tracks:
        return f"No tracks found for: {query}"

    track = tracks[0]
    uri = track["uri"]
    osascript(f'play track "{uri}"')
    time.sleep(1)
    return f'Now playing: {track["name"]} by {track["artists"][0]["name"]} [{track["album"]["name"]}]'


def search_and_play_artist(query: str) -> str:
    """Search for an artist and play their top tracks."""
    sp = _get_spotify_client()
    results = sp.search(q=query, type="artist", limit=5)
    artists = results["artists"]["items"]
    if not artists:
        return f"No artists found for: {query}"

    artist = artists[0]
    uri = artist["uri"]
    osascript(f'play track "{uri}"')
    time.sleep(1)
    info = current_track_summary()
    return f'Now playing {artist["name"]}: {info}'


def search_and_play_playlist(query: str) -> str:
    """Search for a playlist and play it."""
    sp = _get_spotify_client()
    results = sp.search(q=query, type="playlist", limit=5)
    playlists = results["playlists"]["items"]
    if not playlists:
        return f"No playlists found for: {query}"

    playlist = playlists[0]
    uri = playlist["uri"]
    set_shuffle(True)
    osascript(f'play track "{uri}"')
    time.sleep(1)
    info = current_track_summary()
    return f'Now playing playlist "{playlist["name"]}": {info}'


def search_and_play_auto(query: str) -> str:
    """Smart search: try artist first, then track, then playlist."""
    sp = _get_spotify_client()

    # まずアーティスト検索
    results = sp.search(q=query, type="artist", limit=3)
    artists = results["artists"]["items"]
    for artist in artists:
        if query.lower() in artist["name"].lower() or artist["name"].lower() in query.lower():
            uri = artist["uri"]
            osascript(f'play track "{uri}"')
            time.sleep(1)
            info = current_track_summary()
            return f'Artist match: {artist["name"]}\n{info}'

    # 次にトラック検索
    results = sp.search(q=query, type="track", limit=3)
    tracks = results["tracks"]["items"]
    if tracks:
        track = tracks[0]
        uri = track["uri"]
        osascript(f'play track "{uri}"')
        time.sleep(1)
        return f'Now playing: {track["name"]} by {track["artists"][0]["name"]}'

    # 最後にプレイリスト検索
    results = sp.search(q=query, type="playlist", limit=3)
    playlists = results["playlists"]["items"]
    if playlists:
        playlist = playlists[0]
        uri = playlist["uri"]
        set_shuffle(True)
        osascript(f'play track "{uri}"')
        time.sleep(1)
        info = current_track_summary()
        return f'Playlist: "{playlist["name"]}"\n{info}'

    return f"No results found for: {query}"


# ---------------------------------------------------------------------------
# Basic Playback (AppleScript)
# ---------------------------------------------------------------------------

def play() -> str:
    return osascript("play")


def pause() -> str:
    return osascript("pause")


def toggle() -> str:
    return osascript("playpause")


def next_track() -> str:
    return osascript("next track")


def prev_track() -> str:
    return osascript("previous track")


def play_uri(uri: str) -> str:
    """Play a Spotify URI (track, album, playlist, artist)."""
    osascript(f'play track "{uri}"')
    time.sleep(1)
    return current_track_summary()


def play_playlist(uri: str) -> str:
    """Play a Spotify playlist URI with shuffle enabled."""
    set_shuffle(True)
    osascript(f'play track "{uri}"')
    time.sleep(1)
    return f"Now playing: {current_track_summary()}"


# ---------------------------------------------------------------------------
# Track Info
# ---------------------------------------------------------------------------

def current_track_info() -> dict:
    """Get current track details as a dict."""
    return {
        "name": osascript("name of current track"),
        "artist": osascript("artist of current track"),
        "album": osascript("album of current track"),
        "duration_ms": osascript("duration of current track"),
        "position": osascript("player position"),
        "uri": osascript("spotify url of current track"),
    }


def current_track_summary() -> str:
    """Get a human-readable summary of the current track."""
    info = current_track_info()
    try:
        dur_sec = int(info["duration_ms"]) // 1000
        pos_sec = int(float(info["position"]))
        time_str = f" ({pos_sec}s / {dur_sec}s)"
    except (ValueError, TypeError):
        time_str = ""
    return f'{info["name"]} by {info["artist"]} [{info["album"]}]{time_str}'


# ---------------------------------------------------------------------------
# Volume & Controls
# ---------------------------------------------------------------------------

def set_volume(level: int) -> str:
    level = max(0, min(100, level))
    return osascript(f"set sound volume to {level}")


def get_volume() -> str:
    return osascript("sound volume")


def seek(seconds: float) -> str:
    return osascript(f"set player position to {seconds}")


def set_shuffle(on: bool) -> str:
    val = "true" if on else "false"
    return osascript(f"set shuffling to {val}")


def set_repeat(on: bool) -> str:
    val = "true" if on else "false"
    return osascript(f"set repeating to {val}")


def is_shuffling() -> bool:
    return osascript("shuffling").lower() == "true"


def is_repeating() -> bool:
    return osascript("repeating").lower() == "true"


def fade_volume(target: int, steps: int = 10) -> str:
    """Gradually fade Spotify volume to target (0-100)."""
    target = max(0, min(100, target))
    current_str = get_volume()
    try:
        current = int(current_str)
    except ValueError:
        return f"Could not read volume: {current_str}"

    step_size = (target - current) / steps
    for i in range(1, steps + 1):
        vol = int(current + step_size * i)
        osascript(f"set sound volume to {vol}")
        subprocess.run(["sleep", "0.1"])

    osascript(f"set sound volume to {target}")
    return f"Volume faded {current} → {target}"


def set_system_volume(level: int) -> str:
    level = max(0, min(100, level))
    osascript_raw(f"set volume output volume {level}")
    return f"System volume set to {level}"
