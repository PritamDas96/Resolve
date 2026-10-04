"""RESOLVE review console — a professional Streamlit UI (PLAN §11.3).

Run with ``streamlit run src/resolve/ui/streamlit_app.py`` (or ``./make.ps1 ui``).

Two modes:
* **Demo** — a scripted gateway + fixed Reg E evidence, so the full flow (route ->
  retrieve -> cited draft -> review) always works with no API quota or Qdrant.
* **Live** — the real Gemini gateway + the sparse Qdrant index (needs Docker up,
  ``make index-sparse``, and Gemini quota).

The UI calls the agent in-process; nothing here holds secrets.
"""

from __future__ import annotations

import json
from datetime import date

import streamlit as st

from resolve.agent.graph_single import run_case
from resolve.agent.tools import make_retriever
from resolve.config import get_settings
from resolve.llm.gateway import FakeGateway, build_gateway
from resolve.retrieval.search import SearchResult
from resolve.security import pii
from resolve.security.guardrails import check_output

EXAMPLES = {
    "Unauthorized debit (Reg E)": (
        "Someone made two charges on my debit card that I did not authorize. I called the "
        "bank on 02/03/2025 to report the error, but weeks later they still have not given "
        "me provisional credit while they investigate. What are they required to do?"
    ),
    "Credit-card billing error (Reg Z)": (
        "There is a charge on my credit card statement for something I never bought. I "
        "disputed it in writing but the bank keeps billing me for it."
    ),
    "Mortgage escrow (Reg X)": (
        "My mortgage servicer is mishandling my escrow account and will not respond to my "
        "written notice of error about the shortage."
    ),
}

_CSS = """
<style>
  .block-container {padding-top: 2rem; max-width: 1200px;}
  .chip {display:inline-block; background:#eef2ff; color:#3730a3; border-radius:12px;
         padding:1px 9px; margin:2px 4px 2px 0; font-size:0.72rem; font-family:monospace;}
  .ev {border-left:3px solid #6366f1; padding:6px 12px; margin:6px 0; background:#fafafe;}
  .ev code {color:#3730a3;}
  .fact {border-left:3px solid #10b981; padding-left:10px; margin:6px 0;}
  .nonfact {color:#4b5563; padding-left:10px; margin:6px 0;}
  .ok {color:#047857; font-weight:600;} .bad {color:#b91c1c; font-weight:600;}
</style>
"""


def _demo_retriever(*_a: object, **_k: object) -> list[SearchResult]:
    def _r(ref: str, para: str, text: str) -> SearchResult:
        return SearchResult(
            chunk_id=ref,
            citation_id=ref,
            section="1005.11",
            regulation="Reg E",
            paragraph=para,
            is_interpretation=False,
            interprets=None,
            heading_path=f"Reg E > §1005.11 Procedures for resolving errors > {para}",
            text=text,
            score=1.0,
        )

    return [
        _r(
            "1005.11(c)(1)@2023-01-01",
            "(c)(1)",
            "The financial institution shall investigate promptly and determine whether "
            "an error occurred within 10 business days, except as provided in (c)(2)-(4).",
        ),
        _r(
            "1005.11(c)(2)@2023-01-01",
            "(c)(2)",
            "If the institution needs more time it may take up to 45 days, provided it "
            "provisionally credits the consumer's account within 10 business days.",
        ),
    ]


def _demo_gateway() -> FakeGateway:
    route = json.dumps(
        {
            "family": "deposits",
            "issue": "Problem with a lender or other company charging your account",
            "confidence": 0.93,
            "legal_question": "time limit for provisional credit after a debit-card error",
            "regulation_hint": "Reg E",
            "key_facts": ["unauthorized debit", "notice by phone"],
        }
    )
    letter = json.dumps(
        {
            "subject": "Your debit-card error claim and the applicable investigation timeline",
            "sentences": [
                {
                    "text": "Thank you for notifying us about the unauthorized charges "
                    "on your debit card.",
                    "is_factual_claim": False,
                    "citations": [],
                },
                {
                    "text": "Under Regulation E, the institution must investigate promptly and "
                    "determine whether an error occurred within 10 business days of the notice.",
                    "is_factual_claim": True,
                    "citations": [{"kind": "regulation", "ref": "1005.11(c)(1)@2023-01-01"}],
                },
                {
                    "text": "If more time is needed, the institution must provisionally "
                    "credit your account within 10 business days while it investigates.",
                    "is_factual_claim": True,
                    "citations": [{"kind": "regulation", "ref": "1005.11(c)(2)@2023-01-01"}],
                },
            ],
            "deadlines_referenced": ["determination_or_provisional_credit"],
            "abstained": False,
        }
    )
    return FakeGateway([route, letter])


def _letter_text(result: object) -> str:
    return " ".join(s.text for s in result.letter.sentences)  # type: ignore[attr-defined]


def main() -> None:
    """Render the review console."""
    st.set_page_config(
        page_title="RESOLVE — Complaint Review Console", page_icon="⚖️", layout="wide"
    )
    st.markdown(_CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.title("⚖️ RESOLVE")
        st.caption("Evaluated, guarded, observable complaint-resolution agent.")
        mode = st.radio("Mode", ["Demo (no quota)", "Live (Gemini)"], index=0)
        as_of = st.date_input("Regulation as-of date", value=date(2025, 3, 14))
        st.divider()
        st.caption(
            "Demo mode uses scripted evidence so the full flow always works. "
            "Live mode needs Docker up, `make index-sparse`, and Gemini quota."
        )

    st.title("Complaint Review Console")
    st.write(
        "Submit a consumer complaint. The agent routes it, retrieves the governing "
        "regulation **as of the complaint date**, drafts a cited response, and shows every "
        "guardrail — or safely abstains when the evidence is thin."
    )

    choice = st.selectbox("Example complaints", ["(write my own)", *EXAMPLES])
    default = EXAMPLES.get(choice, "")
    complaint = st.text_area(
        "Complaint narrative", value=default, height=150, placeholder="Describe the complaint…"
    )

    if not st.button("Resolve complaint", type="primary", use_container_width=True):
        return
    if not complaint.strip():
        st.warning("Please enter a complaint.")
        return

    settings = get_settings()
    is_demo = mode.startswith("Demo")
    try:
        gateway = _demo_gateway() if is_demo else build_gateway(settings)
        retrieve = _demo_retriever if is_demo else make_retriever(settings)
        with st.spinner("Routing → retrieving → drafting…"):
            result = run_case(
                gateway,
                case_id="ui-case",
                complaint=complaint,
                retrieve=retrieve,
                router_model="demo" if is_demo else settings.router_model,
                drafter_model="demo" if is_demo else settings.drafter_model,
                as_of=as_of,
                mask=lambda t: pii.mask(t)[0],
            )
    except Exception as exc:
        st.error(
            f"Run failed: {exc}\n\nIn Live mode this usually means Docker/Qdrant is down "
            "or Gemini quota is exhausted. Try Demo mode."
        )
        return

    # --- PII masking shown transparently ---
    masked, spans = pii.mask(complaint)
    if spans:
        with st.expander(f"🔒 PII masked before the model saw the complaint ({len(spans)} spans)"):
            st.code(masked)

    # --- routing ---
    st.subheader("Routing")
    c1, c2, c3 = st.columns(3)
    c1.metric("Queue (family)", result.route.family)
    c2.metric("Issue", result.route.issue)
    c3.metric("Confidence", f"{result.route.confidence:.0%}")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Drafted letter")
        if result.letter.abstained:
            st.warning(f"**Abstained.** {result.letter.abstain_reason}")
        else:
            st.markdown(f"**Subject:** {result.letter.subject}")
            for s in result.letter.sentences:
                chips = "".join(f"<span class='chip'>{c.ref}</span>" for c in s.citations)
                css = "fact" if s.is_factual_claim else "nonfact"
                st.markdown(f"<div class='{css}'>{s.text} {chips}</div>", unsafe_allow_html=True)

    with right:
        st.subheader("Evidence (point-in-time)")
        for e in result.evidence_refs:
            st.markdown(f"<span class='chip'>{e}</span>", unsafe_allow_html=True)
        st.subheader("Guardrails")
        guard = check_output(_letter_text(result))
        cite_ok = result.citations_valid
        st.markdown(
            f"- Citations grounded: <span class='{'ok' if cite_ok else 'bad'}'>"
            f"{'PASS' if cite_ok else 'FAIL'}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"- No legal accusation: <span class='{'ok' if not guard.accusations else 'bad'}'>"
            f"{'PASS' if not guard.accusations else 'FAIL'}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"- No PII in output: <span class='{'ok' if not guard.pii_types else 'bad'}'>"
            f"{'PASS' if not guard.pii_types else 'FAIL'}</span>",
            unsafe_allow_html=True,
        )

    # --- human review ---
    st.divider()
    st.subheader("Human review")
    r1, r2 = st.columns(2)
    if r1.button("✅ Approve", use_container_width=True):
        st.success(
            "Approved. In the multi-agent graph this resumes the paused case and "
            "appends an `audit_log` entry (case.approved)."
        )
    if r2.button("✏️ Request changes", use_container_width=True):
        st.info("Sent back for revision (audit event: draft.rejected).")


main()
