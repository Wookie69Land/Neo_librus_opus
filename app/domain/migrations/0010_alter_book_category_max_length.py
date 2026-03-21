from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0009_book_published_year"),
    ]

    operations = [
        migrations.AlterField(
            model_name="book",
            name="category",
            field=models.CharField(
                blank=True,
                max_length=511,
                null=True,
                verbose_name="Category",
            ),
        ),
    ]