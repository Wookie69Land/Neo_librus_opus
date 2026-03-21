import app.domain.isbn
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0011_cyclictaskreport"),
    ]

    operations = [
        migrations.AlterField(
            model_name="book",
            name="isbn",
            field=models.CharField(
                max_length=20,
                unique=True,
                validators=[app.domain.isbn.validate_isbn],
                verbose_name="ISBN",
            ),
        ),
    ]