"""Search quality scorecard: runs labeled queries across BM25-only, Vector-only, and Hybrid,
and computes Recall@5 and Mean Reciprocal Rank (MRR).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from app.search_service import search_hybrid

LABELED_QUERIES = [
    # Typos
    {"query": "bluetoth earphones", "expected_sku_prefixes": ["EL-BOA", "EL-NOI", "EL-JBL", "EL-1PL"], "type": "typo"},
    {"query": "samsng galxy", "expected_sku_prefixes": ["EL-SAM"], "type": "typo"},
    {"query": "iphon 15", "expected_sku_prefixes": ["EL-APP"], "type": "typo"},
    {"query": "hedphones", "expected_sku_prefixes": ["EL-SON", "EL-JBL", "EL-BOA"], "type": "typo"},
    {"query": "ashirvad ata", "expected_sku_prefixes": ["GR-AAS"], "type": "typo"},
    {"query": "parle g biskut", "expected_sku_prefixes": ["GR-PAR"], "type": "typo"},
    {"query": "leves jeans", "expected_sku_prefixes": ["FA-LEV"], "type": "typo"},
    {"query": "himalya neem", "expected_sku_prefixes": ["PC-HIM"], "type": "typo"},
    {"query": "prestig cooker", "expected_sku_prefixes": ["HO-PRE"], "type": "typo"},
    {"query": "bata shoes", "expected_sku_prefixes": ["FA-BAT"], "type": "typo"},
    
    # Hinglish queries
    {"query": "sasta atta", "expected_sku_prefixes": ["GR-AAS"], "type": "hinglish"},
    {"query": "sasta phone", "expected_sku_prefixes": ["EL-SAM-001", "EL-REL", "EL-XIA", "EL-1PL"], "type": "hinglish"},
    {"query": "kam daam rice", "expected_sku_prefixes": ["GR-FOR", "GR-DAA"], "type": "hinglish"},
    {"query": "nahane ka sabun", "expected_sku_prefixes": ["PC-DOV", "PC-DET", "PC-LIF"], "type": "hinglish"},
    {"query": "chai patti", "expected_sku_prefixes": ["GR-TAT", "GR-RED", "GR-TAJ"], "type": "hinglish"},
    {"query": "sarso ka tel", "expected_sku_prefixes": ["GR-FOR-002"], "type": "hinglish"},
    {"query": "doodh powder", "expected_sku_prefixes": ["GR-NES-001"], "type": "hinglish"},
    {"query": "daant ka paste", "expected_sku_prefixes": ["PC-COL", "PC-SEN", "PC-HIM", "GR-PAT-002"], "type": "hinglish"},
    {"query": "khana pakane ka bartan", "expected_sku_prefixes": ["HO-PRE", "HO-HAW"], "type": "hinglish"},
    {"query": "juta sports", "expected_sku_prefixes": ["FA-NIK", "FA-PUM", "FA-SPA", "FA-CAM"], "type": "hinglish"},

    # Brand + Category / Synonyms
    {"query": "wireless earbuds with anc", "expected_sku_prefixes": ["EL-1PL-003", "EL-BOA-005", "EL-REL-003", "EL-APP-003"], "type": "synonym"},
    {"query": "gaming laptop rtx", "expected_sku_prefixes": ["EL-LEN-002", "EL-HP-002"], "type": "synonym"},
    {"query": "smartwatch bluetooth calling", "expected_sku_prefixes": ["EL-BOA", "EL-NOI", "FA-FAS-001"], "type": "synonym"},
    {"query": "mustard oil cold pressed", "expected_sku_prefixes": ["GR-FOR-002"], "type": "synonym"},
    {"query": "basmati rice biryani", "expected_sku_prefixes": ["GR-FOR-004", "GR-DAA-002"], "type": "synonym"},
    {"query": "cotton kurta women", "expected_sku_prefixes": ["FA-BIB", "FA-WWO"], "type": "synonym"},
    {"query": "men formal suit navy", "expected_sku_prefixes": ["FA-PET-003"], "type": "synonym"},
    {"query": "non stick kadhai", "expected_sku_prefixes": ["HO-HAW-002", "HO-PRE-003"], "type": "synonym"},
    {"query": "hair fall control oil", "expected_sku_prefixes": ["PC-HIM-002", "PC-MAM-001", "PC-PAR-005"], "type": "synonym"},
    {"query": "anti dandruff shampoo", "expected_sku_prefixes": ["PC-HNS", "PC-TRE"], "type": "synonym"},
]


def evaluate_search_mode(mode: str) -> Dict[str, Any]:
    """Run labeled test queries for a given search mode and evaluate metrics."""
    total_queries = len(LABELED_QUERIES)
    recall_at_5_hits = 0
    reciprocal_ranks = []
    details = []

    for item in LABELED_QUERIES:
        q = item["query"]
        prefixes = item["expected_sku_prefixes"]
        res = search_hybrid(q=q, size=5, search_mode=mode)
        hits = res.get("hits", [])
        
        hit_skus = [h.get("sku", "") for h in hits]
        # Check first matching rank
        first_match_rank = None
        for rank, sku in enumerate(hit_skus, start=1):
            if any(sku.startswith(p) for p in prefixes):
                first_match_rank = rank
                break

        if first_match_rank is not None and first_match_rank <= 5:
            recall_at_5_hits += 1
            reciprocal_ranks.append(1.0 / first_match_rank)
        else:
            reciprocal_ranks.append(0.0)

        details.append({
            "query": q,
            "type": item["type"],
            "expected": prefixes,
            "top_hits": hit_skus[:3],
            "rank": first_match_rank,
        })

    recall_at_5 = round(recall_at_5_hits / total_queries, 4)
    mrr = round(sum(reciprocal_ranks) / total_queries, 4)

    return {
        "mode": mode,
        "total_queries": total_queries,
        "recall_at_5": recall_at_5,
        "mrr": mrr,
        "details": details,
    }


def run_full_scorecard() -> Dict[str, Any]:
    """Compare BM25-only, Vector-only, and Hybrid."""
    bm25 = evaluate_search_mode("bm25")
    vector = evaluate_search_mode("vector")
    hybrid = evaluate_search_mode("hybrid")

    scorecard = {
        "summary": [
            {"mode": "BM25 Only", "recall_at_5": bm25["recall_at_5"], "mrr": bm25["mrr"]},
            {"mode": "Vector Only", "recall_at_5": vector["recall_at_5"], "mrr": vector["mrr"]},
            {"mode": "Hybrid (BM25 + kNN)", "recall_at_5": hybrid["recall_at_5"], "mrr": hybrid["mrr"]},
        ],
        "bm25": bm25,
        "vector": vector,
        "hybrid": hybrid,
    }
    return scorecard


if __name__ == "__main__":
    print("Running Search Quality Scorecard across 30 benchmark queries...")
    results = run_full_scorecard()
    print("\n=== SCORECARD RESULTS ===")
    print(f"{'Mode':<25} | {'Recall@5':<10} | {'MRR':<10}")
    print("-" * 52)
    for row in results["summary"]:
        print(f"{row['mode']:<25} | {row['recall_at_5']:<10.2%} | {row['mrr']:<10.4f}")

