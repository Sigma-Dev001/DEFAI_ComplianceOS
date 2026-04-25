import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.decision import (
    _clamp_confidence,
    _clamp_score,
    _confidence_label,
    _extract_json,
    _normalize_citation,
    _score_to_decision,
    parse_claude_output,
)


def _valid_citation(jurisdiction: str, rule_id: str) -> dict:
    return {
        "jurisdiction": jurisdiction,
        "instrument": f"{jurisdiction} Rulebook",
        "rule_id": rule_id,
        "effective_date": "2023-01-01",
        "quote_excerpt": "verbatim excerpt from the regulatory clause",
        "mapping": f"{rule_id} triggered because transfer_count_24h satisfies the unusual pattern element.",
    }


def _claude_payload(vara_score, mas_score, fca_score, confidence=0.80):
    return json.dumps(
        {
            "decisions": {
                "vara": {"score": vara_score, "citations": [_valid_citation("VARA", "Part II Rule 1.2")]},
                "mas": {"score": mas_score, "citations": [_valid_citation("MAS", "PSN01 Para 5")]},
                "fca": {"score": fca_score, "citations": [_valid_citation("FCA", "SYSC 6.3")]},
            },
            "confidence": confidence,
            "summary_reason": "Structuring indicators present near reporting threshold.",
            "recommended_action": "Hold for manual review",
        }
    )


def test_clamp_score_basic():
    assert _clamp_score(50) == 50
    assert _clamp_score(150) == 100
    assert _clamp_score(-10) == 0
    assert _clamp_score("not-a-number") == 50


def test_clamp_confidence_rounds_to_2dp():
    assert _clamp_confidence(0.8765) == 0.88
    assert _clamp_confidence(1.5) == 1.0
    assert _clamp_confidence(-0.1) == 0.0
    assert _clamp_confidence("bad") == 0.5


def test_confidence_label_bands():
    assert _confidence_label(0.3) == "low"
    assert _confidence_label(0.4) == "medium"
    assert _confidence_label(0.7) == "medium"
    assert _confidence_label(0.71) == "high"


def test_score_to_decision_thresholds():
    assert _score_to_decision(0) == "PASS"
    assert _score_to_decision(39) == "PASS"
    assert _score_to_decision(40) == "FLAG"
    assert _score_to_decision(65) == "FLAG"
    assert _score_to_decision(66) == "BLOCK"
    assert _score_to_decision(100) == "BLOCK"


def test_normalize_citation_drops_incomplete():
    missing_rule_id = _valid_citation("VARA", "R1")
    missing_rule_id.pop("rule_id")
    assert _normalize_citation(missing_rule_id) is None

    empty_quote = _valid_citation("VARA", "R1")
    empty_quote["quote_excerpt"] = ""
    assert _normalize_citation(empty_quote) is None

    cleaned = _normalize_citation(_valid_citation("VARA", "R1"))
    assert isinstance(cleaned, dict)
    assert set(cleaned.keys()) == {"jurisdiction", "instrument", "rule_id", "quote_excerpt"}
    assert all(isinstance(v, str) and v == v.strip() and v for v in cleaned.values())


def test_extract_json_handles_code_fences():
    assert _extract_json('{"decisions":{}}') == {"decisions": {}}
    assert _extract_json('```json\n{"decisions":{}}\n```') == {"decisions": {}}
    assert _extract_json('prose before {"decisions":{}} prose after') == {"decisions": {}}
    assert _extract_json("garbage no braces") is None
    assert _extract_json("") is None


def test_parse_claude_output_structuring_flag():
    tx = {"sender_country": "AE", "receiver_country": "SG", "amount": 9800, "transfer_count_24h": 7}
    raw = _claude_payload(55, 55, 55, confidence=0.82)
    result = parse_claude_output(raw, "tx-1", tx, 120)
    assert result["decision"] == "FLAG"
    assert result["score"] == 55
    assert result["confidence"] == 0.82
    assert result["confidence_label"] == "high"
    assert result["override_applied"] is False
    assert len(result["rule_references"]) >= 1


def test_parse_claude_output_sanctions_force_block():
    tx = {"sender_country": "IR", "receiver_country": "UK", "amount": 50000}
    raw = _claude_payload(50, 50, 50, confidence=0.70)
    result = parse_claude_output(raw, "tx-2", tx, 150)
    assert result["decision"] == "BLOCK"
    assert result["score"] >= 85
    assert result["override_applied"] is True
    assert "sanctioned" in result["override_reason"]
    assert all(d["decision"] == "FLAG" for d in result["decisions"].values())


def test_parse_claude_output_block_downgraded_to_flag_non_sanctioned():
    tx = {"sender_country": "AE", "receiver_country": "SG", "amount": 15000, "transfer_count_24h": 3}
    raw = _claude_payload(70, 70, 70)
    result = parse_claude_output(raw, "tx-3", tx, 110)
    assert result["decision"] == "FLAG"
    assert result["override_applied"] is True
    for key in ("vara", "mas", "fca"):
        assert key in result["override_reason"]
        assert result["decisions"][key]["decision"] == "FLAG"


def test_parse_claude_output_sanctioned_preserves_block_scores():
    tx = {"sender_country": "IR", "receiver_country": "UK", "amount": 50000}
    raw = _claude_payload(90, 90, 90)
    result = parse_claude_output(raw, "tx-4", tx, 140)
    assert result["decision"] == "BLOCK"
    assert result["score"] == 90
    assert result["override_applied"] is True
    assert all(d["decision"] == "BLOCK" for d in result["decisions"].values())
