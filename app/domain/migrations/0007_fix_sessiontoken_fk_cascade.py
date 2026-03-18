"""Fix the SessionToken → LibraryUser FK so it has ON DELETE CASCADE at the
database level. The Django model already declares on_delete=CASCADE but the
constraint in production may have been created without it."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("domain", "0006_alter_sessiontoken_key"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE `domain_sessiontoken`
                    DROP FOREIGN KEY `domain_sessiontoken_user_id_1f7f0302_fk_domain_libraryuser_id`;

                ALTER TABLE `domain_sessiontoken`
                    ADD CONSTRAINT `domain_sessiontoken_user_id_1f7f0302_fk_domain_libraryuser_id`
                    FOREIGN KEY (`user_id`)
                    REFERENCES `domain_libraryuser` (`id`)
                    ON DELETE CASCADE;
            """,
            reverse_sql="""
                ALTER TABLE `domain_sessiontoken`
                    DROP FOREIGN KEY `domain_sessiontoken_user_id_1f7f0302_fk_domain_libraryuser_id`;

                ALTER TABLE `domain_sessiontoken`
                    ADD CONSTRAINT `domain_sessiontoken_user_id_1f7f0302_fk_domain_libraryuser_id`
                    FOREIGN KEY (`user_id`)
                    REFERENCES `domain_libraryuser` (`id`);
            """,
        ),
    ]
