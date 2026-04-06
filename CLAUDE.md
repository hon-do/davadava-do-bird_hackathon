# CLAUDE.md

## プロジェクト概要
davadava - VoiceOS MCP 音声 DJ アプリ。
タスク・モチベーション・ドライブの目的地に応じて Spotify の曲を推薦・再生する。

## 技術スタック
- Python 3
- `mcp` (FastMCP) - MCP サーバーフレームワーク
- AppleScript (osascript) - Spotify / macOS 制御

## ディレクトリ構成
```
src/
  dj_server.py    - MCPサーバー (エントリポイント)
  spotify.py      - Spotify操作ヘルパー (AppleScript)
  recommender.py  - 曲推薦エンジン (タスク/モチベ/ドライブ)
  maps.py         - Google Maps Directions API 連携
  anthropic_eta.py - Anthropic API による所要時間推定
docs/
  voiceos-mcp-overview.md - VoiceOS MCP 機能一覧
```

## 開発コマンド
```bash
pip install -r requirements.txt    # 依存関係
python3 src/dj_server.py           # MCPサーバー起動
```

## 設計方針
- VoiceOS の AI がツールの description を読んで音声→ツールのマッピングを行う
- description は英語で書く（VoiceOS の AI が解釈しやすいため）
- 推薦ロジックは recommender.py に集約し、dj_server.py はMCPツール定義に専念
- Spotify操作は spotify.py に集約し、AppleScript の詳細を隠蔽

## 追加した開発方針（2026-04）
- 1ツール1責務を基本にしつつ、ユーザー体験向上のために「複合ツール」も提供する
- 例: `start_drive_session` は Spotify起動 + Google Mapsブラウザ起動 + 再生までを1コマンドで実行
- ルート情報取得が失敗しても、再生を止めない（フォールバックで目的地ベース推薦）
- 外部API失敗時は例外を握りつぶさず、ユーザーに原因が分かる文字列を返す

## APIキー運用方針
- すべて環境変数から読み込む（コード・リポジトリに埋め込まない）
- `GOOGLE_MAPS_API_KEY`: Google Directions API 用
- `ANTHROPIC_API_KEY`: Anthropic Messages API 用
- `ANTHROPIC_MODEL`: 任意上書き（未指定時 `claude-3-5-sonnet-latest`）
- VoiceOS のカスタム連携起動コマンドに環境変数を渡す前提で運用する

## 現在の主要MCPツール方針
- ルート確認: `route_summary(origin, destination)`
- ルート連動再生: `drive_music_with_route(origin, destination, mood="")`
- 予測プロンプト確認: `anthropic_eta_prompt(origin, destination, distance_km, departure_context="")`
- Anthropic時間予測: `predict_drive_time_with_anthropic(...)`
- 予測時間連動再生: `drive_music_with_predicted_time(...)`
- 複合起動: `start_drive_session(origin, destination, mood="")`
- 任意URI再生: `play_spotify_uri(uri)`
- プレイリスト名再生: `play_spotify_playlist_by_name(name)`

## 音声コマンド設計ルール
- 「AからBまで」を入れて `origin/destination` を明示する
- 動詞を明確にする（例: 「開始して」「時間を見て」「予測して」）
- 1発話1意図を優先し、情報を詰め込みすぎない
