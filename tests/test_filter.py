from sf_clean_room.filter_md import apply_deny_list


def test_deny_listed_types_are_removed():
    members = {
        "ApexClass": ["A", "B"],
        "ConnectedApp": ["Slack", "Jira"],
        "Document": ["d1", "d2", "d3"],
        "Flow": ["F1"],
    }
    result = apply_deny_list(members)
    assert "ApexClass" in result.kept
    assert "Flow" in result.kept
    assert "ConnectedApp" not in result.kept
    assert "Document" not in result.kept
    assert result.excluded_counts == {"ConnectedApp": 2, "Document": 3}
    assert result.excluded_total == 5


def test_empty_input_returns_empty():
    result = apply_deny_list({})
    assert result.kept == {}
    assert result.excluded_counts == {}


def test_kept_members_are_copies():
    members = {"ApexClass": ["A"]}
    result = apply_deny_list(members)
    result.kept["ApexClass"].append("B")
    assert members["ApexClass"] == ["A"]
