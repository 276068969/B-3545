from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import GamePlayer, Game, Highlight, PlayerStats


def update_player_stats(user):
    stats, _ = PlayerStats.objects.get_or_create(user=user)
    stats.recalculate()


@receiver(post_save, sender=Game)
def on_game_status_change(sender, instance, **kwargs):
    if instance.status == 'completed':
        for gp in instance.players.select_related('user').all():
            update_player_stats(gp.user)
        check_and_create_highlights(instance)


def check_and_create_highlights(game):
    """自动识别并创建高光时刻"""
    players = list(game.players.select_related('user').all())
    if not players:
        return

    # Check domination (全场通吃)
    if game.is_domination():
        winner_gp = max(players, key=lambda p: p.score)
        Highlight.objects.get_or_create(
            game=game,
            winner=winner_gp.user,
            highlight_type='domination',
            defaults={
                'title': f'{winner_gp.user.get_display_name()} 全场通吃！',
                'description': f'以 {winner_gp.score} 分独吞全场',
                'is_domination': True,
                'domination_score': winner_gp.score,
                'highlight_score': calculate_highlight_score(game, winner_gp, 'domination'),
            }
        )

    # Check big win (大胜局)
    max_gp = max(players, key=lambda p: p.score)
    if max_gp.score >= 50:
        Highlight.objects.get_or_create(
            game=game,
            winner=max_gp.user,
            highlight_type='big_win',
            defaults={
                'title': f'{max_gp.user.get_display_name()} 大胜 {max_gp.score} 分',
                'description': f'本场最高得分 {max_gp.score} 分',
                'highlight_score': calculate_highlight_score(game, max_gp, 'big_win'),
            }
        )

    # Check rare patterns
    from .models import GamePlayerPattern
    for gp in players:
        rare_patterns = gp.patterns.filter(tile_pattern__rarity_score__gte=8).select_related('tile_pattern')
        for pattern_record in rare_patterns:
            Highlight.objects.get_or_create(
                game=game,
                winner=gp.user,
                highlight_type='rare_pattern',
                defaults={
                    'title': f'{gp.user.get_display_name()} 打出 {pattern_record.tile_pattern.name}！',
                    'description': f'稀有牌型 {pattern_record.tile_pattern.name}，{pattern_record.tile_pattern.fan_count}番',
                    'highlight_score': pattern_record.tile_pattern.rarity_score * 10,
                }
            )


def calculate_highlight_score(game, winner_gp, highlight_type):
    base = winner_gp.score
    multiplier = {
        'domination': 3,
        'comeback': 4,
        'big_win': 2,
        'rare_pattern': 2,
        'other': 1,
    }.get(highlight_type, 1)
    return min(base * multiplier, 999)
