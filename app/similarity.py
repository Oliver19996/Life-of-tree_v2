from __future__ import annotations

from .catalog import branch_of, trunk_of


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def similarity(my_leaves: set[str], other_leaves: set[str]) -> float:
    leaf_score = jaccard(my_leaves, other_leaves)
    my_b = {branch_of(x) for x in my_leaves}
    ot_b = {branch_of(x) for x in other_leaves}
    branch_score = jaccard(my_b, ot_b)
    shared_trunks = {trunk_of(x) for x in my_leaves & other_leaves}
    trunk_balance = len(shared_trunks) / 5
    return 0.75 * leaf_score + 0.15 * branch_score + 0.10 * trunk_balance


def qualifies(my_leaves: set[str], other_leaves: set[str]) -> bool:
    shared = my_leaves & other_leaves
    if len(shared) >= 2:
        return True
    if len(shared) == 1:
        my_b = {branch_of(x) for x in my_leaves}
        ot_b = {branch_of(x) for x in other_leaves}
        return len(my_b & ot_b) >= 2
    return False


def resonance_label(score: float) -> str:
    if score >= 0.45:
        return "木の響きがとても近い"
    if score >= 0.22:
        return "木の響きが近い"
    return "かすかに響き合う"
