from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0007_fix_sessiontoken_fk_cascade"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sessiontoken",
            name="key",
            field=models.CharField(max_length=700, unique=True),
        ),
    ]
