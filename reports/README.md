## Report helper (KB_Graph / RAG / E-commerce screenshots)

This folder is meant for exporting small artifacts you can paste into the report.

### KB_Graph: export 20 rows + Cypher for screenshot

Run inside the `ai-service` container:

```bash
python manage.py export_kb_graph_sample --user-id user-0001 --limit 20 --out-dir /app/reports
```

Outputs:
- `/app/reports/kb_graph_sample_20_edges.csv` (copy 20 lines into the report)
- `/app/reports/kb_graph_visualize.cypher` (open in Neo4j Browser, run, then screenshot the graph)

### Phase 4: GraphRAG evidence export (JSON)

Run inside the `ai-service` container:

```bash
python manage.py export_graphrag_example --user-id user-0001 --message "Mình cần gợi ý laptop dưới 15 triệu cho học lập trình." --out /app/reports/graphrag_example.json
```

Output:
- `/app/reports/graphrag_example.json` (paste key evidence items into the report)

### Phase 4: Evaluation (offline metrics)

Run inside the `ai-service` container:

```bash
python manage.py eval_phase4 --out-dir /app/reports --limit-users 200 --k 5,10
```

Output:
- `/app/reports/phase4_recsys_metrics.json`

### Phase 4: Product similarity edges (Neo4j SIMILAR)

This creates `(:Product)-[:SIMILAR {score}]->(:Product)` edges using pgvector embeddings of product descriptions.

Run inside the `ai-service` container:

```bash
python manage.py sync_product_similarity_to_graph --topk 5 --min-score 0.35 --bidirectional
```

Verify in Neo4j Browser:

```cypher
MATCH (:Product)-[r:SIMILAR]->(:Product) RETURN count(r);
MATCH (p:Product)-[r:SIMILAR]->(q:Product)
RETURN p.id, q.id, r.score
ORDER BY r.score DESC
LIMIT 20;
```

### Neo4j Browser

Open: `http://localhost:7474`
- user: `neo4j`
- password: `neo4j-password`

