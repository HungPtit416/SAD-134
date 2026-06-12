from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_alter_productreview_user_id_int"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ProductReview",
            new_name="ProductRating",
        ),
    ]
