from django.shortcuts import render
from django.db.models import Count, Sum, Avg, Max, Min, Q, F
from django.utils import timezone
from datetime import timedelta
import json

from apps.games.models import Game, GamePlayer, Highlight, PlayerStats, TilePattern
from apps.accounts.models import User


def home(request):
    """Homepage with key statistics"""
    total_games = Game.objects.filter(status='completed').count()
    total_players = User.objects.filter(game_participations__game__status='completed').distinct().count()

    # Top 5 players by win rate
    top_players = PlayerStats.objects.filter(
        total_games__gte=3
    ).select_related('user').order_by('-win_rate')[:5]

    # Recent games
    recent_games = Game.objects.filter(
        status='completed'
    ).prefetch_related('players__user').select_related('creator').order_by('-game_time')[:5]

    # Recent highlights
    recent_highlights = Highlight.objects.filter(
        is_featured=True
    ).select_related('winner', 'game').order_by('-highlight_score')[:3]

    # This month's stats
    now = timezone.now()
    this_month_games = Game.objects.filter(
        status='completed',
        game_time__year=now.year,
        game_time__month=now.month
    ).count()

    context = {
        'total_games': total_games,
        'total_players': total_players,
        'top_players': top_players,
        'recent_games': recent_games,
        'recent_highlights': recent_highlights,
        'this_month_games': this_month_games,
    }
    return render(request, 'home.html', context)


def main_leaderboard(request):
    """Main leaderboard with multiple stats"""
    sort_by = request.GET.get('sort', 'win_rate')
    order = request.GET.get('order', 'desc')
    min_games = int(request.GET.get('min_games', 1))
    date_filter = request.GET.get('date_filter', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    game_type = request.GET.get('game_type', '')
    player_filter = request.GET.get('player', '')

    sort_fields = {
        'win_rate': 'win_rate',
        'total_games': 'total_games',
        'wins': 'wins',
        'total_score': 'total_score',
        'avg_score': 'avg_score',
        'max_score': 'max_score',
        'max_consecutive_wins': 'max_consecutive_wins',
        'max_consecutive_losses': 'max_consecutive_losses',
        'domination_count': 'domination_count',
        'comeback_count': 'comeback_count',
    }

    sort_field = sort_fields.get(sort_by, 'win_rate')
    order_expr = sort_field if order == 'asc' else f'-{sort_field}'

    stats_qs = PlayerStats.objects.filter(
        total_games__gte=min_games
    ).select_related('user').order_by(order_expr, '-total_games')

    # Determine time window
    now = timezone.now()
    start = end = None
    if date_filter == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif date_filter == 'week':
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif date_filter == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif date_filter == 'custom':
        from datetime import datetime
        if date_from:
            try:
                start = timezone.make_aware(datetime.strptime(date_from, '%Y-%m-%d'))
            except ValueError:
                pass
        if date_to:
            try:
                end = timezone.make_aware(datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
            except ValueError:
                pass

    if start or game_type or player_filter:
        stats_list = build_stats_for_period(
            start=start,
            end=end or now,
            game_type=game_type or None,
            player_id=int(player_filter) if player_filter else None,
        )
        stats_list = [s for s in stats_list if s['total_games'] >= min_games]
        stats_list.sort(
            key=lambda x: (x.get(sort_by) or 0, x.get('total_games', 0)),
            reverse=(order == 'desc')
        )
    else:
        # Convert QuerySet to the same dict format used by build_stats_for_period
        stats_list = []
        for s in stats_qs:
            stats_list.append({
                'user_obj': s.user,
                'total_games': s.total_games,
                'wins': s.wins,
                'losses': s.losses,
                'win_rate': s.win_rate,
                'total_score': s.total_score,
                'avg_score': s.avg_score,
                'max_score': s.max_score,
                'min_score': s.min_score,
                'max_consecutive_wins': s.max_consecutive_wins,
                'max_consecutive_losses': s.max_consecutive_losses,
                'domination_count': s.domination_count,
                'comeback_count': s.comeback_count,
                'current_consecutive_wins': s.current_consecutive_wins,
                'current_consecutive_losses': s.current_consecutive_losses,
            })

    from apps.games.models import Game
    game_type_choices = Game.GAME_TYPE_CHOICES

    context = {
        'stats_list': stats_list,
        'sort_by': sort_by,
        'order': order,
        'min_games': min_games,
        'date_filter': date_filter,
        'date_from': date_from,
        'date_to': date_to,
        'game_type': game_type,
        'player_filter': player_filter,
        'all_users': User.objects.filter(is_active=True).order_by('username'),
        'game_type_choices': game_type_choices,
        'sort_options': [
            ('win_rate', '胜率'),
            ('total_games', '总场次'),
            ('wins', '胜场数'),
            ('total_score', '总得分'),
            ('avg_score', '场均得分'),
            ('max_score', '最高单场'),
            ('max_consecutive_wins', '最大连胜'),
            ('max_consecutive_losses', '最大连败'),
            ('domination_count', '通吃次数'),
            ('comeback_count', '逆转次数'),
        ],
    }
    return render(request, 'leaderboard/main.html', context)


def build_stats_for_period(start=None, end=None, game_type=None, player_id=None):
    """Build temporary stats for a time period with optional filters"""
    qs = GamePlayer.objects.filter(game__status='completed').select_related('user', 'game')
    if start:
        qs = qs.filter(game__game_time__gte=start)
    if end:
        qs = qs.filter(game__game_time__lte=end)
    if game_type:
        qs = qs.filter(game__game_type=game_type)
    if player_id:
        # Only include games where the specific player also participated
        game_ids = GamePlayer.objects.filter(user_id=player_id).values_list('game_id', flat=True)
        qs = qs.filter(game_id__in=game_ids)
    game_players = qs

    user_stats = {}
    for gp in game_players:
        uid = gp.user.pk
        if uid not in user_stats:
            user_stats[uid] = {
                'user__id': uid,
                'user__username': gp.user.username,
                'user__nickname': gp.user.nickname,
                'user_obj': gp.user,
                'total_games': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_score': 0,
                'avg_score': 0,
                'max_score': None,
                'min_score': None,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0,
            }
        s = user_stats[uid]
        s['total_games'] += 1
        if gp.is_winner:
            s['wins'] += 1
        else:
            s['losses'] += 1
        s['total_score'] += gp.score
        if s['max_score'] is None or gp.score > s['max_score']:
            s['max_score'] = gp.score
        if s['min_score'] is None or gp.score < s['min_score']:
            s['min_score'] = gp.score

    for uid, s in user_stats.items():
        if s['total_games'] > 0:
            s['win_rate'] = s['wins'] / s['total_games'] * 100
            s['avg_score'] = s['total_score'] / s['total_games']

    return list(user_stats.values())


def domination_board(request):
    """全场通吃榜"""
    games = Game.objects.filter(status='completed').prefetch_related(
        'players__user'
    ).order_by('-game_time')

    domination_games = []
    for game in games:
        players = list(game.players.select_related('user').all())
        if len(players) < 2:
            continue
        winners = [p for p in players if p.score > 0]
        losers = [p for p in players if p.score <= 0]
        if len(winners) == 1 and len(losers) == len(players) - 1:
            domination_games.append({
                'game': game,
                'winner': winners[0],
                'losers': losers,
                'total_loss': sum(abs(p.score) for p in losers),
            })

    # Top dominators
    from collections import Counter
    dominator_counts = Counter()
    dominator_scores = {}
    for dg in domination_games:
        uid = dg['winner'].user.pk
        dominator_counts[uid] += 1
        if uid not in dominator_scores:
            dominator_scores[uid] = {'user': dg['winner'].user, 'count': 0, 'total_score': 0, 'best_score': 0}
        dominator_scores[uid]['count'] += 1
        dominator_scores[uid]['total_score'] += dg['winner'].score
        if dg['winner'].score > dominator_scores[uid]['best_score']:
            dominator_scores[uid]['best_score'] = dg['winner'].score

    top_dominators = sorted(dominator_scores.values(), key=lambda x: x['count'], reverse=True)[:10]

    context = {
        'domination_games': domination_games[:50],
        'top_dominators': top_dominators,
        'total_dominations': len(domination_games),
    }
    return render(request, 'leaderboard/domination.html', context)


def comeback_board(request):
    """反败为胜榜"""
    comebacks = Highlight.objects.filter(
        is_comeback=True
    ).select_related('winner', 'game').prefetch_related(
        'game__players__user'
    ).order_by('-comeback_deficit')[:50]

    # Top comeback kings
    comeback_stats = {}
    for cb in Highlight.objects.filter(is_comeback=True).select_related('winner'):
        uid = cb.winner.pk
        if uid not in comeback_stats:
            comeback_stats[uid] = {
                'user': cb.winner,
                'count': 0,
                'max_deficit': 0,
                'total_deficit': 0,
            }
        comeback_stats[uid]['count'] += 1
        comeback_stats[uid]['total_deficit'] += cb.comeback_deficit
        if cb.comeback_deficit > comeback_stats[uid]['max_deficit']:
            comeback_stats[uid]['max_deficit'] = cb.comeback_deficit

    top_comeback_kings = sorted(comeback_stats.values(), key=lambda x: x['count'], reverse=True)[:10]

    # Build chart data for each comeback using GameSnapshot or reconstructed scores
    from apps.games.models import GameSnapshot
    import json as _json
    comebacks_with_charts = []
    for cb in comebacks:
        snapshots = GameSnapshot.objects.filter(game=cb.game).order_by('round_number', 'player_id')
        if snapshots.exists():
            rounds = sorted(set(s.round_number for s in snapshots))
            players_in_snap = {s.player_id: s.player.get_display_name() for s in snapshots}
            datasets = {}
            for pid, pname in players_in_snap.items():
                datasets[pid] = {'label': pname, 'data': []}
            for rnd in rounds:
                round_snaps = {s.player_id: s.cumulative_score for s in snapshots if s.round_number == rnd}
                for pid in players_in_snap:
                    datasets[pid]['data'].append(round_snaps.get(pid, None))
            chart_data = {
                'labels': [f'第{r}局' for r in rounds],
                'datasets': list(datasets.values()),
            }
        else:
            # No snapshots – show a simple 2-point chart (before/after)
            players = list(cb.game.players.select_related('user').all())
            winner_gp = next((p for p in players if p.user_id == cb.winner_id), None)
            if winner_gp:
                deficit = -(cb.comeback_deficit or 0)
                chart_data = {
                    'labels': ['逆转前', '最终'],
                    'datasets': [{'label': cb.winner.get_display_name(), 'data': [deficit, winner_gp.score]}],
                }
            else:
                chart_data = None
        comebacks_with_charts.append({
            'highlight': cb,
            'chart_json': _json.dumps(chart_data) if chart_data else None,
        })

    context = {
        'comebacks': comebacks,
        'comebacks_with_charts': comebacks_with_charts,
        'top_comeback_kings': top_comeback_kings,
    }
    return render(request, 'leaderboard/comeback.html', context)


def highlights_board(request):
    """高光时刻集锦"""
    sort_by = request.GET.get('sort', 'score')
    highlight_type = request.GET.get('type', '')

    highlights_qs = Highlight.objects.select_related('winner', 'game').prefetch_related(
        'game__players__user', 'collected_by'
    )

    if highlight_type:
        highlights_qs = highlights_qs.filter(highlight_type=highlight_type)

    if sort_by == 'time':
        highlights_qs = highlights_qs.order_by('-is_pinned', '-is_featured', '-created_at')
    elif sort_by == 'collected':
        highlights_qs = highlights_qs.annotate(
            collect_count=Count('collected_by')
        ).order_by('-is_pinned', '-is_featured', '-collect_count')
    else:
        highlights_qs = highlights_qs.order_by('-is_pinned', '-is_featured', '-highlight_score', '-created_at')

    highlights = highlights_qs[:100]

    # Collect user IDs for quick lookup
    collected_ids = set()
    if request.user.is_authenticated:
        collected_ids = set(
            Highlight.objects.filter(collected_by=request.user).values_list('id', flat=True)
        )

    # Check if user is staff for admin actions
    is_staff = request.user.is_authenticated and request.user.is_staff

    context = {
        'highlights': highlights,
        'sort_by': sort_by,
        'highlight_type': highlight_type,
        'highlight_type_choices': Highlight.HIGHLIGHT_TYPE_CHOICES,
        'collected_ids': collected_ids,
        'is_staff': is_staff,
    }
    return render(request, 'leaderboard/highlights.html', context)


def player_vs_player(request):
    """玩家对比分析"""
    player1_id = request.GET.get('player1')
    player2_id = request.GET.get('player2')
    all_users = User.objects.filter(is_active=True).order_by('username')

    comparison = None
    if player1_id and player2_id:
        try:
            p1 = User.objects.get(pk=player1_id)
            p2 = User.objects.get(pk=player2_id)
            comparison = get_vs_stats(p1, p2)
        except User.DoesNotExist:
            pass

    context = {
        'all_users': all_users,
        'player1_id': player1_id,
        'player2_id': player2_id,
        'comparison': comparison,
    }
    return render(request, 'leaderboard/vs.html', context)


def get_vs_stats(p1, p2):
    """Get head-to-head statistics between two players"""
    shared_games = Game.objects.filter(
        status='completed',
        players__user=p1
    ).filter(
        players__user=p2
    ).prefetch_related('players__user').distinct()

    total = shared_games.count()
    p1_wins = 0
    p2_wins = 0
    draws = 0
    p1_total_score = 0
    p2_total_score = 0

    game_history = []
    cumulative_p1 = 0
    cumulative_p2 = 0
    cumulative_data = []
    single_game_scores = []
    win_streak_data = []
    p1_cum_wins = 0
    p2_cum_wins = 0

    for idx, game in enumerate(shared_games.order_by('game_time'), 1):
        p1_gp = game.players.filter(user=p1).first()
        p2_gp = game.players.filter(user=p2).first()
        if p1_gp and p2_gp:
            if p1_gp.score > p2_gp.score:
                p1_wins += 1
                p1_cum_wins += 1
                result = 'p1'
            elif p2_gp.score > p1_gp.score:
                p2_wins += 1
                p2_cum_wins += 1
                result = 'p2'
            else:
                draws += 1
                result = 'draw'
            p1_total_score += p1_gp.score
            p2_total_score += p2_gp.score
            cumulative_p1 += p1_gp.score
            cumulative_p2 += p2_gp.score
            game_history.append({
                'game': game,
                'p1_score': p1_gp.score,
                'p2_score': p2_gp.score,
                'result': result,
            })
            cumulative_data.append({
                'game_num': idx,
                'label': game.game_time.strftime('%m/%d'),
                'p1_cumulative': cumulative_p1,
                'p2_cumulative': cumulative_p2,
            })
            single_game_scores.append({
                'game_num': idx,
                'label': game.game_time.strftime('%m/%d'),
                'p1_score': p1_gp.score,
                'p2_score': p2_gp.score,
                'score_diff': p1_gp.score - p2_gp.score,
            })
            win_streak_data.append({
                'game_num': idx,
                'label': game.game_time.strftime('%m/%d'),
                'p1_win_rate': (p1_cum_wins / idx * 100) if idx > 0 else 0,
                'p2_win_rate': (p2_cum_wins / idx * 100) if idx > 0 else 0,
            })

    chart_data = {
        'cumulative_labels': [d['label'] for d in cumulative_data],
        'p1_cumulative_data': [d['p1_cumulative'] for d in cumulative_data],
        'p2_cumulative_data': [d['p2_cumulative'] for d in cumulative_data],
        'score_labels': [d['label'] for d in single_game_scores],
        'p1_score_data': [d['p1_score'] for d in single_game_scores],
        'p2_score_data': [d['p2_score'] for d in single_game_scores],
        'score_diff_data': [d['score_diff'] for d in single_game_scores],
        'win_rate_labels': [d['label'] for d in win_streak_data],
        'p1_win_rate_data': [d['p1_win_rate'] for d in win_streak_data],
        'p2_win_rate_data': [d['p2_win_rate'] for d in win_streak_data],
        'win_pie_data': [p1_wins, p2_wins, draws],
    }

    return {
        'p1': p1,
        'p2': p2,
        'total': total,
        'p1_wins': p1_wins,
        'p2_wins': p2_wins,
        'draws': draws,
        'p1_avg_score': p1_total_score / total if total else 0,
        'p2_avg_score': p2_total_score / total if total else 0,
        'p1_total_score': p1_total_score,
        'p2_total_score': p2_total_score,
        'game_history': game_history[-10:],
        'chart_data_json': json.dumps(chart_data),
    }
