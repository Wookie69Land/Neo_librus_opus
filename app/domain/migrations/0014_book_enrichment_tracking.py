from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0013_alter_book_cover_url_and_integration_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="google_checked",
            field=models.BooleanField(
                default=False,
                db_index=True,
                verbose_name="Google Checked",
            ),
        ),
        migrations.RunSQL(
            sql="""
                UPDATE domain_book
                SET google_checked = TRUE
                WHERE google_id IS NOT NULL AND google_id <> '';
            """,
            reverse_sql="""
                UPDATE domain_book
                SET google_checked = FALSE
                WHERE google_id IS NOT NULL AND google_id <> '';
            """,
        ),
    ]