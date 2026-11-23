"""セーブデータ (save_data.json) の読み書きとランク・称号・スコア計算。"""
import json
import os
import time
from datetime import date, timedelta
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
    (59, "Lv.10", "セキュリティ演習の探究者"),
]

STAGE_TITLES = {
    1: "ファイルシステムの開拓者",
    2: "grep & awk の錬金術師",
    3: "プロセスハンター",
    4: "パケットの旅人",
    5: "クジラ使い (Docker Whale Rider)",
    6: "自動化の錬成師",
    7: "本番環境の守り人",
    8: "Web セキュリティの検証者",
    9: "最小権限の監査者",
    10: "証拠を伝える調査者",
    11: "ストレージと復旧の調査者",
    12: "性能と権限の調査者",
    13: "通信とサービスの構築者",
    14: "ブートとカーネルの探究者",
    15: "ストレージの設計者",
    16: "アクセス制御の設計者",
    17: "運用管理の統括者",
    18: "基盤技術の実践者",
    19: "総点検の完遂者",
    20: "通信と暗号の守護者",
    21: "基盤サービスの運用者",
    22: "仮想基盤の構築者",
    23: "データ保全の責任者",
    24: "ビルドと自動化の職人",
    25: "コマンド総ざらい(基礎)の達成者",
    26: "ブロックデバイスの職人",
    27: "システム観測の達人",
    28: "管理基盤の熟練者",
    29: "全域コマンドの踏破者",
    30: "Gitの実務家",
    31: "エディタの達人",
    32: "道具箱の使い手",
    33: "ビルドと品質の担当者",
    34: "リモート作業のプロ",
    99: "時短の求道者",
}

# ヒント段階ごとの獲得点数倍率（answer 閲覧時は 0.5）
HINT_FACTOR = {0: 1.0, 1: 0.9, 2: 0.8, 3: 0.7}
ANSWER_FACTOR = 0.5


def empty():
    return {
        "version": 1,
        "player": {"created": None, "play_seconds": 0, "sessions": 0},
        "cleared": {},
        "review": {},
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
        "advanced": {"completed": [], "cwd": ".", "packages": [], "apt_updated": False},
        "expert": {"completed": [], "cwd": ".", "packages": [], "apt_updated": False},
        "practice": {"mission": None},
    }


def _plain_title(t):
    """旧セーブに残る絵文字付きの称号から絵文字を取り除く。"""
    return str(t).replace("\U0001F3C5", "").replace("\ufe0f", "").strip()


def load():
    try:
        d = json.loads(SAVE.read_text(encoding="utf-8"))
        legacy_review = "review" not in d
        base = empty()
        # 既存の実践プレイヤーは同じモードから再開。初めての人は導入から。
        legacy_mode = "practice" if d.get("cleared") or d.get("player", {}).get("sessions", 0) else "intro"
        defaults = learning_defaults(legacy_mode)
        learning = d.setdefault("learning", {})
        for key, value in defaults.items():
            learning.setdefault(key, value)
        if learning["mode"] not in ("intro", "basic", "advanced", "expert", "practice"):
            learning["mode"] = legacy_mode
        for mode in ("intro", "basic", "advanced", "expert", "practice"):
            for key, value in defaults[mode].items():
                learning[mode].setdefault(key, value)
        for k, v in base.items():
            d.setdefault(k, v)
        if legacy_review:
            for lesson_id, record in d["cleared"].items():
                if record.get("answer"):
                    mark_review(d, "practice", lesson_id)
        for k, v in base["stats"].items():
            d["stats"].setdefault(k, v)
        d["titles"] = list(dict.fromkeys(_plain_title(t) for t in d.get("titles", [])))
        return d
    except (OSError, ValueError):
        return empty()


def store(d):
    tmp = SAVE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SAVE)


def bump(stat, n=1):
    d = load()
    d["stats"][stat] = d["stats"].get(stat, 0) + n
    store(d)


def mark_review(data, mode, lesson_id):
    """答えを見た時点で、未達成の問題も復習対象として残す。"""
    data.setdefault("review", {})[mode + ":" + lesson_id] = {"mode": mode, "id": lesson_id}


def finish_review(data, mode, lesson_id, assisted=False):
    """ヒントや答えなしで解き直した試行だけ、復習対象から外す。"""
    if not assisted:
        data.setdefault("review", {}).pop(mode + ":" + lesson_id, None)


def review_ids(data, mode):
    return [item["id"] for item in data.get("review", {}).values()
            if isinstance(item, dict) and item.get("mode") == mode and isinstance(item.get("id"), str)]


def score_for(points, hint_level, answer_viewed):
    f = ANSWER_FACTOR if answer_viewed else HINT_FACTOR.get(hint_level, 0.7)
    return int(points * f)


def record_clear(mission, hint_level, answer_viewed, seconds):
    """クリアを記録。新しく得た称号・ランクアップ情報を返す。"""
    from engine.runner import missions_of
    d = load()
    before_rank = rank_of(len(d["cleared"]))
    sc = score_for(mission.points, hint_level, answer_viewed)
    finish_review(d, "practice", mission.id, assisted=bool(hint_level or answer_viewed))
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
    activity = record_activity(d, "practice:" + mission.id)
    store(d)
    return {"score": sc, "first": first, "titles": new_titles,
            "rankup": after_rank if after_rank != before_rank else None,
            "activity": activity}


def rank_table():
    from engine.runner import load_curriculum
    total = len(load_curriculum())
    return [r for r in RANKS if r[0] < total] + [(total, "Lv.MAX", "全実践課題の修了者")]


def rank_of(n_cleared):
    table = rank_table()
    cur = table[0]
    for r in table:
        if n_cleared >= r[0]:
            cur = r
    return cur


def next_rank(n_cleared):
    for r in rank_table():
        if r[0] > n_cleared:
            return r
    return None


def total_score(d=None):
    d = d or load()
    return sum(v.get("score", 0) for v in d["cleared"].values())


def activity_summary(d, today=None):
    """端末のローカル日付で日々の学習を集計する。"""
    today = today or date.today()
    activity = d.get("activity", {})
    days = activity.get("days", {})
    cursor = today if today.isoformat() in days else today - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    count = len(days.get(today.isoformat(), []))
    return {"xp": activity.get("xp", 0), "today": count, "goal": 3,
            "streak": streak}


def record_activity(d, lesson_id, today=None):
    """同じ課題への報酬は1日1回。復習も別の日なら学習として数える。"""
    today = today or date.today()
    activity = d.setdefault("activity", {})
    activity.setdefault("xp", 0)
    activity.setdefault("days", {})
    completed = activity["days"].setdefault(today.isoformat(), [])
    earned = 0
    if lesson_id not in completed:
        completed.append(lesson_id)
        earned = 10
        activity["xp"] += earned
    return dict(activity_summary(d, today), earned=earned)


def activity_line(d):
    summary = activity_summary(d)
    goal = "今日の目標達成！" if summary["today"] >= summary["goal"] else "今日は3課題に挑戦しよう"
    return (f"学習XP {summary['xp']}  |  連続 {summary['streak']} 日  |  "
            f"今日 {summary['today']}/{summary['goal']} 課題  {goal}")
