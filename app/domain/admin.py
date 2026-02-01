from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Book, Loan

# 1. Register Custom User
# We use try/except to avoid "AlreadyRegistered" crashes during reloads
try:
    admin.site.register(User, UserAdmin)
except admin.sites.AlreadyRegistered:
    pass

# 2. Register Book
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'isbn', 'copies')
    # search_fields is REQUIRED for 'autocomplete_fields' to work in LoanAdmin
    search_fields = ('title', 'author', 'isbn')
    list_filter = ('created_at',)

# 3. Register Loan
@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    # Updated field names to match your models.py:
    # 'user' -> 'borrower'
    # 'due_date' -> 'due_at'
    list_display = ('borrower', 'book', 'borrowed_at', 'due_at', 'returned_at', 'is_active_display')
    list_filter = ('returned_at', 'due_at')
    
    # This enables the searchable dropdown for selecting Users and Books
    autocomplete_fields = ['borrower', 'book']

    # Custom column to show if the loan is currently active
    @admin.display(boolean=True, description='Active?')
    def is_active_display(self, obj):
        return obj.is_active()