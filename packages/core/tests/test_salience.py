from alexandria_core.ingest.salience import rank_entities
from alexandria_core.providers.base import ExtractedNode


def _ent(name: str) -> ExtractedNode:
    return ExtractedNode(name=name, kind="entity", description="")


def test_cap_keeps_the_most_mentioned():
    # Canelo dominates the text, Bivol is secondary, Smith is incidental.
    # With identical vectors, mention frequency is the only signal.
    ents = [_ent("Canelo"), _ent("Bivol"), _ent("Smith")]
    text = ("Canelo fought hard. Canelo landed. Canelo won the round. "
            "Bivol countered. Bivol jabbed. Smith only watched.")
    vecs = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
    kept, kept_vecs = rank_entities(ents, vecs, [1.0, 0.0], text, cap=2)
    assert [e.name for e in kept] == ["Canelo", "Bivol"]
    assert len(kept_vecs) == 2


def test_cap_none_returns_everything_unchanged():
    ents = [_ent("Alpha"), _ent("Beta")]
    vecs = [[1.0], [1.0]]
    kept, kept_vecs = rank_entities(ents, vecs, [1.0], "Alpha Beta", cap=None)
    assert [e.name for e in kept] == ["Alpha", "Beta"]
    assert kept_vecs == vecs


def test_cap_larger_than_input_returns_everything():
    ents = [_ent("Alpha"), _ent("Beta")]
    vecs = [[1.0], [1.0]]
    kept, _ = rank_entities(ents, vecs, [1.0], "Alpha Beta", cap=10)
    assert [e.name for e in kept] == ["Alpha", "Beta"]


def test_survivors_preserve_source_order():
    # Beta is more frequent (higher score) but Alpha must still come first.
    ents = [_ent("Alpha"), _ent("Beta")]
    text = "Alpha once. Beta Beta Beta everywhere."
    vecs = [[1.0, 0.0], [1.0, 0.0]]
    kept, _ = rank_entities(ents, vecs, [1.0, 0.0], text, cap=2)
    assert [e.name for e in kept] == ["Alpha", "Beta"]


def test_similarity_decides_when_frequency_ties():
    # Equal mention counts: the entity whose vector aligns with the source wins.
    ents = [_ent("Near"), _ent("Far")]
    text = "Near appears once. Far appears once."
    vecs = [[1.0, 0.0], [0.0, 1.0]]
    kept, _ = rank_entities(ents, vecs, [1.0, 0.0], text, cap=1)
    assert [e.name for e in kept] == ["Near"]


def test_mention_count_uses_word_boundaries():
    # "Ali" must not be inflated by "Alice"/"realign"; only the whole word counts.
    ents = [_ent("Ali"), _ent("Frazier")]
    text = "Alice realigned. Ali boxed. Frazier fought. Frazier won. Frazier retired."
    vecs = [[1.0, 0.0], [1.0, 0.0]]
    kept, _ = rank_entities(ents, vecs, [1.0, 0.0], text, cap=1)
    assert [e.name for e in kept] == ["Frazier"]
