from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0017_update_reservation_statuses"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MailNotification",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("new_status", models.CharField(max_length=50, verbose_name="New Status")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("sent_at", models.DateTimeField(blank=True, null=True, verbose_name="Sent At")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mail_notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Recipient",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mail_notifications",
                        to="domain.reservation",
                        verbose_name="Reservation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Mail Notification",
                "verbose_name_plural": "Mail Notifications",
            },
        ),
        migrations.AddIndex(
            model_name="mailnotification",
            index=models.Index(fields=["sent_at"], name="domain_mailnotif_sentat_idx"),
        ),
    ]
