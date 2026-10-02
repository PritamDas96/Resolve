"""Domain models and deterministic logic.

Pydantic domain models, the CFPB taxonomy enums, and the deterministic deadline
calculator (``deadlines.py``) whose rules each cite a CFR paragraph. The LLM
never performs date arithmetic — it calls this calculator.
"""
