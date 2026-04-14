from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0014_book_enrichment_tracking"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="library",
            index=models.Index(fields=["region"], name="domain_library_region_idx"),
        ),
        migrations.AddIndex(
            model_name="author",
            index=models.Index(fields=["name"], name="domain_author_name_idx"),
        ),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["title", "id"], name="domain_book_title_id_idx"),
        ),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["integration_source"], name="domain_book_integ_idx"),
        ),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["published_year"], name="domain_book_pubyear_idx"),
        ),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["page_count"], name="domain_book_pagecnt_idx"),
        ),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["language"], name="domain_book_language_idx"),
        ),
    ]