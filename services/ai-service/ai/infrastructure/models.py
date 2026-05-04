from django.db import models

try:
    from pgvector.django import VectorField
except Exception:  # noqa: BLE001
    VectorField = None  # type: ignore[assignment]


class ChatTurn(models.Model):
    user_id = models.CharField(max_length=64, db_index=True)
    session_id = models.CharField(max_length=64, db_index=True, default="default")
    message = models.TextField()
    answer = models.TextField()
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user_id", "session_id", "created_at"], name="ai_chatturn_session_idx"),
        ]


class DocumentChunk(models.Model):
    """
    A chunk of text that can be retrieved via vector similarity.
    """

    source_type = models.CharField(max_length=32, db_index=True)  # e.g. "product"
    source_id = models.CharField(max_length=64, db_index=True)  # e.g. product id
    title = models.CharField(max_length=255, blank=True, default="")
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    # Gemini embeddings (output_dimensionality=1536 in llm_client) match this column
    embedding = VectorField(dimensions=1536) if VectorField is not None else models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["source_type", "source_id"], name="ai_docchunk_source_idx"),
        ]


class ProductEmbedding(models.Model):
    product_id = models.PositiveBigIntegerField(unique=True, db_index=True)
    embedding = VectorField(dimensions=64) if VectorField is not None else models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)


class UserEmbedding(models.Model):
    user_id = models.CharField(max_length=64, unique=True, db_index=True)
    embedding = VectorField(dimensions=64) if VectorField is not None else models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)


class GnnProductEmbedding(models.Model):
    """
    Product embedding trained from a graph model (e.g., LightGCN).
    Stored separately from the baseline skip-gram embeddings to keep evaluation clean.
    """

    product_id = models.PositiveBigIntegerField(unique=True, db_index=True)
    embedding = VectorField(dimensions=64) if VectorField is not None else models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)


class GnnUserEmbedding(models.Model):
    """
    User embedding trained from a graph model (e.g., LightGCN).
    """

    user_id = models.CharField(max_length=64, unique=True, db_index=True)
    embedding = VectorField(dimensions=64) if VectorField is not None else models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)


class GraphSyncState(models.Model):
    """
    Cursor for incremental sync of interaction-service events into Neo4j.
    """

    key = models.CharField(max_length=32, unique=True, default="default")
    last_event_id = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Graph sync states"

