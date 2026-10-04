# ADR-004: Single-agent vs multi-agent graph

- **Status:** accepted (multi-agent adopted; full benchmark pending quota)
- **Date:** 2026-10-04
- **Deciders:** Pritam Das

## Context

Phase 4 shipped a single-agent pipeline (`graph_single`). Phase 7 asks whether a
multi-agent graph (`graph_multi`) is worth the extra complexity, measured on accuracy,
latency, cost and injection ASR. Two forces drive the design: a **trust boundary**
(the component reading the untrusted narrative must not hold privileged tools) and
**human review** before anything is finalised.

## Options considered

1. **Single agent** — simplest; one model call chain. But the same agent reads the
   narrative *and* would hold account tools, so an injected instruction has a path to a
   privileged action; no natural pause point for review.
2. **Multi-agent graph** — router (reads narrative, **no tools**) → parallel regulation
   + account agents (account agent has tools but never sees the narrative) → drafter →
   **human-review interrupt**. Fan-out/fan-in with an evidence reducer; durable,
   interruptible, resumable.

## Decision

Adopt the **multi-agent graph** for the trust-boundary and human-in-the-loop
properties, while keeping `graph_single` as the baseline the eval gate compares
against. The key security win: the only component that reads the untrusted narrative
(router) has no tools, so a prompt injection cannot reach a privileged action — this is
measured by injection ASR (single vs multi) once LLM quota allows the full run.

## Consequences

- Positive: injection has no privileged path; cases pause for review and resume
  (`/v1/cases/{id}/decision`); parallel agents cut wall-clock; stopping conditions
  (`limits.py`) bound cost.
- Negative / trade-offs: more moving parts and state; checkpointing added. Committed
  HITL uses an in-memory saver (interrupt/resume tested); `AsyncPostgresSaver` is the
  one-dependency swap for restart-durability.
- Follow-ups: run the full single-vs-multi eval (accuracy, p95, cost, injection ASR)
  and record the numbers in the README when quota is available.
