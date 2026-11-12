from app.ingestion import split_text, build_chunks
from app.retriever import tokenize

def test_split_respects_size():
    chunks = split_text("A" * 3000, 500, 50)
    assert chunks and all(len(c) <= 500 for c in chunks)

def test_chunk_metadata_preserved():
    docs = [{"id":"x","title":"Example","text":"A paragraph.\n\nAnother paragraph.","source":"x.md","source_type":"generic_example","roles":[]}]
    chunks = build_chunks(docs, 100, 10)
    assert chunks[0]["chunk_id"].startswith("x::")
    assert chunks[0]["source_type"] == "generic_example"

def test_tokenizer_handles_paths_and_codes():
    assert "dealer-mapping" in tokenize("/admin/dealer-mapping")

def test_bm25_retrieves_product_and_generic_sources():
    from app.retriever import HybridRetriever
    docs = [
        {"id":"product","title":"Dealer mapping","text":"Add a dealer mapping using Exchange and Terminal ID.","source":"catalog.json","source_type":"product_knowledge","roles":["admin"]},
        {"id":"example","title":"Password reset","text":"If a password reset email does not arrive, check spam and request a new link.","source":"example.md","source_type":"generic_example","roles":[]},
    ]
    chunks = build_chunks(docs, 500, 50)
    retriever = HybridRetriever(chunks, mode="bm25")
    assert retriever.search("how to add a dealer mapping", 1)[0]["source_type"] == "product_knowledge"
    assert retriever.search("password reset email not arriving", 1)[0]["source_type"] == "generic_example"
