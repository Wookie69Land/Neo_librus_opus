from django.db import migrations

OLD_STATUSES = ["picked_up", "archived"]
NEW_STATUSES = ["expired", "rejected", "cancelled"]


def add_new_reservation_statuses(apps, schema_editor):
    Status = apps.get_model("domain", "Status")
    for name in NEW_STATUSES:
        Status.objects.get_or_create(name=name)


def remove_new_reservation_statuses(apps, schema_editor):
    Status = apps.get_model("domain", "Status")
    Status.objects.filter(name__in=NEW_STATUSES).delete()


def remove_old_reservation_statuses(apps, schema_editor):
    Status = apps.get_model("domain", "Status")
    # Only delete statuses that have no reservations referencing them
    Status.objects.filter(name__in=OLD_STATUSES, reservation__isnull=True).delete()


def restore_old_reservation_statuses(apps, schema_editor):
    Status = apps.get_model("domain", "Status")
    for name in OLD_STATUSES:
        Status.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0016_add_default_reservation_statuses"),
    ]

    operations = [
        migrations.RunPython(
            add_new_reservation_statuses,
            reverse_code=remove_new_reservation_statuses,
        ),
        migrations.RunPython(
            remove_old_reservation_statuses,
            reverse_code=restore_old_reservation_statuses,
        ),
    ]
