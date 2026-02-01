"""Data migration to create default groups and assign permissions.

Creates two groups:
- Librarian: add/change/delete books, view loans
- Member: view books, add loans
"""
from __future__ import annotations

from django.db import migrations


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    # ContentType for our Book and Loan models
    try:
        book_ct = ContentType.objects.get(app_label="domain", model="book")
        loan_ct = ContentType.objects.get(app_label="domain", model="loan")
    except ContentType.DoesNotExist:
        return

    # Librarian: manage books and view loans
    librarian_perms = Permission.objects.filter(
        content_type=book_ct, codename__in=["add_book", "change_book", "delete_book", "view_book"]
    )
    librarian_view_loans = Permission.objects.filter(content_type=loan_ct, codename__in=["view_loan"]) 

    # Member: view books and add loans
    member_perms = Permission.objects.filter(content_type=book_ct, codename__in=["view_book"]) 
    member_add_loan = Permission.objects.filter(content_type=loan_ct, codename__in=["add_loan"]) 

    # Admin: grant all permissions on domain app models
    admin_perms = Permission.objects.filter(content_type__app_label="domain")

    librarian, _ = Group.objects.get_or_create(name="Librarian")
    librarian.permissions.add(*librarian_perms)
    librarian.permissions.add(*librarian_view_loans)

    member, _ = Group.objects.get_or_create(name="Member")
    member.permissions.add(*member_perms)
    member.permissions.add(*member_add_loan)

    admin, _ = Group.objects.get_or_create(name="Admin")
    admin.permissions.add(*admin_perms)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=["Librarian", "Member"]).delete()


class Migration(migrations.Migration):

    dependencies = [("domain", "0001_initial")]

    operations = [migrations.RunPython(create_groups, remove_groups)]
