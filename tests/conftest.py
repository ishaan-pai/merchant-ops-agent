# tests/conftest.py
"""
Offline eval harness.

Freezes the agent's "today" and swaps the Shopify GraphQL client for one that
serves tests/fixtures/shopifyStore.json, so CI results only change when the
agent changes. Claude is still called for real.
"""
import json
import os
import re
from pathlib import Path

import pytest

# Set before any test module imports agent/shopify: the system prompt and the
# Shopify client both read these at import time.
os.environ["AGENT_TODAY"] = "2026-11-19"
os.environ.setdefault("SHOPIFY_SHOP", "eval-fixture")

STORE = json.loads(
    (Path(__file__).parent / "fixtures" / "shopifyStore.json").read_text(encoding="utf-8")
)
ORDER_RANGE = re.compile(r"processed_at:>='([^']+)' processed_at:<'([^']+)'")
TITLE_SEARCH = re.compile(r"title:\*(.*)\*")


def _products(q: str | None) -> list[dict]:
    if q is None:
        return STORE["products"]
    if q == "status:active":
        return [p for p in STORE["products"] if p["status"] == "ACTIVE"]
    if m := TITLE_SEARCH.fullmatch(q):
        term = m.group(1).lower()
        return [p for p in STORE["products"] if term in p["title"].lower()]
    raise AssertionError(f"fake Shopify can't handle products query {q!r}")


def fake_graphql(query: str, variables: dict | None = None) -> dict:
    variables = variables or {}
    if "discountCodeBasicCreate" in query:
        raise AssertionError("create_discount reached Shopify without merchant approval")
    if "orders(" in query:
        m = ORDER_RANGE.fullmatch(variables["q"])
        if not m:
            raise AssertionError(f"fake Shopify can't handle orders query {variables['q']!r}")
        start, end = m.groups()
        nodes = [o for o in STORE["orders"] if start <= o["processedAt"] < end]
        return {"orders": {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    if "products(" in query:
        return {"products": {"nodes": _products(variables.get("q"))}}
    raise AssertionError(f"fake Shopify has no handler for:\n{query}")


@pytest.fixture(autouse=True)
def offline_shopify(monkeypatch):
    import tools

    monkeypatch.setattr(tools, "graphql", fake_graphql)