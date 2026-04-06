"""davadava - Voice-controlled DJ MCP Server.

VoiceOS からの音声コマンドで Spotify を操作し、
タスク・モチベーション・ドライブの目的地に応じた曲を推薦・再生する。
"""

import subprocess
from urllib.parse import urlencode
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from mcp.server.fastmcp import FastMCP

from spotify import (
    play,
    pause,
    toggle,
    next_track,
    prev_track,
    play_uri,
    play_playlist,
    play_playlist_by_name,
    current_track_summary,
    set_volume,
    get_volume,
    fade_volume,
    seek,
    set_shuffle,
    set_repeat,
    set_system_volume,
    search_and_play_auto,
    search_and_play_track,
    search_and_play_artist,
    search_and_play_playlist,
    play_recommended_tracks,
)
from recommender import (
    recommend_drive_music,
    recommend_drive_music_for_trip,
    recommend_task_music,
    recommend_for_motivation,
)
from maps import get_drive_route_summary, MapsError
from anthropic_eta import (
    AnthropicETAError,
    AnthropicSelectionError,
    build_eta_prompt,
    build_playlist_selection_prompt,
    choose_playlist_with_anthropic,
    estimate_drive_time_with_anthropic,
)
from spotify_web import search_spotify_playlists, SpotifySearchError

mcp = FastMCP("davadava-dj")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_time_of_day() -> str:
    """現在の時間帯を返す。"""
    hour = datetime.now().hour
    if 5 <= hour < 11:
        return "morning"
    elif 11 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"


def _open_spotify_app() -> str:
    """Launch Spotify app on macOS."""
    try:
        subprocess.run(["open", "-a", "Spotify"], check=True, capture_output=True, text=True)
        return "Spotify opened"
    except Exception as exc:
        return f"Spotify open failed: {exc}"


def _open_google_maps_directions(origin: str, destination: str) -> str:
    """Open browser Google Maps directions page."""
    params = urlencode(
        {
            "api": 1,
            "origin": origin,
            "destination": destination,
            "travelmode": "driving",
        }
    )
    url = f"https://www.google.com/maps/dir/?{params}"
    try:
        subprocess.run(["open", url], check=True, capture_output=True, text=True)
        return f"Google Maps opened: {url}"
    except Exception as exc:
        return f"Google Maps open failed: {exc}"


def _play_recommendation(rec) -> str:
    """Recommendation の内容に応じて再生する共通ヘルパー。"""
    if rec.tracks:
        from spotify import osascript
        import time as _time
        osascript(f'play track "{rec.tracks[0]["uri"]}"')
        _time.sleep(1)
        return current_track_summary()
    else:
        return play_playlist(rec.playlist_uri)


# =========================================================================
# Basic Playback Controls
# =========================================================================

@mcp.tool()
def resume_playback() -> str:
    """Resume playing music. Use when asked to play or continue music."""
    return play()


@mcp.tool()
def pause_playback() -> str:
    """Pause the currently playing music."""
    return pause()


@mcp.tool()
def toggle_play_pause() -> str:
    """Toggle between play and pause."""
    return toggle()


@mcp.tool()
def next_song() -> str:
    """Skip to the next song."""
    return next_track()


@mcp.tool()
def previous_song() -> str:
    """Go back to the previous song."""
    return prev_track()


@mcp.tool()
def now_playing() -> str:
    """Get information about the currently playing song, including title, artist, and album."""
    return current_track_summary()


# =========================================================================
# Volume & Playback Settings
# =========================================================================

@mcp.tool()
def change_volume(level: int) -> str:
    """Set the music volume. Level is 0 to 100."""
    return set_volume(level)


@mcp.tool()
def check_volume() -> str:
    """Check the current volume level."""
    return f"Current volume: {get_volume()}"


@mcp.tool()
def smooth_fade(target_volume: int) -> str:
    """Smoothly fade the volume to a target level (0-100). Good for transitions."""
    return fade_volume(target_volume)


@mcp.tool()
def jump_to_position(seconds: float) -> str:
    """Jump to a specific position in the current song (in seconds)."""
    return seek(seconds)


@mcp.tool()
def shuffle_on() -> str:
    """Turn on shuffle mode to randomize playback order."""
    set_shuffle(True)
    return "Shuffle is now ON"


@mcp.tool()
def shuffle_off() -> str:
    """Turn off shuffle mode."""
    set_shuffle(False)
    return "Shuffle is now OFF"


@mcp.tool()
def repeat_on() -> str:
    """Turn on repeat mode."""
    set_repeat(True)
    return "Repeat is now ON"


@mcp.tool()
def repeat_off() -> str:
    """Turn off repeat mode."""
    set_repeat(False)
    return "Repeat is now OFF"


@mcp.tool()
def change_system_volume(level: int) -> str:
    """Set the Mac system volume (0-100). Different from Spotify volume."""
    return set_system_volume(level)


# =========================================================================
# Smart Recommendations - Driving (Google Maps)
# =========================================================================

@mcp.tool()
def drive_music(destination: str, mood: str = "") -> str:
    """Recommend and play music for driving based on destination type.

    Destination types: beach, mountain, city, highway, countryside, night_drive, date.
    Mood examples: high, low, neutral, stressed, excited.

    Uses your Spotify listening history to personalize recommendations.
    Also considers the current time of day (night -> chill, morning -> fresh).
    """
    time_of_day = _get_time_of_day()
    if time_of_day == "night" and destination not in ("night_drive", "date"):
        destination = "night_drive"

    rec = recommend_drive_music(destination, mood, time_of_day)
    result = _play_recommendation(rec)
    return f"{rec.description} ({rec.genre})\n{result}"


@mcp.tool()
def beach_drive_music() -> str:
    """Play upbeat beach/summer music for a drive to the beach or coast."""
    return drive_music("beach", "high")


@mcp.tool()
def night_drive_music() -> str:
    """Play chill, atmospheric music for driving at night."""
    return drive_music("night_drive")


@mcp.tool()
def highway_drive_music() -> str:
    """Play energetic music for highway/freeway driving."""
    return drive_music("highway", "excited")


@mcp.tool()
def route_summary(origin: str, destination: str) -> str:
    """Get driving route distance and travel time from origin to destination via Google Maps."""
    try:
        route = get_drive_route_summary(origin, destination)
    except MapsError as exc:
        return f"Route lookup failed: {exc}"

    return (
        f"Route: {route.origin} -> {route.destination}\n"
        f"Distance: {route.distance_text}\n"
        f"Estimated time: {route.duration_text} ({route.duration_minutes} min)"
    )


@mcp.tool()
def drive_music_with_route(origin: str, destination: str, mood: str = "") -> str:
    """Play music for a drive using Google Maps route info.

    Looks up the actual driving time and distance, then picks a playlist
    that matches both the destination vibe and the trip length.

    Example: origin="東京駅", destination="湘南海岸"
    Use this when the user mentions both where they are and where they're going.
    """
    try:
        route = get_drive_route_summary(origin, destination)
    except MapsError as exc:
        return f"Route lookup failed: {exc}"

    time_of_day = _get_time_of_day()
    rec = recommend_drive_music_for_trip(
        destination, route.duration_minutes, mood, time_of_day,
    )
    result = _play_recommendation(rec)
    return (
        f"Route: {route.origin} -> {route.destination}\n"
        f"Distance: {route.distance_text}, Time: {route.duration_text}\n"
        f"Recommendation: {rec.description} ({rec.genre})\n"
        f"{result}"
    )


@mcp.tool()
def anthropic_eta_prompt(
    origin: str,
    destination: str,
    distance_km: float,
    departure_context: str = "",
) -> str:
    """Build the prompt used for Anthropic-based travel time estimation."""
    return build_eta_prompt(origin, destination, distance_km, departure_context)


@mcp.tool()
def predict_drive_time_with_anthropic(
    origin: str,
    destination: str,
    distance_km: float,
    departure_context: str = "",
) -> str:
    """Estimate drive time via Anthropic API using ANTHROPIC_API_KEY."""
    try:
        estimate, _ = estimate_drive_time_with_anthropic(
            origin=origin,
            destination=destination,
            distance_km=distance_km,
            departure_context=departure_context,
        )
    except AnthropicETAError as exc:
        return f"ETA prediction failed: {exc}"

    return (
        f"Predicted ETA: {estimate.minutes_mid} min "
        f"(range {estimate.minutes_low}-{estimate.minutes_high} min)\n"
        f"Confidence: {estimate.confidence}\n"
        f"Rationale: {estimate.rationale}"
    )


@mcp.tool()
def drive_music_with_predicted_time(
    origin: str,
    destination: str,
    distance_km: float,
    mood: str = "",
    departure_context: str = "",
) -> str:
    """Predict drive time via Anthropic and play a playlist matched to the predicted trip length."""
    try:
        estimate, _ = estimate_drive_time_with_anthropic(
            origin=origin,
            destination=destination,
            distance_km=distance_km,
            departure_context=departure_context,
        )
    except AnthropicETAError as exc:
        return f"ETA prediction failed: {exc}"

    rec = recommend_drive_music_for_trip(destination, estimate.minutes_mid, mood)
    result = _play_recommendation(rec)
    return (
        f"Prediction: {estimate.minutes_mid} min "
        f"(range {estimate.minutes_low}-{estimate.minutes_high} min)\n"
        f"Confidence: {estimate.confidence}\n"
        f"Recommendation: {rec.description} ({rec.genre})\n"
        f"{result}"
    )


@mcp.tool()
def start_drive_session(origin: str, destination: str, mood: str = "") -> str:
    """Open Spotify and Google Maps in one command, then play route-aware drive music."""
    spotify_open = _open_spotify_app()
    maps_open = _open_google_maps_directions(origin, destination)

    try:
        route = get_drive_route_summary(origin, destination)
        time_of_day = _get_time_of_day()
        rec = recommend_drive_music_for_trip(
            destination, route.duration_minutes, mood, time_of_day,
        )
        playback = _play_recommendation(rec)
        route_info = (
            f"Route: {route.origin} -> {route.destination}\n"
            f"Distance: {route.distance_text}, Time: {route.duration_text}"
        )
        recommendation = f"Recommendation: {rec.description} ({rec.genre})"
    except MapsError as exc:
        rec = recommend_drive_music(destination, mood)
        playback = _play_recommendation(rec)
        route_info = f"Route lookup failed: {exc}"
        recommendation = f"Fallback recommendation: {rec.description} ({rec.genre})"

    return (
        f"{spotify_open}\n"
        f"{maps_open}\n"
        f"{route_info}\n"
        f"{recommendation}\n"
        f"{playback}"
    )


# =========================================================================
# Smart Recommendations - Task & Motivation
# =========================================================================

@mcp.tool()
def task_music(task: str, motivation: str = "") -> str:
    """Recommend and play music suited to a specific task.

    Task examples: focus, exercise, relax, creative, meeting.
    Motivation examples: high, low, neutral, stressed, excited.

    Use this when the user wants music for working or an activity.
    """
    rec = recommend_task_music(task, motivation)
    result = _play_recommendation(rec)
    return f"{rec.description} ({rec.genre})\n{result}"


@mcp.tool()
def focus_music() -> str:
    """Play calm, instrumental music for focused work or studying."""
    return task_music("focus")


@mcp.tool()
def workout_music() -> str:
    """Play high-energy music for exercising or working out."""
    return task_music("exercise", "high")


@mcp.tool()
def relax_music() -> str:
    """Play soothing music for relaxation or winding down."""
    return task_music("relax", "low")


@mcp.tool()
def creative_music() -> str:
    """Play inspiring music for creative work like design, writing, or brainstorming."""
    return task_music("creative")


# =========================================================================
# Mood-based
# =========================================================================

@mcp.tool()
def mood_music(mood: str) -> str:
    """Play music matching your current mood.

    Mood examples: high, low, neutral, stressed, excited.
    """
    rec = recommend_for_motivation(mood)
    result = _play_recommendation(rec)
    return f"{rec.description} ({rec.genre})\n{result}"


@mcp.tool()
def cheer_me_up() -> str:
    """Play uplifting music to boost your mood when you're feeling down."""
    return mood_music("low")


@mcp.tool()
def hype_music() -> str:
    """Play hype/exciting music to match or boost high energy."""
    return mood_music("excited")


# =========================================================================
# Search & Play (specific artist, song, playlist)
# =========================================================================

@mcp.tool()
def search_music(query: str) -> str:
    """Search and play music by artist name, song title, or any query.

    This is the main tool for specific requests like:
    - "Play Zutomayo" -> searches for the artist and plays their music
    - "Play KICK BACK by Kenshi Yonezu" -> finds and plays that exact song
    - "Play chill jazz playlist" -> finds a matching playlist

    Use this whenever the user asks for a specific artist, song, or genre.
    """
    return search_and_play_auto(query)


@mcp.tool()
def play_artist(artist_name: str) -> str:
    """Play music by a specific artist. Searches Spotify and plays their top tracks.

    Examples: Zutomayo, YOASOBI, Kenshi Yonezu, Taylor Swift, etc.
    """
    return search_and_play_artist(artist_name)


@mcp.tool()
def play_song(song_name: str) -> str:
    """Play a specific song by title. You can include the artist name for accuracy.

    Examples: "KICK BACK Kenshi Yonezu", "Idol YOASOBI", "Shape of You"
    """
    return search_and_play_track(song_name)


@mcp.tool()
def play_a_playlist(query: str) -> str:
    """Search for a Spotify playlist and play it.

    Examples: "chill vibes", "J-pop hits", "workout mix"
    """
    return search_and_play_playlist(query)


# =========================================================================
# Direct Play
# =========================================================================

@mcp.tool()
def play_spotify_uri(uri: str) -> str:
    """Play a specific Spotify URI directly.

    Examples:
      spotify:track:6rqhFgbbKwnb9MLmUQDhG6
      spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
    """
    return play_uri(uri)


@mcp.tool()
def play_spotify_playlist_by_name(name: str) -> str:
    """Play a Spotify playlist by its name from your library."""
    return play_playlist_by_name(name)


@mcp.tool()
def search_spotify_playlists_web(query: str, limit: int = 8) -> str:
    """Search Spotify playlists via Web API (requires SPOTIFY_CLIENT_ID/SECRET)."""
    try:
        results = search_spotify_playlists(query=query, limit=limit)
    except SpotifySearchError as exc:
        return f"Spotify search failed: {exc}"

    if not results:
        return f'No playlists found for "{query}"'

    lines = []
    for i, item in enumerate(results, start=1):
        name = item.get("name", "Unknown")
        owner = item.get("owner", "Unknown")
        total = item.get("tracks_total", "?")
        uri = item.get("uri", "")
        lines.append(f"{i}. {name} (by {owner}, {total} tracks)\n   {uri}")
    return "\n".join(lines)


@mcp.tool()
def smart_playlist_search(query: str, mood: str = "") -> str:
    """Search playlists via Web API and optionally let Anthropic pick the best match."""
    try:
        results = search_spotify_playlists(query=query, limit=10)
    except SpotifySearchError as exc:
        return f"Spotify search failed: {exc}"

    if not results:
        return f'No playlists found for "{query}"'

    try:
        chosen = choose_playlist_with_anthropic(
            results, mood=mood or "general listening"
        )
    except AnthropicSelectionError:
        chosen = results[0]

    uri = chosen.get("uri", "")
    name = chosen.get("name", "Unknown")
    if not uri:
        return "Could not determine playlist URI"
    result = play_playlist(uri)
    return f"Selected: {name}\n{result}"


# =========================================================================
# Entry point
# =========================================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
