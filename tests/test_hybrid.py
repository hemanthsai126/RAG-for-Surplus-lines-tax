from app.retrieval.hybrid import reciprocal_rank_fusion


def test_rrf_fuses_lists():
    fused = reciprocal_rank_fusion([[0, 1], [1, 2]], k=60)
    # doc 1 appears in both lists → should rank highly
    best = [i for i, _ in fused[:2]]
    assert 1 in best
