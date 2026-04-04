"""Travel-time estimation via Anthropic Messages API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from urllib.request import Request, urlopen


ANTHROPIC_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicETAError(RuntimeError):
    """Raised when Anthropic-based ETA estimation fails."""


class AnthropicSelectionError(RuntimeError):
    """Raised when Anthropic-based playlist selection fails."""


@dataclass
class TravelTimeEstimate:
    origin: str
    destination: str
    distance_km: float
    minutes_low: int
    minutes_mid: int
    minutes_high: int
    confidence: str
    rationale: str


def build_eta_prompt(
    origin: str,
    destination: str,
    distance_km: float,
    departure_context: str = "",
) -> str:
    """Build a strict JSON prompt for drive-time estimation."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    context = departure_context.strip() or "指定なし"
    return (
        "あなたは日本国内のドライブ時間を見積もるアシスタントです。\n"
        "以下の条件から、現実的な移動時間レンジを推定してください。\n\n"
        f"- 現在時刻: {now}\n"
        f"- 出発地: {origin}\n"
        f"- 目的地: {destination}\n"
        f"- 距離: {distance_km:.1f} km\n"
        f"- 補足コンテキスト: {context}\n\n"
        "推定ルール:\n"
        "- 一般道・高速道路の混在を仮定して妥当な速度帯を置く\n"
        "- 都市部/郊外/観光地の傾向を目的地名から推定する\n"
        "- 渋滞や信号待ちで下振れ/上振れの幅を持たせる\n"
        "- 分単位で返す\n\n"
        "必ずJSONのみを返してください。Markdownは禁止。\n"
        "JSON schema:\n"
        "{\n"
        '  "minutes_low": int,\n'
        '  "minutes_mid": int,\n'
        '  "minutes_high": int,\n'
        '  "confidence": "low|medium|high",\n'
        '  "rationale": "string"\n'
        "}"
    )


def _extract_text(response_payload: dict) -> str:
    content = response_payload.get("content", [])
    texts: list[str] = []
    for block in content:
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
    return "\n".join(texts).strip()


def estimate_drive_time_with_anthropic(
    origin: str,
    destination: str,
    distance_km: float,
    departure_context: str = "",
) -> tuple[TravelTimeEstimate, str]:
    """Call Anthropic API and return ETA estimate with the prompt used."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise AnthropicETAError("ANTHROPIC_API_KEY is not set")

    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest").strip()
    prompt = build_eta_prompt(origin, destination, distance_km, departure_context)
    payload = {
        "model": model,
        "max_tokens": 350,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    request = Request(
        ANTHROPIC_MESSAGES_ENDPOINT,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            response_payload = json.loads(raw)
    except Exception as exc:
        raise AnthropicETAError(f"Failed to call Anthropic API: {exc}") from exc

    text = _extract_text(response_payload)
    if not text:
        raise AnthropicETAError("Anthropic response did not include text content")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnthropicETAError(
            f"Anthropic response was not valid JSON: {text[:200]}"
        ) from exc

    try:
        estimate = TravelTimeEstimate(
            origin=origin,
            destination=destination,
            distance_km=float(distance_km),
            minutes_low=int(data["minutes_low"]),
            minutes_mid=int(data["minutes_mid"]),
            minutes_high=int(data["minutes_high"]),
            confidence=str(data["confidence"]),
            rationale=str(data["rationale"]),
        )
    except Exception as exc:
        raise AnthropicETAError(f"Anthropic JSON schema mismatch: {data}") from exc

    if not (0 < estimate.minutes_low <= estimate.minutes_mid <= estimate.minutes_high):
        raise AnthropicETAError(
            "Invalid ETA range: expected low <= mid <= high and all positive"
        )

    return estimate, prompt


def build_playlist_selection_prompt(
    query: str,
    candidates: list[dict],
    mood: str = "",
) -> str:
    """Build strict JSON prompt for selecting one playlist from candidates."""
    mood_text = mood.strip() or "指定なし"
    return (
        "あなたは音楽プレイリスト選定アシスタントです。\n"
        "ユーザー意図に最も合う候補を1件だけ選んでください。\n\n"
        f"- ユーザー要求: {query}\n"
        f"- 気分/補足: {mood_text}\n"
        "- 候補一覧(JSON):\n"
        f"{json.dumps(candidates, ensure_ascii=False)}\n\n"
        "選定ルール:\n"
        "- タイトル一致度、アーティスト/ジャンルの妥当性、説明文の関連性を重視\n"
        "- 曖昧な場合は最も一般的で外しにくい候補を選ぶ\n"
        "- 必ず候補内のuriを返す\n\n"
        "必ずJSONのみを返してください。Markdownは禁止。\n"
        "JSON schema:\n"
        "{\n"
        '  "selected_uri": "spotify:playlist:...",\n'
        '  "selected_name": "string",\n'
        '  "reason": "string"\n'
        "}"
    )


def choose_playlist_with_anthropic(
    query: str,
    candidates: list[dict],
    mood: str = "",
) -> tuple[str, str, str]:
    """Choose one playlist URI from candidates via Anthropic."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise AnthropicSelectionError("ANTHROPIC_API_KEY is not set")
    if not candidates:
        raise AnthropicSelectionError("No candidates provided")

    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest").strip()
    prompt = build_playlist_selection_prompt(query, candidates, mood)
    payload = {
        "model": model,
        "max_tokens": 350,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = Request(
        ANTHROPIC_MESSAGES_ENDPOINT,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise AnthropicSelectionError(f"Failed to call Anthropic API: {exc}") from exc

    text = _extract_text(response_payload)
    if not text:
        raise AnthropicSelectionError("Anthropic response did not include text content")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnthropicSelectionError(
            f"Anthropic response was not valid JSON: {text[:200]}"
        ) from exc

    selected_uri = str(data.get("selected_uri", "")).strip()
    selected_name = str(data.get("selected_name", "")).strip() or "unknown"
    reason = str(data.get("reason", "")).strip() or "No reason provided"
    if not selected_uri:
        raise AnthropicSelectionError(f"selected_uri is missing: {data}")

    valid_uris = {str(c.get("uri", "")).strip() for c in candidates}
    if selected_uri not in valid_uris:
        raise AnthropicSelectionError(
            f"selected_uri is not in candidates: {selected_uri}"
        )
    return selected_uri, selected_name, reason
