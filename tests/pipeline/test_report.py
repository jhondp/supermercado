from supermercado.pipeline.report import render_issue_body

FAILURE = {
    "store": "lider",
    "error_class": "BlockedError",
    "message": "captcha | page",
    "at": "2026-09-28T09:00:00+00:00",
}
ALERT = {
    "store": "jumbo",
    "item_id": "rice",
    "message": "sku 1626: approved size 1 kg, store now reports 0.9 kg",
}


def test_no_problems_means_empty_body() -> None:
    assert render_issue_body({"week": "2026-W40", "failures": [], "alerts": []}) == ""


def test_failures_name_store_error_class_and_time() -> None:
    body = render_issue_body({"week": "2026-W40", "failures": [FAILURE], "alerts": []})
    assert "2026-W40" in body
    assert "| lider | `BlockedError` | 2026-09-28T09:00:00+00:00 | captcha \\| page |" in body
    assert "collect --store" in body


def test_alerts_are_listed_as_size_changes() -> None:
    body = render_issue_body({"week": "2026-W40", "failures": [], "alerts": [ALERT]})
    assert "Size changes" in body
    assert "| jumbo | rice |" in body


def test_cells_neutralize_mentions_backticks_and_line_breaks() -> None:
    failure = {**FAILURE, "message": "@octocat `x`\r\nboom"}
    body = render_issue_body({"week": "2026-W40", "failures": [failure], "alerts": []})
    assert "@octocat" not in body
    assert "@\u200boctocat 'x'" in body
    assert "\r" not in body


def test_dropped_rows_are_listed_and_sanitized() -> None:
    dropped = ["jumbo/milk: missing or non-positive price", "lider/rice: @octocat | `x`"]
    body = render_issue_body({"week": "2026-W40", "failures": [], "alerts": [], "dropped": dropped})
    assert "### Dropped rows" in body
    assert "| jumbo/milk: missing or non-positive price |" in body
    assert "@octocat" not in body
    assert "lider/rice: @\u200boctocat \\| 'x'" in body


def test_dropped_rows_are_truncated() -> None:
    dropped = [f"jumbo/item{i}: sku {i} not returned" for i in range(100)]
    body = render_issue_body(
        {"week": "2026-W40", "failures": [FAILURE], "alerts": [], "dropped": dropped}
    )
    assert "jumbo/item0:" in body
    assert "jumbo/item99:" not in body
    assert "and 50 more" in body
