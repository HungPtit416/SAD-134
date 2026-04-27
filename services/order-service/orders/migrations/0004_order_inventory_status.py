from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0003_shipping_address_and_fee"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="inventory_status",
            field=models.CharField(default="PENDING", max_length=32),
        ),
    ]

