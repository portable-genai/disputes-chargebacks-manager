"""Policy packs are DATA: the config file loads, validates, and matches the shipped defaults.

The reason-code windows and abuse thresholds are the client's numbers, kept as configuration in
``config/policy_packs.yaml`` rather than as module constants. This suite is the drift guard: the
file loads into the same structures the defaults declare, and an unknown track in the file fails
closed rather than being silently accepted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from disputes_chargebacks_manager.config import load_policy
from disputes_chargebacks_manager.domain.policy_defaults import (
    DEFAULT_ABUSE_POLICY,
    DEFAULT_REASON_CODE_PACKS,
)

from tests import REPO_ROOT


def test_the_shipped_config_matches_the_declared_defaults() -> None:
    packs, policy = load_policy(Path(REPO_ROOT) / "config" / "policy_packs.yaml")
    assert packs == DEFAULT_REASON_CODE_PACKS, (
        "config/policy_packs.yaml drifted from domain/policy_defaults.py; keep them identical"
    )
    assert policy == DEFAULT_ABUSE_POLICY


def test_a_named_but_missing_file_raises_rather_than_silently_defaulting() -> None:
    """Somebody named a file; running on built-in defaults instead hides a misconfiguration."""
    with pytest.raises(FileNotFoundError):
        load_policy(Path(REPO_ROOT) / "config" / "surely-not-here.yaml")


def test_an_unknown_track_in_the_file_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "policy.yaml"
    bad.write_text(
        "reason_code_packs:\n  - track: not_a_track\n    scheme: x\n    rules: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_policy(bad)


def test_every_shipped_rule_has_a_positive_window_and_deadline() -> None:
    for pack in DEFAULT_REASON_CODE_PACKS:
        for rule in pack.rules:
            assert rule.filing_window_days > 0
            assert rule.response_deadline_days > 0
