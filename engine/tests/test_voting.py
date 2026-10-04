"""Matching and voting rules (requirements §9, §10.1 step 9, FR-15, NFR-2)."""

from conftest import matches

from app.pipeline.voting import VotingRules, crop_vote, decide_track, points_to_one_employee

RULES = VotingRules(threshold=0.36, margin=0.08, min_votes=2, required_crops=3)


def test_nfr2_crop_votes_only_above_threshold_and_margin() -> None:
    assert crop_vote(matches(("A", 0.50), ("B", 0.30)), RULES) == "A"
    assert crop_vote(matches(("A", 0.35), ("B", 0.10)), RULES) is None  # below threshold
    assert crop_vote(matches(("A", 0.50), ("B", 0.45)), RULES) is None  # margin 0.05 < 0.08
    assert crop_vote(matches(("A", 0.50)), RULES) == "A"  # single-employee gallery
    assert crop_vote([], RULES) is None


def test_fr15_needs_three_crops_before_deciding() -> None:
    result = decide_track([matches(("A", 0.9)), matches(("A", 0.9))], RULES)
    assert result.outcome == "pending"


def test_fr15_two_of_three_votes_confirm() -> None:
    crops = [matches(("A", 0.60), ("B", 0.1)), matches(("A", 0.50), ("B", 0.1)), matches(("C", 0.2))]
    result = decide_track(crops, RULES)
    assert result.outcome == "confirmed"
    assert result.employee_code == "A"
    assert abs(result.confidence - 0.55) < 1e-9  # mean of the winning votes


def test_nfr2_any_other_employee_above_threshold_blocks_confirmation() -> None:
    crops = [matches(("A", 0.60)), matches(("A", 0.55)), matches(("B", 0.40), ("A", 0.20))]
    assert decide_track(crops, RULES).outcome == "unknown"


def test_nfr2_second_best_above_threshold_inside_a_voting_crop_blocks() -> None:
    crops = [matches(("A", 0.60), ("B", 0.37)), matches(("A", 0.60)), matches(("A", 0.60))]
    assert decide_track(crops, RULES).outcome == "unknown"


def test_one_vote_is_not_enough() -> None:
    crops = [matches(("A", 0.60)), matches(("A", 0.30)), matches(("A", 0.20))]
    result = decide_track(crops, RULES)
    assert result.outcome == "unknown"
    assert result.confidence == 0.60


def test_no_votes_is_unknown() -> None:
    crops = [matches(("A", 0.2)), matches(), matches(("B", 0.1))]
    assert decide_track(crops, RULES).outcome == "unknown"


def test_stricter_rules_from_configuration_are_respected() -> None:
    strict = VotingRules(threshold=0.36, margin=0.08, min_votes=3, required_crops=3)
    crops = [matches(("A", 0.60)), matches(("A", 0.60)), matches(("A", 0.30))]
    assert decide_track(crops, strict).outcome == "unknown"


# --- FR-17: an unconfirmed track that points to one enrolled employee is not an Unknown face -----------


def test_fr17_points_to_one_employee_when_every_vote_is_for_the_same_employee() -> None:
    assert points_to_one_employee([matches(("A", 0.60))], RULES)  # one crop, one vote
    assert points_to_one_employee([matches(("A", 0.60), ("B", 0.10)), matches(("A", 0.55))], RULES)
    # A crop below the threshold casts no vote and names nobody else: still only A.
    assert points_to_one_employee([matches(("A", 0.60)), matches(("A", 0.30)), matches(("B", 0.20))], RULES)


def test_fr17_no_vote_does_not_point_to_anyone() -> None:
    assert not points_to_one_employee([], RULES)
    assert not points_to_one_employee([matches()], RULES)
    assert not points_to_one_employee([matches(("A", 0.35)), matches(("A", 0.30))], RULES)  # below threshold
    assert not points_to_one_employee([matches(("A", 0.40), ("B", 0.35))], RULES)  # margin 0.05 < 0.08


def test_fr17_nfr2_two_employees_never_point_to_one() -> None:
    assert not points_to_one_employee([matches(("A", 0.60)), matches(("B", 0.60))], RULES)  # split votes
    # A non-voting crop that still scores another employee at or above the threshold.
    assert not points_to_one_employee([matches(("A", 0.60)), matches(("B", 0.40), ("A", 0.38))], RULES)
    # The second-best employee inside a voting crop reaches the threshold.
    assert not points_to_one_employee([matches(("A", 0.60), ("B", 0.36))], RULES)


def test_fr17_pointing_to_one_employee_never_confirms() -> None:
    crops = [matches(("A", 0.90)), matches(("A", 0.30)), matches(("A", 0.20))]
    assert points_to_one_employee(crops, RULES)
    assert decide_track(crops, RULES).outcome == "unknown"  # confirmation rules are unchanged
