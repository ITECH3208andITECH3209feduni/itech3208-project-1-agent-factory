# tests/test_knowledge_base.py
# ──────────────────────────────────────────────────────────────
# Tests for Epic 14: ChromaDB Knowledge Base Engine (PROJ-197)
# ──────────────────────────────────────────────────────────────

import pytest
from fastapi.testclient import TestClient

from api.main import app
from app.knowledge_base.chroma_client import ChromaClientManager
from app.knowledge_base.ingestion import DocumentIngestor, DocumentInput, TextChunker, DocumentParser
from app.knowledge_base.retrieval import QueryRetriever
from skills.knowledge_base import KnowledgeBaseSkill


@pytest.fixture
def memory_client_mgr():
    """Provides an isolated in-memory ChromaDB client for testing."""
    return ChromaClientManager(in_memory=True)


@pytest.fixture
def ingestor(memory_client_mgr):
    return DocumentIngestor(client_manager=memory_client_mgr)


@pytest.fixture
def retriever(memory_client_mgr):
    return QueryRetriever(client_manager=memory_client_mgr)


class TestChromaClientManager:

    def test_health_check(self, memory_client_mgr):
        health = memory_client_mgr.health_check()
        assert health["status"] == "ok"
        assert health["available"] is True

    def test_collection_lifecycle(self, memory_client_mgr):
        col = memory_client_mgr.get_or_create_collection("test_collection")
        assert col is not None
        assert "test_collection" in memory_client_mgr.list_collections()

        stats = memory_client_mgr.get_collection_stats("test_collection")
        assert stats["exists"] is True
        assert stats["count"] == 0

        assert memory_client_mgr.delete_collection("test_collection") is True
        assert "test_collection" not in memory_client_mgr.list_collections()


class TestDocumentIngestion:

    def test_text_chunker(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        long_text = "Sentence one is here. " * 10
        chunks = chunker.split_text(long_text)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= 120

    def test_document_parser_json(self):
        json_content = '{"title": "JSON Doc", "content": "Parsed content text", "source": "unit_test"}'
        doc = DocumentParser.parse(json_content)
        assert doc.title == "JSON Doc"
        assert doc.content == "Parsed content text"
        assert doc.source == "unit_test"

    def test_ingest_document(self, ingestor):
        doc = DocumentInput(
            title="Test Architecture Doc",
            content="Agent Factory is an intelligent multi-agent platform designed for research automation.",
            source="pytest"
        )
        res = ingestor.ingest_document(doc)
        assert res.success is True
        assert res.chunks_count >= 1
        assert res.document_id.startswith("doc_")


class TestQueryRetrieval:

    def test_search_and_list(self, ingestor, retriever):
        doc1 = DocumentInput(
            title="Vector Indexing Policy",
            content="Vector similarity search uses cosine distance to match semantic context.",
            source="pytest_retrieval"
        )
        doc2 = DocumentInput(
            title="SQLite Memory System",
            content="SQLite database retains conversation history across agent sessions.",
            source="pytest_retrieval"
        )
        ingestor.ingest_document(doc1)
        ingestor.ingest_document(doc2)

        # Query vector search
        res = retriever.search("cosine vector similarity search", n_results=2)
        assert res.results_count > 0
        assert "Vector Indexing Policy" in [item.title for item in res.results]

        # List documents
        docs = retriever.list_documents()
        assert len(docs) >= 2
        titles = [d["title"] for d in docs]
        assert "Vector Indexing Policy" in titles
        assert "SQLite Memory System" in titles

    def test_delete_document(self, ingestor, retriever):
        doc = DocumentInput(
            title="Temporary Document",
            content="This document will be deleted.",
            source="pytest_delete",
            document_id="doc_temp_123"
        )
        ingestor.ingest_document(doc)
        assert retriever.delete_document("doc_temp_123") is True
        res = retriever.search("deleted", n_results=5)
        assert all(item.document_id != "doc_temp_123" for item in res.results)


class TestKnowledgeBaseSkill:

    def test_skill_execution(self, ingestor, retriever):
        doc = DocumentInput(
            title="Knowledge Base Skill Spec",
            content="The KnowledgeBaseSkill wraps vector search into a standard BaseSkill interface.",
            source="pytest_skill"
        )
        ingestor.ingest_document(doc)

        skill = KnowledgeBaseSkill(retriever=retriever)
        res = skill("Tell me about KnowledgeBaseSkill")
        assert res.success is True
        assert res.skill_name == "knowledge_base"
        assert len(res.results) > 0
        assert "Knowledge Base" in res.summary


class TestKBManagementAPI:

    def test_kb_api_flow(self):
        client = TestClient(app)

        # 1. Ingest document via API
        ingest_payload = {
            "title": "API Test Document",
            "content": "FastAPI endpoints allow uploading and querying Knowledge Base documents via REST.",
            "source": "api_test",
            "document_id": "doc_api_999"
        }
        res_ingest = client.post("/api/kb/ingest", json=ingest_payload)
        assert res_ingest.status_code == 201
        data_ingest = res_ingest.json()
        assert data_ingest["success"] is True
        assert data_ingest["document_id"] == "doc_api_999"

        # 2. Query via API
        query_payload = {"query": "FastAPI REST endpoints", "n_results": 2}
        res_query = client.post("/api/kb/query", json=query_payload)
        assert res_query.status_code == 200
        data_query = res_query.json()
        assert data_query["count"] > 0
        assert data_query["results"][0]["document_id"] == "doc_api_999"

        # 3. List documents via API
        res_list = client.get("/api/kb/documents")
        assert res_list.status_code == 200
        data_list = res_list.json()
        assert data_list["count"] >= 1
        assert any(d["document_id"] == "doc_api_999" for d in data_list["documents"])

        # 4. Delete document via API
        res_del = client.delete("/api/kb/documents/doc_api_999")
        assert res_del.status_code == 200
        assert res_del.json()["document_id"] == "doc_api_999"
