from django.db import migrations


def add_default_roles(apps, schema_editor):
    Role = apps.get_model('domain', 'Role')
    Role.objects.get_or_create(name='library admin')
    Role.objects.get_or_create(name='library manager')


def remove_default_roles(apps, schema_editor):
    Role = apps.get_model('domain', 'Role')
    Role.objects.filter(name__in=['library admin', 'library manager']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('domain', '0004_sessiontoken'),
    ]

    operations = [
        migrations.RunPython(add_default_roles, reverse_code=remove_default_roles),
    ]
