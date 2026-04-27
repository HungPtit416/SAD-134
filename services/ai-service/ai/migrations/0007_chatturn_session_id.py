from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0006_gnn_embeddings"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatturn",
            name="session_id",
            field=models.CharField(db_index=True, default="default", max_length=64),
        ),
        migrations.AddIndex(
            model_name="chatturn",
            index=models.Index(fields=["user_id", "session_id", "created_at"], name="ai_chatturn_session_idx"),
        ),
    ]

