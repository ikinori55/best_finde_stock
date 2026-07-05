# -*- coding: utf-8 -*-
"""J-Quants API v2 共通クライアント（2026-07時点のv2仕様に対応）
v1はトークン認証だったが、v2は「ダッシュボード > 設定 > APIキー」で発行した
静的APIキーを x-api-key ヘッダーで送るだけ（トークン発行・更新は不要）。

環境変数:
  JQUANTS_API_KEY … ダッシュボードで発行したAPIキー(必須)
  JQUANTS_RPM     … 1分あたりのリクエスト上限(既定5=Freeプラン相当。有料プランなら60/120/500等に上げてよい)

レートリミット(公式ドキュメント): Free=5/分, Light=60/分, Standard=120/分, Premium=500/分。
財務情報系エンドポイントはプラン問わず60/分の個別上限あり。超過時は429。
"""
import os
import json
import time
import urllib.request
import urllib.error

BASE = "https://api.jquants.com/v2"
_last_request_ts = [0.0]


class JQuantsError(RuntimeError):
    pass


def _rpm():
    try:
        return max(1, int(os.environ.get("JQUANTS_RPM", "5")))
    except ValueError:
        return 5


def _throttle():
    min_interval = 60.0 / _rpm()
    elapsed = time.time() - _last_request_ts[0]
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_request_ts[0] = time.time()


def _api_key():
    key = os.environ.get("JQUANTS_API_KEY")
    if not key:
        raise JQuantsError(
            "環境変数 JQUANTS_API_KEY が未設定です。J-Quantsダッシュボード > 設定 > APIキー で発行し、"
            "設定してください。詳細は references/jquants-setup.md 参照。"
        )
    return key


def _get(path, params):
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    url = f"{BASE}{path}?{qs}" if qs else f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"x-api-key": _api_key()})

    for attempt in range(3):
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                print(f"[WARN] 429 Too Many Requests。60秒待機してリトライ...", flush=True)
                time.sleep(60)
                continue
            raise JQuantsError(f"GET {path} failed: {e.code} {e.read().decode('utf-8', 'ignore')}")
    raise JQuantsError(f"GET {path} failed: リトライ上限到達(429継続)")


def get_paginated(path, params=None):
    """pagination_key を辿って全ページ取得し、"data"配列を連結して返す(v2は常にdataキー)。"""
    params = dict(params or {})
    results = []
    while True:
        resp = _get(path, params)
        results.extend(resp.get("data", []))
        pk = resp.get("pagination_key")
        if not pk:
            break
        params["pagination_key"] = pk
    return results
