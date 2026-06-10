from django.db import migrations, models
import django.db.models.deletion


def reset_seeded_ratings(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Product.objects.all().update(ratings=0, no_of_ratings=0)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_remove_product_actual_price_and_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(db_index=True, max_length=128)),
                ("stars", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reviews",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="productreview",
            constraint=models.UniqueConstraint(
                fields=("user_id", "product"),
                name="uniq_product_review_per_user",
            ),
        ),
        migrations.RunPython(reset_seeded_ratings, migrations.RunPython.noop),
    ]
