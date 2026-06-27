from __future__ import annotations

import pytest

from app.services import graph_store


def test_build_graph_store_falls_back_when_neo4j_driver_missing(monkeypatch):
    monkeypatch.setattr(graph_store.settings, "neo4j_enabled", True)
    monkeypatch.setattr(graph_store, "GraphDatabase", None)

    store = graph_store.build_graph_store()

    assert isinstance(store, graph_store.NullGraphStore)
    assert store.enabled is False


def test_build_graph_store_required_raises_when_neo4j_driver_missing(monkeypatch):
    monkeypatch.setattr(graph_store.settings, "neo4j_enabled", True)
    monkeypatch.setattr(graph_store, "GraphDatabase", None)

    with pytest.raises(RuntimeError, match="neo4j driver is not installed"):
        graph_store.build_graph_store(required=True)


def test_build_graph_store_required_raises_when_neo4j_disabled(monkeypatch):
    monkeypatch.setattr(graph_store.settings, "neo4j_enabled", False)

    with pytest.raises(RuntimeError, match="neo4j is disabled"):
        graph_store.build_graph_store(required=True)
