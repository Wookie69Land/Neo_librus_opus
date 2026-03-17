from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('domain', '0005_add_default_roles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sessiontoken',
            name='key',
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
