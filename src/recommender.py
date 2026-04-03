"""Music recommendation engine based on mood, task, and driving context."""

from __future__ import annotations

import random
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    genre: str
    playlist_uri: str
    description: str = ""


# ---------------------------------------------------------------------------
# Spotify公式プレイリスト URI マッピング
# ---------------------------------------------------------------------------

# タスク別
TASK_MAP: dict[str, list[Recommendation]] = {
    "focus": [
        Recommendation("lo-fi", "spotify:playlist:0vvXsWCC9xrXsKd4FyS8kM", "集中作業向けの Lo-Fi Beats"),
        Recommendation("ambient", "spotify:playlist:37i9dQZF1DX3Ogo9pFvBkY", "環境音楽で深い集中"),
        Recommendation("classical", "spotify:playlist:37i9dQZF1DWWEJlAGA9gs0", "クラシック音楽で知的作業"),
    ],
    "exercise": [
        Recommendation("workout", "spotify:playlist:37i9dQZF1DX76Wlfdnj7AP", "ハイエネルギーなワークアウト"),
        Recommendation("hip-hop", "spotify:playlist:37i9dQZF1DX0BcQWzuB7ZO", "テンポの良いヒップホップ"),
        Recommendation("power", "spotify:playlist:37i9dQZF1DX32NsLKyzScr", "パワフルなロックでモチベUP"),
    ],
    "relax": [
        Recommendation("acoustic", "spotify:playlist:37i9dQZF1DX4E3UdUs7fUx", "アコースティックでリラックス"),
        Recommendation("jazz", "spotify:playlist:37i9dQZF1DX0SM0LYsmbMT", "スムースジャズで癒しの時間"),
        Recommendation("chill", "spotify:playlist:37i9dQZF1DX4WYpdgoIcn6", "Chillでリフレッシュ"),
    ],
    "creative": [
        Recommendation("indie", "spotify:playlist:37i9dQZF1DX2Nc3B70tvx0", "インディーで創造力を刺激"),
        Recommendation("electronic", "spotify:playlist:37i9dQZF1DX6J5NfMJS675", "エレクトロニカでクリエイティブに"),
        Recommendation("alternative", "spotify:playlist:37i9dQZF1DX873GaRGUmPl", "オルタナで自由な発想"),
    ],
    "meeting": [
        Recommendation("lo-fi", "spotify:playlist:37i9dQZF1DWWQRwui0ExPn", "会議前のリラックスBGM"),
    ],
}

# モチベーション別
MOTIVATION_MAP: dict[str, list[Recommendation]] = {
    "high": [
        Recommendation("pop hits", "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", "テンション高めのポップヒッツ"),
        Recommendation("dance", "spotify:playlist:37i9dQZF1DX4JAvHpjipBk", "ノリノリのダンスミュージック"),
    ],
    "low": [
        Recommendation("acoustic", "spotify:playlist:37i9dQZF1DX4E3UdUs7fUx", "優しいアコースティックで気分を上げる"),
        Recommendation("feel good", "spotify:playlist:37i9dQZF1DX3rxVfibe1L0", "フィールグッドで元気に"),
    ],
    "neutral": [
        Recommendation("chill hits", "spotify:playlist:37i9dQZF1DX4WYpdgoIcn6", "日常にフィットするChill"),
        Recommendation("indie pop", "spotify:playlist:37i9dQZF1DX2Nc3B70tvx0", "ゆったりインディーポップ"),
    ],
    "stressed": [
        Recommendation("peaceful", "spotify:playlist:37i9dQZF1DWZqd5JBER9Ig", "ストレス解消のピースフルBGM"),
        Recommendation("nature", "spotify:playlist:37i9dQZF1DX4PP3DA4J0N8", "自然音でストレスを和らげる"),
    ],
    "excited": [
        Recommendation("edm", "spotify:playlist:37i9dQZF1DX1kCIzMYtzum", "フェス気分のEDM"),
        Recommendation("rock anthem", "spotify:playlist:37i9dQZF1DWXRqgorJj26U", "アンセムロックで最高潮に"),
    ],
}

# ドライブ目的地別
DRIVE_DESTINATION_MAP: dict[str, list[Recommendation]] = {
    "beach": [
        Recommendation("summer", "spotify:playlist:37i9dQZF1DXdPec7aLTmlC", "ビーチドライブにサマーヒッツ"),
        Recommendation("tropical", "spotify:playlist:37i9dQZF1DX0UKk1LMOjmR", "トロピカルで南国気分"),
        Recommendation("feel good", "spotify:playlist:37i9dQZF1DX3rxVfibe1L0", "夏のフィールグッド"),
    ],
    "mountain": [
        Recommendation("folk", "spotify:playlist:37i9dQZF1DXaUDcU6KDCGg", "山ドライブにフォーク"),
        Recommendation("country", "spotify:playlist:37i9dQZF1DX1lVhptIYRda", "カントリーで開放感"),
        Recommendation("classic rock", "spotify:playlist:37i9dQZF1DWXRqgorJj26U", "クラシックロックで山道を"),
    ],
    "city": [
        Recommendation("hip-hop", "spotify:playlist:37i9dQZF1DX0XUsuxWHRQd", "シティドライブにヒップホップ"),
        Recommendation("r&b", "spotify:playlist:37i9dQZF1DX4SBhb3fqCJd", "R&Bでシティナイト"),
        Recommendation("electronic", "spotify:playlist:37i9dQZF1DX6J5NfMJS675", "エレクトロでモダンシティ"),
    ],
    "highway": [
        Recommendation("rock", "spotify:playlist:37i9dQZF1DWXRqgorJj26U", "ハイウェイにロック"),
        Recommendation("edm", "spotify:playlist:37i9dQZF1DX1kCIzMYtzum", "高速ドライブにEDM"),
        Recommendation("road trip", "spotify:playlist:37i9dQZF1DXdPec7aLTmlC", "歌えるポップスでロードトリップ"),
    ],
    "countryside": [
        Recommendation("folk", "spotify:playlist:37i9dQZF1DXaUDcU6KDCGg", "田舎道にフォーク"),
        Recommendation("jazz", "spotify:playlist:37i9dQZF1DX0SM0LYsmbMT", "ジャズで優雅なドライブ"),
        Recommendation("acoustic", "spotify:playlist:37i9dQZF1DX4E3UdUs7fUx", "アコースティックでのんびり"),
    ],
    "night_drive": [
        Recommendation("lo-fi", "spotify:playlist:37i9dQZF1DWWQRwui0ExPn", "夜のドライブにlo-fi"),
        Recommendation("r&b", "spotify:playlist:37i9dQZF1DX4SBhb3fqCJd", "ムーディーなR&Bで夜道"),
        Recommendation("synthwave", "spotify:playlist:37i9dQZF1DXdLEN7aqioXM", "シンセウェーブで夜の街"),
    ],
    "date": [
        Recommendation("r&b", "spotify:playlist:37i9dQZF1DX4SBhb3fqCJd", "デートドライブにR&B"),
        Recommendation("romantic", "spotify:playlist:37i9dQZF1DX50QitC6Oqtn", "ロマンチックなポップス"),
        Recommendation("jazz", "spotify:playlist:37i9dQZF1DX0SM0LYsmbMT", "ジャズでロマンチックに"),
    ],
}

# 移動時間別
DRIVE_DURATION_MAP: dict[str, list[Recommendation]] = {
    "short": [
        Recommendation("quick pop", "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", "短距離向けのキャッチーなヒット曲"),
        Recommendation("urban beats", "spotify:playlist:37i9dQZF1DX0XUsuxWHRQd", "街中移動に合う軽快なビート"),
    ],
    "medium": [
        Recommendation("road trip", "spotify:playlist:37i9dQZF1DXdPec7aLTmlC", "中距離ドライブ向けロードトリップ"),
        Recommendation("chill drive", "spotify:playlist:37i9dQZF1DX4WYpdgoIcn6", "流し聴きしやすいチル系"),
    ],
    "long": [
        Recommendation("long drive rock", "spotify:playlist:37i9dQZF1DWXRqgorJj26U", "長距離ドライブ向けロック"),
        Recommendation("epic journey", "spotify:playlist:37i9dQZF1DX1kCIzMYtzum", "長時間でも飽きにくい高揚感"),
    ],
}


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------

def recommend_for_task(task: str) -> Recommendation:
    """Get a recommendation based on task type."""
    key = task.lower().strip()
    candidates = TASK_MAP.get(key, TASK_MAP["focus"])
    return random.choice(candidates)


def recommend_for_motivation(level: str) -> Recommendation:
    """Get a recommendation based on motivation level."""
    key = level.lower().strip()
    candidates = MOTIVATION_MAP.get(key, MOTIVATION_MAP["neutral"])
    return random.choice(candidates)


def recommend_for_drive(destination: str) -> Recommendation:
    """Get a recommendation based on driving destination."""
    key = destination.lower().strip()
    for map_key, candidates in DRIVE_DESTINATION_MAP.items():
        if map_key in key or key in map_key:
            return random.choice(candidates)
    return random.choice(DRIVE_DESTINATION_MAP["highway"])


def recommend_for_drive_duration(duration_minutes: int) -> Recommendation:
    """Get a recommendation based on trip length."""
    if duration_minutes <= 30:
        return random.choice(DRIVE_DURATION_MAP["short"])
    if duration_minutes <= 90:
        return random.choice(DRIVE_DURATION_MAP["medium"])
    return random.choice(DRIVE_DURATION_MAP["long"])


def recommend_drive_music(
    destination: str,
    mood: str = "",
) -> Recommendation:
    """Smart recommendation combining destination and mood."""
    key = destination.lower().strip()
    has_destination_match = any(
        map_key in key or key in map_key
        for map_key in DRIVE_DESTINATION_MAP
    )
    if mood and not has_destination_match:
        return recommend_for_motivation(mood)
    return recommend_for_drive(destination)


def recommend_drive_music_for_trip(
    destination: str,
    duration_minutes: int,
    mood: str = "",
) -> Recommendation:
    """Route-aware drive recommendation based on destination and trip length."""
    destination_rec = recommend_for_drive(destination)
    duration_rec = recommend_for_drive_duration(duration_minutes)

    # 長めの移動は時間重視、それ以外は目的地の雰囲気を優先
    if duration_minutes >= 45:
        chosen = duration_rec
        reason = f"移動時間 {duration_minutes} 分に合わせた選曲"
    else:
        chosen = destination_rec
        reason = f"目的地 {destination} に合わせた選曲"

    # mood が指定されていて目的地も時間もピンとこない場合は mood を優先
    if mood and not any(
        k in destination.lower() or destination.lower() in k
        for k in DRIVE_DESTINATION_MAP
    ) and duration_minutes < 45:
        mood_rec = recommend_for_motivation(mood)
        chosen = mood_rec
        reason = f"ムード ({mood}) に合わせた選曲"

    return Recommendation(
        genre=chosen.genre,
        playlist_uri=chosen.playlist_uri,
        description=f"{chosen.description} / {reason}",
    )


def recommend_task_music(
    task: str,
    motivation: str = "",
) -> Recommendation:
    """Smart recommendation combining task and motivation."""
    key = task.lower().strip()
    if motivation and key not in TASK_MAP:
        return recommend_for_motivation(motivation)
    return recommend_for_task(task)
