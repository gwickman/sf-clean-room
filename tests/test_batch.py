import pytest

from sf_clean_room.batch import build_batches, describe_plan


def test_empty_input_yields_no_batches():
    assert build_batches({}) == []


def test_single_small_input_fits_one_batch():
    members = {"ApexClass": [f"C{i}" for i in range(10)]}
    batches = build_batches(members, max_components=100, max_weight=1000)
    assert len(batches) == 1
    assert batches[0].total_count == 10
    assert batches[0].chunks[0].type_name == "ApexClass"


def test_count_ceiling_triggers_split():
    members = {"ApexClass": [f"C{i}" for i in range(25)]}
    batches = build_batches(members, max_components=10, max_weight=10_000)
    assert len(batches) == 3
    assert [b.total_count for b in batches] == [10, 10, 5]


def test_weight_ceiling_triggers_split_for_heavy_type():
    # ExperienceBundle weight is 500; max_weight 1500 means 3 per batch.
    members = {"ExperienceBundle": [f"B{i}" for i in range(8)]}
    batches = build_batches(members, max_components=10_000, max_weight=1500)
    counts = [b.total_count for b in batches]
    assert sum(counts) == 8
    for b in batches:
        assert b.total_weight <= 1500 or b.total_count == 1  # never split a component


def test_oversize_single_component_lands_alone():
    # Single component whose weight alone exceeds the ceiling still gets placed.
    members = {"ExperienceBundle": ["A"]}  # weight 500
    batches = build_batches(members, max_components=10_000, max_weight=100)
    assert len(batches) == 1
    assert batches[0].total_count == 1


def test_mixed_types_packed_into_one_batch_when_under_ceilings():
    members = {
        "ApexClass": ["A1", "A2"],
        "Flow": ["F1"],
        "LightningComponentBundle": ["L1"],
    }
    batches = build_batches(members, max_components=100, max_weight=100)
    assert len(batches) == 1
    types_in = {c.type_name for c in batches[0].chunks}
    assert types_in == {"ApexClass", "Flow", "LightningComponentBundle"}


def test_iteration_order_is_deterministic():
    a = {"Bravo": ["x"], "Alpha": ["y"], "Charlie": ["z"]}
    b = {"Charlie": ["z"], "Alpha": ["y"], "Bravo": ["x"]}
    batches_a = build_batches(a, max_components=10, max_weight=100)
    batches_b = build_batches(b, max_components=10, max_weight=100)
    assert [c.type_name for c in batches_a[0].chunks] == [c.type_name for c in batches_b[0].chunks]


def test_invalid_ceilings_rejected():
    with pytest.raises(ValueError):
        build_batches({"X": ["a"]}, max_components=0)
    with pytest.raises(ValueError):
        build_batches({"X": ["a"]}, max_weight=0)


def test_describe_plan_handles_empty():
    assert describe_plan([]) == "no components after filtering"


def test_describe_plan_lists_chunks():
    members = {"ApexClass": ["A", "B"], "Flow": ["F1"]}
    plan = describe_plan(build_batches(members))
    assert "ApexClass" in plan and "Flow" in plan
    assert "totals" in plan
