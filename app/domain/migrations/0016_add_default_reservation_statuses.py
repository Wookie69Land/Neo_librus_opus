from django.db import migrations


DEFAULT_RESERVATION_STATUSES = [
    "pending",
    "accepted",
    "picked_up",
    "closed",
    "archived",
]


def add_default_reservation_statuses(apps, schema_editor):
    Status = apps.get_model("domain", "Status")
    for status_name in DEFAULT_RESERVATION_STATUSES:
        Status.objects.get_or_create(name=status_name)


def remove_default_reservation_statuses(apps, schema_editor):
    Status = apps.get_model("domain", "Status")
    Status.objects.filter(name__in=DEFAULT_RESERVATION_STATUSES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0015_search_indexes"),
    ]

    operations = [
        migrations.RunPython(
            add_default_reservation_statuses,
            reverse_code=remove_default_reservation_statuses,
        ),
    ]
