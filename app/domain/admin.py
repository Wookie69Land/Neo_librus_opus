from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.auth.admin import UserAdmin
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _

from .models import (
    Author,
    Book,
    BookAuthor,
    CyclicTaskReport,
    Library,
    LibraryAdmin,
    LibraryBook,
    LibraryUser,
    Reservation,
    Role,
    Status,
)


class LibraryAdminRoleInline(admin.TabularInline):
    model = LibraryAdmin
    extra = 0
    verbose_name = "Library Role"
    verbose_name_plural = "Library Roles"
    autocomplete_fields = ['library']
    fields = ('library', 'role', 'added_at')
    readonly_fields = ('added_at',)


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
    inlines = [LibraryAdminRoleInline]
    actions = ['deactivate_users']

    @admin.action(description=_("Deactivate selected Library Users"))
    def deactivate_users(self, request, queryset):
        if request.POST.get('post') == 'yes':
            updated = queryset.update(is_active=False)
            self.message_user(
                request,
                _("%(count)d %(verbose_name)s deactivated.")
                % {
                    'count': updated,
                    'verbose_name': self.model._meta.verbose_name
                    if updated == 1
                    else self.model._meta.verbose_name_plural,
                },
                messages.SUCCESS,
            )
            return None

        context = {
            **self.admin_site.each_context(request),
            'title': _("Deactivate selected Library Users"),
            'queryset': queryset,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'opts': self.model._meta,
            'media': self.media,
        }
        return TemplateResponse(
            request,
            'admin/deactivate_selected_confirmation.html',
            context,
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


@admin.register(CyclicTaskReport)
class CyclicTaskReportAdmin(admin.ModelAdmin):
    list_display = ('task_name', 'status', 'started_at', 'finished_at', 'duration_ms')
    list_filter = ('task_name', 'status')
    search_fields = ('task_name',)
    readonly_fields = ('task_name', 'status', 'started_at', 'finished_at', 'duration_ms', 'payload', 'created_at')
