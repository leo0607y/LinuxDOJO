"""Helpers for keeping complete solutions in the explicit answer flow."""
import re


def _plain(text):
    text = str(text or "").replace("`", "").replace("→", " ").replace("'", "").replace('"', "")
    text = re.sub(r"^入力例[^:\n]*:\s*", "", text.strip())
    return " ".join(text.split())


def contains_full_solution(hint, solutions):
    """Return true when a hint is just a wrapped or formatted full solution."""
    candidate = _plain(hint)
    if not candidate:
        return False
    for solution in solutions:
        expected = _plain(solution)
        if expected and expected in candidate:
            return True
    return False


def advice_only(hints, solutions):
    return [hint for hint in hints if str(hint).strip() and not contains_full_solution(hint, solutions)]
