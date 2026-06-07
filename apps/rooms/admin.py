from django.contrib import admin
from .models import Room, RoomMember


class RoomMemberInline(admin.TabularInline):
    model = RoomMember
    extra = 0
    readonly_fields = ('joined_at',)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'host', 'status', 'game_type', 'get_player_count', 'created_at')
    list_filter = ('status', 'game_type')
    search_fields = ('name', 'code', 'host__username')
    inlines = [RoomMemberInline]
    readonly_fields = ('code', 'created_at')

    def get_player_count(self, obj):
        return obj.get_player_count()
    get_player_count.short_description = '人数'


@admin.register(RoomMember)
class RoomMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'room', 'joined_at', 'is_active', 'is_ready')
    list_filter = ('is_active', 'is_ready')
