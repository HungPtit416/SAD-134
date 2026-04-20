# HNSW indexes for faster cosine similarity search at scale (pgvector).

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0004_graph_sync_state"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS ai_documentchunk_embedding_hnsw_cosine
            ON ai_documentchunk
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
            """,
            reverse_sql="DROP INDEX IF EXISTS ai_documentchunk_embedding_hnsw_cosine;",
        ),
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS ai_productembedding_embedding_hnsw_cosine
            ON ai_productembedding
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
            """,
            reverse_sql="DROP INDEX IF EXISTS ai_productembedding_embedding_hnsw_cosine;",
        ),
    ]
