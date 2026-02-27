from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Book, Reservation, Edition

# 1. Register Custom User
# We use try/except to avoid "AlreadyRegistered" crashes during reloads
try:
    admin.site.register(CustomUser, UserAdmin)
except admin.sites.AlreadyRegistered:
    pass

# 2. Register Book
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'get_isbn', 'get_available_copies')
    search_fields = ('title', 'author', 'editions__isbn')
    list_filter = ('created_at',)

    @admin.display(description='ISBN')
    def get_isbn(self, obj):
        return ', '.join(edition.isbn for edition in obj.editions.all())

    @admin.display(description='Available Copies')
    def get_available_copies(self, obj):
        return sum(edition.available_copies for edition in obj.editions.all())

# 3. Register Reservation
@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    # Updated field names to match your models.py:
    # 'user' -> 'borrower'
    # 'due_date' -> 'due_at'
    list_display = ('user', 'edition', 'created_at', 'expires_at', 'is_active_display')
    list_filter = ('expires_at',)
    
    # This enables the searchable dropdown for selecting Users and Books
    autocomplete_fields = ['user', 'edition']

    @admin.display(boolean=True, description='Active?')
    def is_active_display(self, obj):
        return obj.expires_at > timezone.now()

# Register Edition model
@admin.register(Edition)
class EditionAdmin(admin.ModelAdmin):
    list_display = ('book', 'isbn', 'year', 'publisher', 'available_copies')
    search_fields = ('isbn', 'book__title', 'publisher')
    list_filter = ('year', 'publisher')