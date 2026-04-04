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
        scope="user-modify-playback-state user-read-playback-state user-read-currently-playing",
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


def _escape_applescript_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def play_playlist_by_name(name: str) -> str:
    """Play a playlist by name from the user's Spotify library."""
    escaped = _escape_applescript_string(name.strip())
    if not escaped:
        return "Playlist name is empty"

    script = f'''
tell application "Spotify"
    try
        set targetPlaylist to first playlist whose name is "{escaped}"
        set targetUri to spotify url of targetPlaylist
        play track targetUri
        return "Playing playlist: " & (name of targetPlaylist) & " (" & targetUri & ")"
    on error errMsg
        return "ERROR: " & errMsg
    end try
end tell
'''
    result = osascript_raw(script)
    if result.startswith("ERROR:"):
        return (
            f'Could not find playlist "{name}" in your Spotify library. '
            "Try follow/save the playlist first, or play by Spotify URI."
        )
    return result


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
