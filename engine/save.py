"""セーブデータ (save_data.json) の読み書きとランク・称号・スコア計算。"""
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAVE = Path(os.environ.get("LQ_SAVE", ROOT / "save_data.json"))

RANKS = [
    (0, "Lv.1", "ターミナル見習い"),
    (5, "Lv.2", "ディレクトリ探検家"),
    (11, "Lv.3", "パイプライン職人"),
    (17, "Lv.4", "パーミッションの番人"),
    (23, "Lv.5", "サーバー守護神"),
    (30, "Lv.6", "ネットワーク航海士"),
    (36, "Lv.7", "コンテナ魔術師"),
    (44, "Lv.8", "自動化の達人"),
    (52, "Lv.9", "本番運用マスター"),
    (59, "Lv.MAX", "伝説のシェル仙人"),
]

STAGE_TITLES = {
    1: "🏅 ファイルシステムの開拓者",
    2: "🏅 grep & awk の錬金術師",
    3: "🏅 プロセスハンター",
    4: "🏅 パケットの旅人",
    5: "🏅 クジラ使い (Docker Whale Rider)",
    6: "🏅 自動化の錬成師",
    7: "🏅 本番環境の守り人",
    99: "🏅 時短の求道者",
}

# ヒント段階ごとの獲得点数倍率（answer 閲覧時は 0.5）
HINT_FACTOR = {0: 1.0, 1: 0.9, 2: 0.8, 3: 0.7}
ANSWER_FACTOR = 0.5


def empty():
    return {
        "version": 1,
        "player": {"created": None, "play_seconds": 0, "sessions": 0},
        "cleared": {},
        "titles": [],
        "stats": {"checks": 0, "hints": 0, "answers": 0, "resets": 0},
        "settings": {"docker_mode": "auto"},
        "learning": learning_defaults(),
    }


def learning_defaults(mode="intro"):
    return {
        "mode": mode,
        "intro": {"completed": [], "cwd": ".", "packages": [], "apt_updated": False},
        "basic": {"completed": [], "cwd": ".", "packages": [], "apt_updated": False},
        "practice": {"mission": None},
    }


def load():
    try:
        d = json.loads(SAVE.read_text())
        base = empty()
        # 既存の実践プレイヤーは同じモードから再開。初めての人は導入から。
        legacy_mode = "practice" if d.get("cleared") or d.get("player", {}).get("sessions", 0) else "intro"
        defaults = learning_defaults(legacy_mode)
        learning = d.setdefault("learning", {})
        for key, value in defaults.items():
            learning.setdefault(key, value)
        if learning["mode"] not in ("intro", "basic", "practice"):
            learning["mode"] = legacy_mode
        for mode in ("intro", "basic", "practice"):
            for key, value in defaults[mode].items():
                learning[mode].setdefault(key, value)
        for k, v in base.items():
            d.setdefault(k, v)
        for k, v in base["stats"].items():
            d["stats"].setdefault(k, v)
        return d
    except (OSError, ValueError):
        return empty()


def store(d):
    tmp = SAVE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    os.replace(tmp, SAVE)


def bump(stat, n=1):
    d = load()
    d["stats"][stat] = d["stats"].get(stat, 0) + n
    store(d)


def score_for(points, hint_level, answer_viewed):
    f = ANSWER_FACTOR if answer_viewed else HINT_FACTOR.get(hint_level, 0.7)
    return int(points * f)


def record_clear(mission, hint_level, answer_viewed, seconds):
    """クリアを記録。新しく得た称号・ランクアップ情報を返す。"""
    from engine.runner import missions_of
    d = load()
    before_rank = rank_of(len(d["cleared"]))
    sc = score_for(mission.points, hint_level, answer_viewed)
    prev = d["cleared"].get(mission.id)
    first = prev is None
    if prev is None or sc > prev.get("score", 0):
        d["cleared"][mission.id] = {
            "score": sc, "hints": hint_level, "answer": answer_viewed,
            "seconds": int(seconds), "date": time.strftime("%Y-%m-%d %H:%M"),
        }
    new_titles = []
    ids = {m.id for m in missions_of(mission.stage)}
    if ids and ids <= set(d["cleared"]):
        t = STAGE_TITLES.get(mission.stage)
        if t and t not in d["titles"]:
            d["titles"].append(t)
            new_titles.append(t)
    after_rank = rank_of(len(d["cleared"]))
    store(d)
    return {"score": sc, "first": first, "titles": new_titles,
            "rankup": after_rank if after_rank != before_rank else None}


def rank_of(n_cleared):
    cur = RANKS[0]
    for r in RANKS:
        if n_cleared >= r[0]:
            cur = r
    return cur


def next_rank(n_cleared):
    for r in RANKS:
        if r[0] > n_cleared:
            return r
    return None


def total_score(d=None):
    d = d or load()
    return sum(v.get("score", 0) for v in d["cleared"].values())
