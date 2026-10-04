"""Unit tests for PII masking, output guardrails, and audit hashing (offline)."""

from __future__ import annotations

from resolve.security import pii
from resolve.security.audit import GENESIS, AuditEvent, hash_event
from resolve.security.guardrails import check_output


def test_pii_detect_common_entities() -> None:
    text = "email me at jane@x.test or call 555-123-4567; ssn 123-45-6789 on 02/03/2025"
    types = {s.entity_type for s in pii.detect(text)}
    assert {"EMAIL_ADDRESS", "PHONE_NUMBER", "SSN", "DATE"} <= types


def test_pii_mask_replaces_with_placeholders() -> None:
    # 14-digit account (not phone-shaped) so it classifies as ACCOUNT_NUMBER.
    masked, spans = pii.mask("contact jane@x.test about account 12345678901234")
    assert "<EMAIL_ADDRESS>" in masked
    assert "<ACCOUNT_NUMBER>" in masked
    assert "jane@x.test" not in masked
    # spans are on the original text
    assert all(0 <= s.start < s.end for s in spans)


def test_pii_mask_last4_uses_group() -> None:
    _masked, spans = pii.mask("card ending in 4321")
    assert any(s.entity_type == "LAST4" for s in spans)
    last4 = next(s for s in spans if s.entity_type == "LAST4")
    assert "card ending in 4321"[last4.start : last4.end] == "4321"


def test_guardrail_blocks_accusation() -> None:
    report = check_output("The bank violated Regulation E and acted illegally.")
    assert report.ok is False
    assert any("violat" in a for a in report.accusations)
    assert any("illegal" in a for a in report.accusations)


def test_guardrail_flags_pii_and_secret_leak() -> None:
    report = check_output("Your account is 12345678901234", secrets=["12345678901234"])
    assert "ACCOUNT_NUMBER" in report.pii_types
    assert "12345678901234" in report.leaked_secrets
    assert report.ok is False


def test_guardrail_passes_clean_output() -> None:
    report = check_output(
        "Under Regulation E, the institution must investigate the reported error promptly."
    )
    assert report.ok is True


def test_audit_hash_is_deterministic_and_tamper_sensitive() -> None:
    event = AuditEvent(
        ts="2026-10-05T00:00:00+00:00", actor="u1", action="draft.created", resource="case/1"
    )
    h1 = hash_event(GENESIS, event)
    assert h1 == hash_event(GENESIS, event)  # deterministic
    tampered = event.model_copy(update={"action": "case.approved"})
    assert hash_event(GENESIS, tampered) != h1  # any change -> different hash
    # chaining: a different prev_hash yields a different hash
    assert hash_event("other", event) != h1
