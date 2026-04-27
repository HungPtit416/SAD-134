from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_payment_and_shipping_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="shipping_address",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="order",
            name="shipping_method",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="order",
            name="shipping_fee",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]

