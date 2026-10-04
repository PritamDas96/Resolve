"""Unit tests for tool selection + MCP server wiring (offline)."""

from __future__ import annotations

from pathlib import Path

from resolve.mcp_server import tool_selection as ts


def test_tool_selection_items() -> None:
    data = ts.items()
    assert len(data) == 16
    assert {it.expected_tool for it in data} <= set(ts.TOOLS)
    assert len({it.id for it in data}) == len(data)


def test_baseline_selector_accuracy_is_reported() -> None:
    acc = ts.selection_accuracy()
    assert 0.0 <= acc <= 1.0
    assert acc >= 0.8  # the keyword baseline should handle most authored prompts


def test_tool_selection_build_round_trips(tmp_path: Path) -> None:
    from resolve.eval.schemas import read_jsonl, write_jsonl

    out = tmp_path / "tool_selection.jsonl"
    assert write_jsonl(out, ts.items()) == 16
    assert read_jsonl(out, ts.ToolSelectionItem) == ts.items()


def test_mcp_server_imports_and_registers_tools() -> None:
    from resolve.mcp_server import server

    assert server.server.name == "resolve"
    # The five tool callables are defined at module scope.
    for name in (
        "search_regulations",
        "compute_deadlines",
        "get_account",
        "get_account_disputes",
        "get_complaint",
    ):
        assert hasattr(server, name)
