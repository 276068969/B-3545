from django.contrib import admin
from django.utils import timezone
from .models import TilePattern, Game, GamePlayer, GamePlayerPattern, Highlight, PlayerStats


@admin.register(TilePattern)
class TilePatternAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'fan_count', 'rarity_score', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name',)
    list_editable = ('fan_count', 'rarity_score', 'is_active')


class GamePlayerInline(admin.TabularInline):
    model = GamePlayer
    extra = 0
    fields = ('user', 'score', 'rank', 'is_winner')
    readonly_fields = ('rank',)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('pk', 'game_time', 'location', 'game_type', 'status', 'creator', 'is_supplemental', 'created_at')
    list_filter = ('status', 'game_type', 'is_supplemental')
    search_fields = ('location', 'notes', 'creator__username')
    inlines = [GamePlayerInline]
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'game_time'


@admin.register(GamePlayer)
class GamePlayerAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'score', 'rank', 'is_winner')
    list_filter = ('is_winner',)
    search_fields = ('user__username',)


@admin.register(GamePlayerPattern)
class GamePlayerPatternAdmin(admin.ModelAdmin):
    list_display = ('game_player', 'tile_pattern', 'is_self_draw', 'shooter', 'consecutive_dealer')
    list_filter = ('is_self_draw', 'tile_pattern__category')
    search_fields = ('game_player__user__username', 'tile_pattern__name')


@admin.register(Highlight)
class HighlightAdmin(admin.ModelAdmin):
    list_display = (
        'display_title', 'winner', 'highlight_type', 'highlight_score',
        'is_pinned', 'is_featured', 'featured_by', 'featured_at', 'created_at'
    )
    list_filter = ('highlight_type', 'is_featured', 'is_pinned', 'is_comeback', 'is_domination')
    list_editable = ('is_featured', 'is_pinned')
    search_fields = ('title', 'featured_title', 'winner__username', 'featured_note')
    readonly_fields = ('created_at', 'featured_at', 'featured_by')
    fieldsets = (
        ('基本信息', {
            'fields': ('game', 'winner', 'highlight_type', 'title', 'description', 'highlight_score')
        }),
        ('自动识别属性', {
            'fields': ('is_comeback', 'comeback_deficit', 'is_domination', 'domination_score'),
            'classes': ('collapse',)
        }),
        ('人工精选', {
            'fields': ('is_featured', 'is_pinned', 'featured_title', 'featured_note'),
            'description': '管理员可对高光进行精选、置顶和补充说明'
        }),
        ('系统信息', {
            'fields': ('featured_at', 'featured_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['mark_featured', 'unmark_featured', 'mark_pinned', 'unmark_pinned']

    def display_title(self, obj):
        return obj.get_display_title()
    display_title.short_description = '标题'
    display_title.admin_order_field = 'title'

    def save_model(self, request, obj, form, change):
        if 'is_featured' in form.changed_data:
            if obj.is_featured:
                obj.featured_at = timezone.now()
                obj.featured_by = request.user
            else:
                obj.featured_at = None
                obj.featured_by = None
        super().save_model(request, obj, form, change)

    def mark_featured(self, request, queryset):
        updated = queryset.update(
            is_featured=True,
            featured_at=timezone.now(),
            featured_by=request.user
        )
        self.message_user(request, f'已精选 {updated} 条高光时刻。')
    mark_featured.short_description = '设为精选'

    def unmark_featured(self, request, queryset):
        updated = queryset.update(
            is_featured=False,
            featured_at=None,
            featured_by=None
        )
        self.message_user(request, f'已取消精选 {updated} 条高光时刻。')
    unmark_featured.short_description = '取消精选'

    def mark_pinned(self, request, queryset):
        updated = queryset.update(is_pinned=True)
        self.message_user(request, f'已置顶 {updated} 条高光时刻。')
    mark_pinned.short_description = '置顶'

    def unmark_pinned(self, request, queryset):
        updated = queryset.update(is_pinned=False)
        self.message_user(request, f'已取消置顶 {updated} 条高光时刻。')
    unmark_pinned.short_description = '取消置顶'


@admin.register(PlayerStats)
class PlayerStatsAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_games', 'wins', 'win_rate', 'total_score', 'avg_score', 'domination_count')
    search_fields = ('user__username', 'user__nickname')
    readonly_fields = ('last_updated',)
