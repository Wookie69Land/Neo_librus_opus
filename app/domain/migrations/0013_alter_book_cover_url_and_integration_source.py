from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0012_alter_book_isbn"),
    ]

    operations = [
        migrations.AlterField(
            model_name="book",
            name="cover_url",
            field=models.URLField(
                blank=True,
                max_length=1000,
                null=True,
                verbose_name="Cover URL",
            ),
        ),
        migrations.AlterField(
            model_name="book",
            name="integration_source",
            field=models.SmallIntegerField(
                choices=[
                    (0, "Unknown / manual"),
                    (1, "e-ISBN"),
                    (20, "Curated Polish Top 100"),
                ],
                default=0,
                verbose_name="Integration Source",
            ),
        ),
    ]