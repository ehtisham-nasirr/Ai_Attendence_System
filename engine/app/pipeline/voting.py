"""Matching decision and track voting (requirements §9 steps 3-4, §10.1 step 9, FR-15, NFR-2).

A false accept is worse than a miss, so the rules are strict:
- one crop votes for employee X only if its best score >= threshold AND best - second-best >= margin;
- a track is confirmed only when at least `min_votes` of its `required_crops` embedded crops vote for
  the same employee AND no crop scores any *other* employee at or above the threshold within
  `conflict_gap` of the winner's score (Q66: 0.88 vs 0.41 is not a conflict; 0.45 vs 0.40 is).
Threshold, margin and vote counts come from configuration and are never lowered without approval.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.gallery.index import MatchCandidate


@dataclass(frozen=True, slots=True)
class VotingRules:
    threshold: float
    margin: float
    min_votes: int = 2
    required_crops: int = 3
    # Another employee at or above the threshold blocks the decision only this close to the winner (Q66).
    conflict_gap: float = 0.15


@dataclass(frozen=True, slots=True)
class VoteResult:
    outcome: Literal["pending", "confirmed", "unknown"]
    employee_code: str | None = None
    # Mean score of the winning votes for a confirmed track; best score seen otherwise.
    confidence: float = 0.0


def crop_vote(matches: Sequence[MatchCandidate], rules: VotingRules) -> str | None:
    """The employee this crop votes for, or None if threshold or margin is not met."""
    if not matches or matches[0].score < rules.threshold:
        return None
    second = matches[1].score if len(matches) > 1 else -1.0
    if matches[0].score - second < rules.margin:
        return None
    return matches[0].employee_code


def _conflicts(best_by_code: dict[str, float], winner: str, winner_score: float, rules: VotingRules) -> bool:
    """Another employee scored at or above the threshold and within `conflict_gap` of the winner."""
    return any(
        code != winner and score >= rules.threshold and score > winner_score - rules.conflict_gap
        for code, score in best_by_code.items()
    )


def _best_by_code(crop_matches: Sequence[Sequence[MatchCandidate]]) -> dict[str, float]:
    best: dict[str, float] = {}
    for matches in crop_matches:
        for m in matches:
            best[m.employee_code] = max(best.get(m.employee_code, -1.0), m.score)
    return best


def decide_track(crop_matches: Sequence[Sequence[MatchCandidate]], rules: VotingRules) -> VoteResult:
    """Decides a track from the match lists of its embedded crops."""
    best_seen = max((m[0].score for m in crop_matches if m), default=0.0)
    if len(crop_matches) < rules.required_crops:
        return VoteResult("pending", confidence=best_seen)

    votes: Counter[str] = Counter()
    scores_by_code: dict[str, list[float]] = {}
    for matches in crop_matches:
        code = crop_vote(matches, rules)
        if code is not None:
            votes[code] += 1
            scores_by_code.setdefault(code, []).append(matches[0].score)

    if not votes:
        return VoteResult("unknown", confidence=best_seen)
    ranked = votes.most_common(2)
    winner, count = ranked[0]
    tied = len(ranked) > 1 and ranked[1][1] == count
    if count < rules.min_votes or tied:
        return VoteResult("unknown", confidence=best_seen)
    winning_scores = scores_by_code[winner]
    winner_score = sum(winning_scores) / len(winning_scores)
    if _conflicts(_best_by_code(crop_matches), winner, winner_score, rules):
        return VoteResult("unknown", confidence=best_seen)
    return VoteResult("confirmed", winner, winner_score)


def points_to_one_employee(crop_matches: Sequence[Sequence[MatchCandidate]], rules: VotingRules) -> bool:
    """True when an UNCONFIRMED track's crops point to exactly one enrolled employee (FR-17).

    Strict: at least one crop votes (`crop_vote`: threshold AND margin), every voting crop votes for the
    same employee, and no crop scores another employee at or above the threshold within `conflict_gap` of
    the voted employee's best score (Q66). Such a track is a
    known person seen too briefly to confirm, not an unknown face. This never confirms a track: that
    still needs `decide_track` (`min_votes` of `required_crops`).
    """
    voted: set[str] = set()
    for matches in crop_matches:
        code = crop_vote(matches, rules)
        if code is not None:
            voted.add(code)
    if len(voted) != 1:
        return False
    winner = next(iter(voted))
    best = _best_by_code(crop_matches)
    return not _conflicts(best, winner, best[winner], rules)
