"""Trend analysis: compare multiple topic scans over time.

Algorithm:
  1. Tokenise each insight body into word sets (stop-words removed).
  2. Compute Jaccard similarity between insight pairs across scans.
  3. Insights with Jaccard >= threshold are considered "matching" (same topic thread).
  4. A TrendSignal is produced for each matched group, showing prevalence over time.

Usage:
    old_scan = load_scan(...)     # older scan result dict
    new_scan = load_scan(...)     # newer scan result dict
    signals = match_insights(old_scan["insights"], new_scan["insights"])
    report  = compute_trend_report([old_scan, mid_scan, new_scan])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

_STOP = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "be", "been", "have", "has",
    "that", "this", "it", "its", "i", "we", "you", "they", "their",
    "do", "does", "not", "no", "as", "by", "from", "about", "what",
    "how", "when", "where", "which", "who",
}

_JACCARD_THRESHOLD = 0.25


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union)


@dataclass
class TrendSignal:
    """A recurring insight theme found across multiple scans."""

    label: str
    representative: str
    first_seen: str
    last_seen: str
    occurrences: int
    matched_texts: list[str] = field(default_factory=list)
    direction: str = "stable"  # "rising" | "falling" | "stable" | "new" | "gone"


def match_insights(
    old_insights: list[dict],
    new_insights: list[dict],
    threshold: float = _JACCARD_THRESHOLD,
) -> dict[str, list[dict]]:
    """Compare two insight lists, return dict with 'persistent', 'new', 'gone'."""
    old_tokens = [(_tokens(i.get("body", "") or ""), i) for i in old_insights]
    new_tokens = [(_tokens(i.get("body", "") or ""), i) for i in new_insights]

    matched_old: set[int] = set()
    matched_new: set[int] = set()
    persistent: list[dict] = []

    for ni, (nt, new_i) in enumerate(new_tokens):
        best_score = 0.0
        best_oi = -1
        for oi, (ot, _) in enumerate(old_tokens):
            if oi in matched_old:
                continue
            score = _jaccard(nt, ot)
            if score > best_score:
                best_score = score
                best_oi = oi

        if best_score >= threshold and best_oi >= 0:
            matched_old.add(best_oi)
            matched_new.add(ni)
            persistent.append({
                "old": old_tokens[best_oi][1],
                "new": new_i,
                "similarity": round(best_score, 3),
            })

    gone = [old_tokens[i][1] for i in range(len(old_insights)) if i not in matched_old]
    new = [new_tokens[i][1] for i in range(len(new_insights)) if i not in matched_new]

    return {"persistent": persistent, "new": new, "gone": gone}


def compute_trend_report(scans: list[dict]) -> dict:
    """Build a trend report from a chronological list of scan result dicts.

    Each scan dict should have:
      - "scanned_at": ISO timestamp string
      - "topic_name": optional string label
      - "insights": list of insight dicts with "body", "severity", etc.
    """
    if len(scans) < 2:
        return {
            "error": "Need at least 2 scans to compute trends.",
            "scan_count": len(scans),
        }

    scans = sorted(scans, key=lambda s: s.get("scanned_at", ""))
    first_scan = scans[0]
    last_scan = scans[-1]

    # Track all insight bodies across time windows
    all_bodies: dict[str, list[str]] = {}  # insight_hash -> [scan timestamps]
    insight_repr: dict[str, str] = {}

    for scan in scans:
        ts = scan.get("scanned_at", "")
        for ins in scan.get("insights", []):
            body = (ins.get("body") or "").strip()
            if not body:
                continue
            toks = frozenset(_tokens(body))
            if not toks:
                continue
            matched_key = None
            for existing_key in all_bodies:
                existing_toks = frozenset(existing_key.split("|"))
                if _jaccard(toks, existing_toks) >= _JACCARD_THRESHOLD:
                    matched_key = existing_key
                    break
            if matched_key is None:
                matched_key = "|".join(sorted(toks))
                insight_repr[matched_key] = body
            all_bodies.setdefault(matched_key, []).append(ts)

    # Classify trends
    n = len(scans)
    rising, falling, stable, one_off = [], [], [], []

    for key, timestamps in all_bodies.items():
        occ = len(timestamps)
        first = timestamps[0]
        last = timestamps[-1]
        representative = insight_repr.get(key, key[:80])

        signal = TrendSignal(
            label=representative[:80],
            representative=representative,
            first_seen=first,
            last_seen=last,
            occurrences=occ,
            matched_texts=timestamps,
        )

        if occ == 1:
            signal.direction = "one_off"
            one_off.append(signal)
        elif first == scans[0].get("scanned_at") and last == scans[-1].get("scanned_at"):
            signal.direction = "persistent"
            stable.append(signal)
        elif last == scans[-1].get("scanned_at") and first != scans[0].get("scanned_at"):
            signal.direction = "rising"
            rising.append(signal)
        elif first == scans[0].get("scanned_at") and last != scans[-1].get("scanned_at"):
            signal.direction = "falling"
            falling.append(signal)
        else:
            signal.direction = "intermittent"
            stable.append(signal)

    def sig_to_dict(s: TrendSignal) -> dict:
        return {
            "label": s.label,
            "direction": s.direction,
            "occurrences": s.occurrences,
            "first_seen": s.first_seen,
            "last_seen": s.last_seen,
        }

    return {
        "scan_count": n,
        "period_start": first_scan.get("scanned_at", ""),
        "period_end": last_scan.get("scanned_at", ""),
        "topic_name": last_scan.get("topic_name"),
        "summary": {
            "persistent_count": len(stable),
            "rising_count": len(rising),
            "falling_count": len(falling),
            "one_off_count": len(one_off),
        },
        "rising": [sig_to_dict(s) for s in rising],
        "falling": [sig_to_dict(s) for s in falling],
        "persistent": [sig_to_dict(s) for s in stable],
        "one_off": [sig_to_dict(s) for s in one_off[:10]],
    }
