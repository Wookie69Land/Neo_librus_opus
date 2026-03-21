from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0010_alter_book_category_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="CyclicTaskReport",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("task_name", models.CharField(db_index=True, max_length=100, verbose_name="Task Name")),
                ("status", models.CharField(max_length=20, verbose_name="Status")),
                ("started_at", models.DateTimeField(verbose_name="Started At")),
                ("finished_at", models.DateTimeField(verbose_name="Finished At")),
                ("duration_ms", models.PositiveIntegerField(default=0, verbose_name="Duration (ms)")),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="Payload")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
            ],
            options={
                "verbose_name": "Cyclic Task Report",
                "verbose_name_plural": "Cyclic Task Reports",
                "ordering": ["-started_at", "-id"],
            },
        ),
    ]