from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0007_rename_productreview_to_productrating"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productrating",
            name="product",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="product_ratings",
                to="catalog.product",
            ),
        ),
    ]
