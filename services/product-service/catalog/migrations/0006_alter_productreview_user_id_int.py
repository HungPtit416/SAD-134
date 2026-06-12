from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_productreview_reset_ratings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productreview",
            name="user_id",
            field=models.PositiveBigIntegerField(db_index=True),
        ),
    ]
