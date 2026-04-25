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

### Neo4j Browser

Open: `http://localhost:7474`
- user: `neo4j`
- password: `neo4j-password`

