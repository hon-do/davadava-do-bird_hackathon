"""Smart music recommendation engine.

Spotify Recommendations API を使い、ユーザーの嗜好 + コンテキスト
(目的地, 気分, タスク, 移動時間, 時間帯) から最適な曲を推薦する。

推薦の優先順位:
1. ユーザーのトップアーティスト/トラックをシードに Recommendations API
2. ジャンルシードで Recommendations API
3. Spotify プレイリスト検索
4. 固定プレイリスト (最終フォールバック)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    genre: str
    playlist_uri: str
    description: str = ""
    tracks: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# コンテキスト → Audio Features マッピング
#
# Spotify audio features:
#   energy (0-1): 曲の激しさ
#   valence (0-1): 明るさ/ポジティブさ
#   danceability (0-1): 踊りやすさ
#   tempo (BPM): テンポ
#   acousticness (0-1): アコースティック度
#   instrumentalness (0-1): インスト度
# ---------------------------------------------------------------------------

DRIVE_AUDIO_PROFILES: dict[str, dict] = {
    "beach": {
        "target_energy": 0.7, "target_valence": 0.8,
        "target_danceability": 0.7, "min_tempo": 100,
        "genres": ["pop", "reggae", "summer"],
    },
    "mountain": {
        "target_energy": 0.5, "target_valence": 0.6,
        "target_acousticness": 0.5, "min_tempo": 90,
        "genres": ["folk", "country", "rock"],
    },
    "city": {
        "target_energy": 0.7, "target_valence": 0.6,
        "target_danceability": 0.7, "min_tempo": 110,
        "genres": ["hip-hop", "r-n-b", "pop"],
    },
    "highway": {
        "target_energy": 0.8, "target_valence": 0.7,
        "min_tempo": 120, "target_danceability": 0.6,
        "genres": ["rock", "edm", "pop"],
    },
    "countryside": {
        "target_energy": 0.4, "target_valence": 0.6,
        "target_acousticness": 0.6, "min_tempo": 80,
        "genres": ["folk", "acoustic", "jazz"],
    },
    "night_drive": {
        "target_energy": 0.4, "target_valence": 0.4,
        "target_danceability": 0.5, "max_tempo": 110,
        "genres": ["chill", "r-n-b", "electronic"],
    },
    "date": {
        "target_energy": 0.4, "target_valence": 0.6,
        "target_danceability": 0.5, "target_acousticness": 0.4,
        "genres": ["r-n-b", "jazz", "soul"],
    },
}

TASK_AUDIO_PROFILES: dict[str, dict] = {
    "focus": {
        "target_energy": 0.3, "max_valence": 0.5,
        "target_instrumentalness": 0.7, "max_speechiness": 0.1,
        "genres": ["study", "ambient", "classical"],
    },
    "exercise": {
        "target_energy": 0.9, "target_valence": 0.8,
        "target_danceability": 0.8, "min_tempo": 130,
        "genres": ["work-out", "edm", "hip-hop"],
    },
    "relax": {
        "target_energy": 0.2, "target_valence": 0.4,
        "target_acousticness": 0.7, "max_tempo": 100,
        "genres": ["ambient", "chill", "acoustic"],
    },
    "creative": {
        "target_energy": 0.5, "target_valence": 0.6,
        "target_instrumentalness": 0.4,
        "genres": ["indie", "alternative", "electronic"],
    },
    "meeting": {
        "target_energy": 0.2, "target_instrumentalness": 0.8,
        "max_speechiness": 0.05, "max_tempo": 100,
        "genres": ["ambient", "classical", "jazz"],
    },
}

MOOD_AUDIO_PROFILES: dict[str, dict] = {
    "high": {
        "target_energy": 0.8, "target_valence": 0.9,
        "target_danceability": 0.7, "min_tempo": 115,
        "genres": ["pop", "dance", "happy"],
    },
    "low": {
        "target_energy": 0.4, "target_valence": 0.5,
        "target_acousticness": 0.4,
        "genres": ["acoustic", "soul", "folk"],
    },
    "neutral": {
        "target_energy": 0.5, "target_valence": 0.5,
        "genres": ["pop", "indie", "chill"],
    },
    "stressed": {
        "target_energy": 0.2, "target_valence": 0.3,
        "target_acousticness": 0.6, "target_instrumentalness": 0.5,
        "genres": ["ambient", "chill", "classical"],
    },
    "excited": {
        "target_energy": 0.9, "target_valence": 0.9,
        "target_danceability": 0.8, "min_tempo": 125,
        "genres": ["edm", "dance", "party"],
    },
}

# 移動時間による補正
DURATION_MODIFIERS: dict[str, dict] = {
    "short": {"target_energy": 0.1},    # 短距離: ちょっとエネルギーUP
    "medium": {},                         # 中距離: 補正なし
    "long": {"target_energy": -0.1, "target_valence": -0.05},  # 長距離: やや落ち着く
}

# 時間帯による補正
TIME_MODIFIERS: dict[str, dict] = {
    "morning": {"target_energy": 0.05, "target_valence": 0.1},
    "afternoon": {},
    "evening": {"target_energy": -0.05, "target_valence": -0.05},
    "night": {"target_energy": -0.15, "target_valence": -0.1},
}


# ---------------------------------------------------------------------------
# Audio features の合成
# ---------------------------------------------------------------------------

def _merge_profiles(*profiles: dict) -> tuple[list[str], dict]:
    """複数のプロファイルを合成し、(genres, audio_features) を返す。

    target_* は平均、min_* は最大、max_* は最小を取る。
    modifier の場合は加算する。
    """
    genres: list[str] = []
    features: dict[str, float] = {}
    counts: dict[str, int] = {}

    for profile in profiles:
        if not profile:
            continue
        for g in profile.get("genres", []):
            if g not in genres:
                genres.append(g)
        for k, v in profile.items():
            if k == "genres":
                continue
            if k.startswith("target_"):
                features[k] = features.get(k, 0) + v
                counts[k] = counts.get(k, 0) + 1
            elif k.startswith("min_"):
                features[k] = max(features.get(k, 0), v)
            elif k.startswith("max_"):
                features[k] = min(features.get(k, float("inf")), v)

    # target は平均
    for k in list(features.keys()):
        if k.startswith("target_") and k in counts and counts[k] > 1:
            features[k] = features[k] / counts[k]

    # 0-1 範囲にクランプ
    for k in list(features.keys()):
        if k.startswith(("target_", "min_", "max_")) and "tempo" not in k:
            features[k] = max(0.0, min(1.0, features[k]))

    return genres[:5], features  # ジャンルは最大5個


def _apply_modifier(features: dict, modifier: dict) -> dict:
    """modifier (加減算) を features に適用する。"""
    result = dict(features)
    for k, delta in modifier.items():
        if k == "genres":
            continue
        base_key = k  # target_energy etc
        if base_key in result:
            result[base_key] = result[base_key] + delta
            if "tempo" not in base_key:
                result[base_key] = max(0.0, min(1.0, result[base_key]))
    return result


# ---------------------------------------------------------------------------
# 固定プレイリスト (最終フォールバック)
# ---------------------------------------------------------------------------

FALLBACK_PLAYLISTS: dict[str, list[Recommendation]] = {
    "beach": [Recommendation("summer", "spotify:playlist:37i9dQZF1DXdPec7aLTmlC", "Summer Hits")],
    "mountain": [Recommendation("folk", "spotify:playlist:37i9dQZF1DXaUDcU6KDCGg", "Folk & Acoustic")],
    "city": [Recommendation("hip-hop", "spotify:playlist:37i9dQZF1DX0XUsuxWHRQd", "Hip-Hop")],
    "highway": [Recommendation("rock", "spotify:playlist:37i9dQZF1DWXRqgorJj26U", "Rock Classics")],
    "countryside": [Recommendation("acoustic", "spotify:playlist:37i9dQZF1DX4E3UdUs7fUx", "Acoustic Chill")],
    "night_drive": [Recommendation("lo-fi", "spotify:playlist:37i9dQZF1DWWQRwui0ExPn", "Lo-Fi Beats")],
    "date": [Recommendation("r&b", "spotify:playlist:37i9dQZF1DX4SBhb3fqCJd", "R&B")],
    "focus": [Recommendation("lo-fi", "spotify:playlist:0vvXsWCC9xrXsKd4FyS8kM", "Lo-Fi Beats")],
    "exercise": [Recommendation("workout", "spotify:playlist:37i9dQZF1DX76Wlfdnj7AP", "Workout")],
    "relax": [Recommendation("chill", "spotify:playlist:37i9dQZF1DX4WYpdgoIcn6", "Chill Hits")],
    "creative": [Recommendation("indie", "spotify:playlist:37i9dQZF1DX2Nc3B70tvx0", "Indie Mix")],
    "default": [Recommendation("pop", "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", "Today's Top Hits")],
}


# ---------------------------------------------------------------------------
# メイン推薦ロジック
# ---------------------------------------------------------------------------

def _smart_recommend(
    genres: list[str],
    audio_features: dict,
    context_label: str,
    fallback_key: str = "default",
) -> Recommendation:
    """ユーザー嗜好 × コンテキストでプレイリスト検索 → 固定フォールバック。

    1. ユーザーのトップアーティスト名 + コンテキストジャンルで検索
    2. コンテキストジャンルのみで検索
    3. ジャンル単体で検索
    4. 固定フォールバック
    """
    from spotify import (
        get_top_artists,
        search_playlists,
        search_my_playlists,
    )

    # ユーザーのトップアーティスト名（推薦の個人化に使う）
    top_artists = get_top_artists(5)
    artist_names = [a["name"] for a in top_artists[:3]]

    # 検索クエリを複数段階で構築
    genre_str = " ".join(genres[:3])
    queries = []

    # 1) ユーザーの好きなアーティスト + コンテキスト
    if artist_names:
        queries.append(f"{artist_names[0]} {genre_str} mix")
        queries.append(f"{artist_names[0]} {genres[0] if genres else 'mix'}")

    # 2) コンテキストジャンルで検索
    queries.append(f"{genre_str} playlist")
    queries.append(f"{genre_str} mix")

    # 3) ジャンル単体
    if genres:
        queries.append(genres[0])

    # Spotify 検索（ユーザーのプレイリストが結果に含まれていたら優先）
    for q in queries:
        playlists = search_playlists(q, limit=10)
        if not playlists:
            continue

        # ユーザー自身のプレイリストがあれば優先
        own = [p for p in playlists if p.get("is_own")]
        if own:
            return Recommendation(
                genre=genres[0] if genres else "mix",
                playlist_uri=own[0]["uri"],
                description=f"{context_label}: {own[0]['name']}",
            )

        # 曲数が十分なプレイリストを選択
        good = [p for p in playlists if p["tracks_total"] >= 20]
        if not good:
            good = [p for p in playlists if p["tracks_total"] >= 5]
        if not good:
            good = playlists
        pick = random.choice(good[:5])
        return Recommendation(
            genre=genres[0] if genres else "mix",
            playlist_uri=pick["uri"],
            description=f"{context_label}: {pick['name']}",
        )

    # 固定フォールバック
    fallback = FALLBACK_PLAYLISTS.get(fallback_key, FALLBACK_PLAYLISTS["default"])
    return random.choice(fallback)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def recommend_drive_music(
    destination: str,
    mood: str = "",
    time_of_day: str = "",
) -> Recommendation:
    """目的地 + 気分 + 時間帯から最適な曲を推薦。"""
    dest_key = destination.lower().strip()
    mood_key = mood.lower().strip()
    time_key = time_of_day.lower().strip()

    dest_profile = DRIVE_AUDIO_PROFILES.get(dest_key, DRIVE_AUDIO_PROFILES["highway"])
    mood_profile = MOOD_AUDIO_PROFILES.get(mood_key, {})
    time_mod = TIME_MODIFIERS.get(time_key, {})

    genres, features = _merge_profiles(dest_profile, mood_profile)
    features = _apply_modifier(features, time_mod)

    label = f"{destination}ドライブ"
    if mood:
        label += f" ({mood})"
    return _smart_recommend(genres, features, label, dest_key)


def recommend_drive_music_for_trip(
    destination: str,
    duration_minutes: int,
    mood: str = "",
    time_of_day: str = "",
) -> Recommendation:
    """ルート情報 + 目的地 + 気分 + 時間帯から推薦。"""
    dest_key = destination.lower().strip()
    mood_key = mood.lower().strip()
    time_key = time_of_day.lower().strip()

    dest_profile = DRIVE_AUDIO_PROFILES.get(dest_key, DRIVE_AUDIO_PROFILES["highway"])
    mood_profile = MOOD_AUDIO_PROFILES.get(mood_key, {})
    time_mod = TIME_MODIFIERS.get(time_key, {})

    if duration_minutes <= 30:
        dur_mod = DURATION_MODIFIERS["short"]
    elif duration_minutes <= 90:
        dur_mod = DURATION_MODIFIERS["medium"]
    else:
        dur_mod = DURATION_MODIFIERS["long"]

    genres, features = _merge_profiles(dest_profile, mood_profile)
    features = _apply_modifier(features, time_mod)
    features = _apply_modifier(features, dur_mod)

    label = f"{destination}ドライブ ({duration_minutes}分)"
    if mood:
        label += f" [{mood}]"
    return _smart_recommend(genres, features, label, dest_key)


def recommend_task_music(
    task: str,
    motivation: str = "",
) -> Recommendation:
    """タスク + モチベーションから最適な曲を推薦。"""
    task_key = task.lower().strip()
    motiv_key = motivation.lower().strip()

    task_profile = TASK_AUDIO_PROFILES.get(task_key, TASK_AUDIO_PROFILES["focus"])
    mood_profile = MOOD_AUDIO_PROFILES.get(motiv_key, {})

    genres, features = _merge_profiles(task_profile, mood_profile)

    label = f"{task}向け"
    if motivation:
        label += f" ({motivation})"
    return _smart_recommend(genres, features, label, task_key)


def recommend_for_motivation(level: str) -> Recommendation:
    """気分/モチベーションから推薦。"""
    key = level.lower().strip()
    profile = MOOD_AUDIO_PROFILES.get(key, MOOD_AUDIO_PROFILES["neutral"])
    genres = profile.get("genres", ["pop"])
    features = {k: v for k, v in profile.items() if k != "genres"}
    return _smart_recommend(genres, features, f"{level} mood", "default")
