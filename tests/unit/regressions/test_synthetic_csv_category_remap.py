"""Regression: remap_categories must replace the growth_v1 generator's
placeholder 'Major'/'Unknown' categories with the real NFDResponse Enum
looked up from incident_type.

Fixed in commit 36cc7c1 ("Remap synthetic incident categories to NFDResponse
Enum"). Before the fix, the simulator received literal strings 'Major' /
'Unknown' in the category column, which are not valid NFDResponse Enum
values (e.g. 'Nine', 'ThreeF', 'Four') and broke the C++ simulator's dispatch
table lookup.
"""

from __future__ import annotations

import pandas as pd

import engine.incidents_variants as variants


def test_remap_replaces_known_placeholder_categories(monkeypatch):
    fixture_mapping = {
        "Medical": "Nine",
        "Outside rubbish fire -  other": "Four",
    }
    monkeypatch.setattr(variants, "_type_to_category", lambda: fixture_mapping)

    df = pd.DataFrame({
        "incident_type": ["Medical", "Outside rubbish fire -  other", "Totally Unrecognized Type"],
        "category": ["Major", "Unknown", "Major"],
    })
    out = variants.remap_categories(df)

    assert out.loc[0, "category"] == "Nine"
    assert out.loc[1, "category"] == "Four"


def test_remap_leaves_placeholder_for_types_not_in_the_lookup(monkeypatch):
    """Rows whose incident_type has no historical mapping keep the generator's
    original placeholder rather than being mapped to NaN -- documented no-op
    behavior of remap_categories, not a bug."""
    monkeypatch.setattr(variants, "_type_to_category", lambda: {"Medical": "Nine"})

    df = pd.DataFrame({
        "incident_type": ["Totally Unrecognized Type"],
        "category": ["Major"],
    })
    out = variants.remap_categories(df)
    assert out.loc[0, "category"] == "Major"


def test_remap_is_a_noop_when_lookup_is_empty(monkeypatch):
    monkeypatch.setattr(variants, "_type_to_category", lambda: {})
    df = pd.DataFrame({"incident_type": ["Medical"], "category": ["Major"]})
    out = variants.remap_categories(df)
    assert out.loc[0, "category"] == "Major"
