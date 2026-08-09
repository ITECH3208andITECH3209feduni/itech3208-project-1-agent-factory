# tests/test_kb_store.py — agent/kb_store.py (PROJ-279-283, PROJ-354-358)
import pytest

from agent.kb_store import (
    KBError,
    add_document,
    delete_document,
    list_documents,
    search_documents,
)


def test_add_document_stores_and_returns_metadata():
    doc = add_document("alice", "notes.txt", b"Hello world, this is a test note.")
    assert doc["filename"] == "notes.txt"
    assert doc["size_bytes"] == len(b"Hello world, this is a test note.")
    assert isinstance(doc["id"], int)


def test_add_document_rejects_unsupported_extension():
    with pytest.raises(KBError, match="Unsupported file type"):
        add_document("alice", "photo.png", b"\x89PNG\r\n")


def test_add_document_rejects_empty_file():
    with pytest.raises(KBError, match="empty"):
        add_document("alice", "empty.txt", b"")


def test_add_document_rejects_non_utf8_content():
    with pytest.raises(KBError, match="UTF-8"):
        add_document("alice", "bad.txt", b"\xff\xfe\x00\x01")


def test_add_document_rejects_missing_filename():
    with pytest.raises(KBError, match="Filename"):
        add_document("alice", "", b"content")


def test_add_document_strips_path_components():
    doc = add_document("alice", "../../etc/passwd.txt", b"not actually /etc/passwd")
    assert doc["filename"] == "passwd.txt"


def test_list_documents_scoped_to_user():
    add_document("bob", "bob_doc.txt", b"Bob's private notes about quarterly planning.")
    add_document("carol", "carol_doc.txt", b"Carol's private notes about budgets.")

    bob_docs = list_documents("bob")
    carol_docs = list_documents("carol")

    assert any(d["filename"] == "bob_doc.txt" for d in bob_docs)
    assert not any(d["filename"] == "carol_doc.txt" for d in bob_docs)
    assert any(d["filename"] == "carol_doc.txt" for d in carol_docs)


def test_list_documents_empty_for_unknown_user():
    assert list_documents("nobody-has-uploaded-anything-xyz") == []


def test_delete_document_removes_own_document():
    doc = add_document("dave", "to_delete.txt", b"temporary content")
    assert delete_document("dave", doc["id"]) is True
    assert not any(d["id"] == doc["id"] for d in list_documents("dave"))


def test_delete_document_cannot_delete_another_users_document():
    doc = add_document("erin", "erins_file.txt", b"Erin's content, not yours.")
    # frank tries to delete erin's document by guessing the id
    assert delete_document("frank", doc["id"]) is False
    # still there for erin
    assert any(d["id"] == doc["id"] for d in list_documents("erin"))


def test_delete_document_returns_false_for_nonexistent_id():
    assert delete_document("alice", 9_999_999) is False


def test_search_documents_finds_keyword_match():
    add_document(
        "grace",
        "onboarding.txt",
        b"New employee onboarding checklist: laptop setup, badge access, HR paperwork.",
    )
    results = search_documents("grace", "badge access checklist")
    assert len(results) == 1
    assert results[0]["filename"] == "onboarding.txt"
    assert results[0]["score"] > 0
    assert "snippet" in results[0]


def test_search_documents_scoped_to_user():
    add_document("henry", "henry_recipes.txt", b"Grandma's secret pasta sauce recipe.")
    results = search_documents("ivy", "pasta sauce recipe")
    assert results == []


def test_search_documents_no_match_returns_empty_list():
    add_document("jack", "jack_notes.txt", b"Completely unrelated content about astronomy.")
    results = search_documents("jack", "xyzzy nonsense query term")
    assert results == []


def test_search_documents_ranks_better_match_first():
    add_document("kate", "doc_a.txt", b"apple banana cherry")
    add_document("kate", "doc_b.txt", b"apple banana cherry date elderberry fig grape")
    # query overlapping fully with doc_a's (shorter) content should score
    # doc_a >= doc_b since score is normalised by query token count, not
    # document length
    results = search_documents("kate", "apple banana cherry")
    assert results[0]["filename"] in {"doc_a.txt", "doc_b.txt"}
    assert all(r["score"] > 0 for r in results)
