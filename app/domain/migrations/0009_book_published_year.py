from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0008_alter_sessiontoken_key_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="published_year",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Published Year"
            ),
        ),
        migrations.RemoveField(
            model_name="book",
            name="publication_date",
        ),
    ]
