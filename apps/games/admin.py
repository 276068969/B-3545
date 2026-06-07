from django.contrib import admin
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
    list_display = ('title', 'winner', 'highlight_type', 'highlight_score', 'is_featured', 'created_at')
    list_filter = ('highlight_type', 'is_featured', 'is_comeback', 'is_domination')
    list_editable = ('is_featured',)
    search_fields = ('title', 'winner__username')


@admin.register(PlayerStats)
class PlayerStatsAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_games', 'wins', 'win_rate', 'total_score', 'avg_score', 'domination_count')
    search_fields = ('user__username', 'user__nickname')
    readonly_fields = ('last_updated',)
