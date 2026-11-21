"""Search quality scorecard: runs labeled queries across BM25-only, Vector-only, and Hybrid,
and computes Recall@5 and Mean Reciprocal Rank (MRR) across tuning, held-out, and combined sets.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List
from app.search_service import search_hybrid

LABELED_QUERIES = [
    # Typos (10 queries)
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
    
    # Hinglish queries (10 queries)
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

    # Brand + Category / Synonyms (10 queries)
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

# Split 30 queries into 15 Tuning and 15 Held-out (5 typos, 5 hinglish, 5 synonyms each)
TUNING_QUERIES = [
    # 5 typos
    LABELED_QUERIES[0], LABELED_QUERIES[1], LABELED_QUERIES[2], LABELED_QUERIES[3], LABELED_QUERIES[4],
    # 5 hinglish
    LABELED_QUERIES[10], LABELED_QUERIES[11], LABELED_QUERIES[12], LABELED_QUERIES[13], LABELED_QUERIES[14],
    # 5 synonyms
    LABELED_QUERIES[20], LABELED_QUERIES[21], LABELED_QUERIES[22], LABELED_QUERIES[23], LABELED_QUERIES[24],
]

HELD_OUT_QUERIES = [
    # 5 typos
    LABELED_QUERIES[5], LABELED_QUERIES[6], LABELED_QUERIES[7], LABELED_QUERIES[8], LABELED_QUERIES[9],
    # 5 hinglish
    LABELED_QUERIES[15], LABELED_QUERIES[16], LABELED_QUERIES[17], LABELED_QUERIES[18], LABELED_QUERIES[19],
    # 5 synonyms
    LABELED_QUERIES[25], LABELED_QUERIES[26], LABELED_QUERIES[27], LABELED_QUERIES[28], LABELED_QUERIES[29],
]


async def evaluate_search_mode(mode: str, queries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run labeled test queries for a given search mode and evaluate metrics."""
    total_queries = len(queries)
    recall_at_5_hits = 0
    reciprocal_ranks = []
    details = []

    for item in queries:
        q = item["query"]
        prefixes = item["expected_sku_prefixes"]
        res = await search_hybrid(q=q, size=5, search_mode=mode)
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

    recall_at_5 = round(recall_at_5_hits / total_queries, 4) if total_queries else 0.0
    mrr = round(sum(reciprocal_ranks) / total_queries, 4) if total_queries else 0.0

    return {
        "mode": mode,
        "total_queries": total_queries,
        "recall_at_5": recall_at_5,
        "mrr": mrr,
        "details": details,
    }


async def run_full_scorecard() -> Dict[str, Any]:
    """Compare BM25-only, Vector-only, and Hybrid across tuning, held-out, and combined sets."""
    modes = ["bm25", "vector", "hybrid"]
    results: Dict[str, Any] = {
        "tuning": {},
        "held_out": {},
        "combined": {},
    }

    for mode in modes:
        tuning_res = await evaluate_search_mode(mode, TUNING_QUERIES)
        held_out_res = await evaluate_search_mode(mode, HELD_OUT_QUERIES)

        # Aggregate combined without repeating queries
        combined_details = tuning_res["details"] + held_out_res["details"]
        combined_hits = sum(1 for d in combined_details if d.get("rank") is not None and d["rank"] <= 5)
        combined_rr = sum(1.0 / d["rank"] for d in combined_details if d.get("rank") is not None and d["rank"] <= 5)
        total_q = len(combined_details)

        results["tuning"][mode] = tuning_res
        results["held_out"][mode] = held_out_res
        results["combined"][mode] = {
            "mode": mode,
            "total_queries": total_q,
            "recall_at_5": round(combined_hits / total_q, 4) if total_q else 0.0,
            "mrr": round(combined_rr / total_q, 4) if total_q else 0.0,
            "details": combined_details,
        }

    scorecard = {
        "summary": {
            "tuning": [
                {"mode": "BM25 Only", "recall_at_5": results["tuning"]["bm25"]["recall_at_5"], "mrr": results["tuning"]["bm25"]["mrr"]},
                {"mode": "Vector Only", "recall_at_5": results["tuning"]["vector"]["recall_at_5"], "mrr": results["tuning"]["vector"]["mrr"]},
                {"mode": "Hybrid (BM25 + kNN)", "recall_at_5": results["tuning"]["hybrid"]["recall_at_5"], "mrr": results["tuning"]["hybrid"]["mrr"]},
            ],
            "held_out": [
                {"mode": "BM25 Only", "recall_at_5": results["held_out"]["bm25"]["recall_at_5"], "mrr": results["held_out"]["bm25"]["mrr"]},
                {"mode": "Vector Only", "recall_at_5": results["held_out"]["vector"]["recall_at_5"], "mrr": results["held_out"]["vector"]["mrr"]},
                {"mode": "Hybrid (BM25 + kNN)", "recall_at_5": results["held_out"]["hybrid"]["recall_at_5"], "mrr": results["held_out"]["hybrid"]["mrr"]},
            ],
            "combined": [
                {"mode": "BM25 Only", "recall_at_5": results["combined"]["bm25"]["recall_at_5"], "mrr": results["combined"]["bm25"]["mrr"]},
                {"mode": "Vector Only", "recall_at_5": results["combined"]["vector"]["recall_at_5"], "mrr": results["combined"]["vector"]["mrr"]},
                {"mode": "Hybrid (BM25 + kNN)", "recall_at_5": results["combined"]["hybrid"]["recall_at_5"], "mrr": results["combined"]["hybrid"]["mrr"]},
            ],
        },
        "results": results,
    }

    export_paths = [
        "scorecard_results.json",
        os.path.join(os.path.dirname(__file__), "..", "scorecard_results.json"),
    ]
    for p in export_paths:
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(scorecard, f, indent=2)
        except Exception:
            pass

    return scorecard


if __name__ == "__main__":
    print("Running Search Quality Scorecard across 30 benchmark queries (15 Tuning, 15 Held-Out)...")
    results = asyncio.run(run_full_scorecard())
    
    print("\n=== TUNING SET (15 queries) ===")
    print(f"{'Mode':<25} | {'Recall@5':<10} | {'MRR':<10}")
    print("-" * 52)
    for row in results["summary"]["tuning"]:
        print(f"{row['mode']:<25} | {row['recall_at_5']:<10.2%} | {row['mrr']:<10.4f}")

    print("\n=== HELD-OUT SET (15 queries) ===")
    print(f"{'Mode':<25} | {'Recall@5':<10} | {'MRR':<10}")
    print("-" * 52)
    for row in results["summary"]["held_out"]:
        print(f"{row['mode']:<25} | {row['recall_at_5']:<10.2%} | {row['mrr']:<10.4f}")

    print("\n=== COMBINED (30 queries) ===")
    print(f"{'Mode':<25} | {'Recall@5':<10} | {'MRR':<10}")
    print("-" * 52)
    for row in results["summary"]["combined"]:
        print(f"{row['mode']:<25} | {row['recall_at_5']:<10.2%} | {row['mrr']:<10.4f}")

    print("\nScorecard results exported to scorecard_results.json")
