from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Author,
    Book,
    BookAuthor,
    Library,
    LibraryAdmin,
    LibraryBook,
    LibraryUser,
    Reservation,
    Role,
    Status,
)


@admin.register(LibraryUser)
class LibraryUserAdmin(UserAdmin):
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'is_staff', 'region',
        'updated_at'
    )
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('region',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('region',)}),
    )

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'isbn', 'publisher', 'published_year', 'last_updated')
    search_fields = ('title', 'isbn', 'publisher')
    list_filter = ('published_year', 'last_updated')
    autocomplete_fields = ['authors']

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('book', 'reader', 'library', 'status', 'start_time', 'end_time', 'updated_at')
    list_filter = ('status', 'start_time', 'library')
    autocomplete_fields = ['book', 'reader', 'librarian', 'library']

@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'added_at')

@admin.register(Library)
class LibraryModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'region', 'added_at', 'updated_at')
    search_fields = ('name', 'city')
    list_filter = ('region', 'city')

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(BookAuthor)
class BookAuthorAdmin(admin.ModelAdmin):
    list_display = ('book', 'author')
    autocomplete_fields = ['book', 'author']

@admin.register(LibraryBook)
class LibraryBookAdmin(admin.ModelAdmin):
    list_display = ('book', 'library', 'is_available', 'added_at')
    list_filter = ('library', 'is_available')
    autocomplete_fields = ['book', 'library']

@admin.register(LibraryAdmin)
class LibraryAdminAdmin(admin.ModelAdmin):
    list_display = ('user', 'library', 'role', 'added_at')
    list_filter = ('library', 'role')
    autocomplete_fields = ['user', 'library']
