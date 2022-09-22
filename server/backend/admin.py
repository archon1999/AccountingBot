from django.contrib import admin

from .models import BotUser, Reservation, Region, RegionAdmin, Template


class RegionAdminInlineAdmin(admin.TabularInline):
    model = RegionAdmin
    extra = 1


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ['id', 'chat_id', 'username', 'first_name']


@admin.register(Region)
class RegionAdmin_(admin.ModelAdmin):
    list_display = ['id', 'name', 'working_time_from', 'working_time_to',
                    'day_limit', 'period']
    inlines = [RegionAdminInlineAdmin]


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['id', 'region', 'user', 'status', 'get_datetime']
    list_filter = ['region', 'status']


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ['id', 'type', 'title']
