from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Game, GamePlayer, TilePattern, GamePlayerPattern, Highlight, PlayerStats
from .forms import GameForm, GameEditForm, GameFilterForm
import json
from .utils import export_games_to_excel, export_games_to_pdf, get_import_template, parse_import_file, apply_game_filters
from apps.accounts.models import User


def game_list(request):
    games = Game.objects.filter(status='completed').prefetch_related(
        'players__user'
    ).select_related('creator').order_by('-game_time')

    filter_form = GameFilterForm(request.GET or None)
    games = apply_game_filters(games, filter_form)

    view_mode = request.GET.get('view_mode', 'score')
    if view_mode not in ('score', 'amount'):
        view_mode = 'score'

    paginator = Paginator(games, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    params = request.GET.copy()
    params.pop('page', None)
    base_query = params.urlencode()

    params_no_viewmode = request.GET.copy()
    params_no_viewmode.pop('page', None)
    params_no_viewmode.pop('view_mode', None)
    base_query_no_viewmode = params_no_viewmode.urlencode()

    total_amount = 0
    total_score = 0
    for game in games:
        for gp in game.players.all():
            total_score += abs(gp.score)
            total_amount += abs(gp.score * game.base_score)

    import_errors = request.session.pop('import_errors', None)
    import_result = request.session.pop('import_result', None)

    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_count': games.count(),
        'total_score': total_score,
        'total_amount': total_amount,
        'view_mode': view_mode,
        'base_query': base_query,
        'base_query_no_viewmode': base_query_no_viewmode,
        'import_errors': import_errors,
        'import_result': import_result,
    }
    return render(request, 'games/list.html', context)


def game_detail(request, pk):
    game = get_object_or_404(Game, pk=pk)
    players = game.players.select_related('user').prefetch_related('patterns__tile_pattern', 'patterns__shooter').order_by('-score')
    highlights = game.highlights.select_related('winner').all()
    snapshots = game.snapshots.select_related('player').order_by('round_number')

    # Prepare chart data
    import json
    score_data = {
        'players': [p.user.get_display_name() for p in players],
        'scores': [p.score for p in players],
    }

    # Build pattern summary for each player
    pattern_summary = []
    for gp in players:
        patterns = gp.patterns.select_related('tile_pattern', 'shooter').all()
        pattern_names = [p.tile_pattern.name for p in patterns]
        self_draw_count = sum(1 for p in patterns if p.is_self_draw)
        total_fan = sum(p.tile_pattern.fan_count for p in patterns)
        pattern_summary.append({
            'player': gp,
            'patterns': patterns,
            'pattern_names': pattern_names,
            'pattern_count': len(patterns),
            'self_draw_count': self_draw_count,
            'total_fan': total_fan,
        })

    is_staff = request.user.is_authenticated and request.user.is_staff

    context = {
        'game': game,
        'players': players,
        'highlights': highlights,
        'snapshots': snapshots,
        'score_data': json.dumps(score_data),
        'pattern_summary': pattern_summary,
        'can_edit': request.user.is_authenticated and (
            game.creator == request.user or request.user.is_staff
        ),
        'is_staff': is_staff,
    }
    return render(request, 'games/detail.html', context)


@login_required
def create_game(request):
    room_id = request.GET.get('room')
    room = None
    if room_id:
        from apps.rooms.models import Room
        try:
            room = Room.objects.get(pk=room_id)
        except Room.DoesNotExist:
            pass

    all_users = User.objects.filter(is_active=True).order_by('username')
    tile_patterns = TilePattern.objects.filter(is_active=True).order_by('category', '-rarity_score')

    if request.method == 'POST':
        form = GameForm(request.POST)
        player_ids = request.POST.getlist('player_ids')
        scores = request.POST.getlist('scores')
        pattern_ids_list = []
        for pid in player_ids:
            key = f'patterns_{pid}'
            pattern_ids_list.append(request.POST.getlist(key))

        errors = []

        if not form.is_valid():
            errors.append('表单数据有误，请检查。')
        
        if len(player_ids) < 2:
            errors.append('至少需要2名玩家。')
        
        if len(player_ids) > 4:
            errors.append('最多4名玩家。')

        if len(player_ids) != len(scores):
            errors.append('玩家数量与得分数量不匹配。')

        try:
            score_values = [int(s) for s in scores]
        except (ValueError, TypeError):
            errors.append('得分必须为整数。')
            score_values = []

        if score_values and sum(score_values) != 0:
            errors.append(f'所有玩家得分之和必须为0（当前为{sum(score_values)}）。')

        if errors:
            for err in errors:
                messages.error(request, err)
            context = {
                'form': form,
                'room': room,
                'all_users': all_users,
                'tile_patterns': tile_patterns,
                'tile_patterns_by_category': get_patterns_by_category(tile_patterns),
            }
            return render(request, 'games/create.html', context)

        with transaction.atomic():
            game = form.save(commit=False)
            game.creator = request.user
            if room:
                game.room = room
            game.status = 'completed'
            game.save()

            max_score = max(score_values)
            for i, (pid, score) in enumerate(zip(player_ids, score_values)):
                try:
                    user = User.objects.get(pk=int(pid))
                except User.DoesNotExist:
                    continue
                gp = GamePlayer.objects.create(
                    game=game,
                    user=user,
                    score=score,
                    is_winner=(score == max_score and score > 0),
                )
                # Handle patterns
                if i < len(pattern_ids_list):
                    for pattern_id in pattern_ids_list[i]:
                        try:
                            pattern = TilePattern.objects.get(pk=int(pattern_id))
                            is_self_draw = f'self_draw_{pid}_{pattern_id}' in request.POST
                            GamePlayerPattern.objects.create(
                                game_player=gp,
                                tile_pattern=pattern,
                                is_self_draw=is_self_draw,
                            )
                        except TilePattern.DoesNotExist:
                            pass

            # Assign ranks
            sorted_players = sorted(game.players.all(), key=lambda p: p.score, reverse=True)
            for rank, gp in enumerate(sorted_players, 1):
                gp.rank = rank
                gp.save()

            if room:
                room.status = 'playing'
                room.save()

        messages.success(request, '战绩录入成功！')
        return redirect('games:detail', pk=game.pk)

    form = GameForm()
    room_members = []
    if room:
        room_members = list(room.members.filter(is_active=True).select_related('user'))

    context = {
        'form': form,
        'room': room,
        'room_members': room_members,
        'all_users': all_users,
        'tile_patterns': tile_patterns,
        'tile_patterns_by_category': get_patterns_by_category(tile_patterns),
    }
    return render(request, 'games/create.html', context)


def get_patterns_by_category(patterns):
    result = {}
    for pattern in patterns:
        cat = pattern.get_category_display()
        if cat not in result:
            result[cat] = []
        result[cat].append(pattern)
    return result


@login_required
def edit_game(request, pk):
    game = get_object_or_404(Game, pk=pk)
    if game.creator != request.user and not request.user.is_staff:
        messages.error(request, '您没有权限修改此战绩。')
        return redirect('games:detail', pk=pk)

    players = game.players.select_related('user').order_by('-score')
    tile_patterns = TilePattern.objects.filter(is_active=True).order_by('category', '-rarity_score')

    if request.method == 'POST':
        form = GameEditForm(request.POST, instance=game)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                # Update player scores if provided
                for player in players:
                    score_key = f'score_{player.pk}'
                    if score_key in request.POST:
                        try:
                            new_score = int(request.POST[score_key])
                            player.score = new_score
                            player.is_winner = False
                            player.save()
                        except (ValueError, TypeError):
                            pass

                # Re-determine winners and ranks
                all_players = list(game.players.all())
                if all_players:
                    max_score = max(p.score for p in all_players)
                    sorted_players = sorted(all_players, key=lambda p: p.score, reverse=True)
                    for rank, gp in enumerate(sorted_players, 1):
                        gp.rank = rank
                        gp.is_winner = (gp.score == max_score and gp.score > 0)
                        gp.save()

                # Recalculate stats for all players
                for gp in game.players.select_related('user').all():
                    stats, _ = PlayerStats.objects.get_or_create(user=gp.user)
                    stats.recalculate()

            messages.success(request, '战绩已更新！')
            return redirect('games:detail', pk=pk)
    else:
        form = GameEditForm(instance=game)

    context = {
        'game': game,
        'form': form,
        'players': players,
        'tile_patterns': tile_patterns,
    }
    return render(request, 'games/edit.html', context)


@login_required
@require_POST
def batch_delete_games(request):
    ids = request.POST.getlist('game_ids')
    if not ids:
        messages.error(request, '请选择要删除的战绩。')
        return redirect('games:list')
    games = Game.objects.filter(pk__in=ids)
    if not request.user.is_staff:
        games = games.filter(creator=request.user)
    affected_users = list(
        GamePlayer.objects.filter(game__in=games).values_list('user_id', flat=True).distinct()
    )
    count = games.count()
    games.delete()
    for user_id in affected_users:
        try:
            user = User.objects.get(pk=user_id)
            stats, _ = PlayerStats.objects.get_or_create(user=user)
            stats.recalculate()
        except User.DoesNotExist:
            pass
    messages.success(request, f'已删除 {count} 条战绩。')
    return redirect('games:list')


@login_required
@require_POST
def delete_game(request, pk):
    game = get_object_or_404(Game, pk=pk)
    if game.creator != request.user and not request.user.is_staff:
        messages.error(request, '您没有权限删除此战绩。')
        return redirect('games:detail', pk=pk)

    affected_users = list(game.players.values_list('user_id', flat=True))
    game.delete()

    # Recalculate stats for affected users
    for user_id in affected_users:
        try:
            user = User.objects.get(pk=user_id)
            stats, _ = PlayerStats.objects.get_or_create(user=user)
            stats.recalculate()
        except User.DoesNotExist:
            pass

    messages.success(request, '战绩已删除。')
    return redirect('games:list')


@login_required
def import_games(request):
    if request.method == 'POST':
        if 'file' not in request.FILES:
            messages.error(request, '请选择要导入的文件。')
            return redirect('games:import')

        file = request.FILES['file']
        allowed = ('.xlsx', '.xls', '.csv')
        if not any(file.name.lower().endswith(ext) for ext in allowed):
            messages.error(request, '只支持 Excel（.xlsx/.xls）或 CSV（.csv）格式。')
            return redirect('games:import')

        games_data, errors = parse_import_file(file)

        if request.POST.get('preview') == '1':
            request.session['import_preview'] = [
                {
                    'game_time': gd['game_time'].isoformat(),
                    'location': gd['location'],
                    'game_type': gd['game_type'],
                    'base_score': gd['base_score'],
                    'notes': gd['notes'],
                    'players': [
                        {'username': p['user'].username, 'display_name': p['user'].get_display_name(), 'score': p['score']}
                        for p in gd['players']
                    ],
                }
                for gd in games_data
            ]
            context = {
                'preview_data': request.session['import_preview'],
                'errors': errors,
                'total': len(games_data),
                'error_count': len(errors),
            }
            return render(request, 'games/import_preview.html', context)

        # Actual import
        imported_count = 0
        with transaction.atomic():
            for gd in games_data:
                game = Game.objects.create(
                    creator=request.user,
                    game_time=gd['game_time'],
                    location=gd['location'],
                    game_type=gd['game_type'],
                    base_score=gd['base_score'],
                    notes=gd['notes'],
                    is_supplemental=True,
                    status='completed',
                )
                max_score = max(p['score'] for p in gd['players'])
                for i, p in enumerate(gd['players']):
                    GamePlayer.objects.create(
                        game=game,
                        user=p['user'],
                        score=p['score'],
                        rank=i + 1,
                        is_winner=(p['score'] == max_score and p['score'] > 0),
                    )
                imported_count += 1

        # Recalculate stats
        all_users = User.objects.all()
        for user in all_users:
            if PlayerStats.objects.filter(user=user).exists() or user.game_participations.exists():
                stats, _ = PlayerStats.objects.get_or_create(user=user)
                stats.recalculate()

        if errors:
            # Store errors in session so the list page can show them in a modal
            request.session['import_errors'] = errors[:50]  # cap at 50
            request.session['import_result'] = f'导入完成：成功 {imported_count} 条，{len(errors)} 个问题已跳过。'
        else:
            messages.success(request, f'成功导入 {imported_count} 条战绩！')
        return redirect('games:list')

    # Pass system users so template can show a helper list
    all_users = User.objects.filter(is_active=True).order_by('username')
    return render(request, 'games/import.html', {'all_users': all_users})


def download_template(request):
    return get_import_template()


def export_games(request):
    games = Game.objects.filter(status='completed').prefetch_related('players__user').order_by('-game_time')
    filter_form = GameFilterForm(request.GET or None)
    games = apply_game_filters(games, filter_form)
    fmt = request.GET.get('format', 'excel')
    view_mode = request.GET.get('view_mode', 'score')
    if view_mode not in ('score', 'amount'):
        view_mode = 'score'
    if fmt == 'pdf':
        return export_games_to_pdf(games, view_mode=view_mode)
    return export_games_to_excel(games, view_mode=view_mode)


@login_required
@require_POST
def collect_highlight(request, pk):
    from .models import HighlightCollection
    highlight = get_object_or_404(Highlight, pk=pk)
    collection = HighlightCollection.objects.filter(highlight=highlight, user=request.user).first()
    if collection:
        collection.delete()
        collected = False
    else:
        HighlightCollection.objects.create(highlight=highlight, user=request.user)
        collected = True
    return JsonResponse({'collected': collected, 'count': highlight.collected_by.count()})


@login_required
@require_POST
def toggle_highlight_featured(request, pk):
    """管理员切换高光精选状态"""
    if not request.user.is_staff:
        return JsonResponse({'error': '无权限操作'}, status=403)
    from django.utils import timezone
    highlight = get_object_or_404(Highlight, pk=pk)
    highlight.is_featured = not highlight.is_featured
    if highlight.is_featured:
        highlight.featured_at = timezone.now()
        highlight.featured_by = request.user
    else:
        highlight.featured_at = None
        highlight.featured_by = None
    highlight.save()
    return JsonResponse({
        'is_featured': highlight.is_featured,
        'featured_by': highlight.featured_by.get_display_name() if highlight.featured_by else None,
    })


@login_required
@require_POST
def toggle_highlight_pinned(request, pk):
    """管理员切换高光置顶状态"""
    if not request.user.is_staff:
        return JsonResponse({'error': '无权限操作'}, status=403)
    highlight = get_object_or_404(Highlight, pk=pk)
    highlight.is_pinned = not highlight.is_pinned
    highlight.save()
    return JsonResponse({'is_pinned': highlight.is_pinned})


@login_required
def backup_data(request):
    """Manual data backup: download all games as JSON"""
    if not request.user.is_staff:
        messages.error(request, '仅管理员可执行数据备份。')
        return redirect('games:list')

    games = Game.objects.filter(status='completed').prefetch_related('players__user').order_by('-game_time')
    backup = []
    for game in games:
        players = []
        for gp in game.players.select_related('user').all():
            players.append({
                'username': gp.user.username,
                'score': gp.score,
                'is_winner': gp.is_winner,
            })
        backup.append({
            'game_time': game.game_time.isoformat(),
            'location': game.location or '',
            'game_type': game.game_type,
            'base_score': game.base_score,
            'notes': game.notes or '',
            'is_supplemental': game.is_supplemental,
            'creator': game.creator.username if game.creator else '',
            'players': players,
        })

    payload = json.dumps({'version': '1.0', 'games': backup}, ensure_ascii=False, indent=2)
    from django.utils import timezone as tz
    filename = f'mahjong_backup_{tz.now().strftime("%Y%m%d_%H%M%S")}.json'
    response = HttpResponse(payload, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def restore_data(request):
    """Manual data restore from JSON backup"""
    if not request.user.is_staff:
        messages.error(request, '仅管理员可执行数据恢复。')
        return redirect('games:list')

    if request.method == 'POST':
        file_obj = request.FILES.get('backup_file')
        if not file_obj:
            messages.error(request, '请选择备份文件。')
            return redirect('games:restore')
        try:
            data = json.loads(file_obj.read().decode('utf-8'))
            games_data = data.get('games', [])
            if not isinstance(games_data, list):
                raise ValueError('格式错误')
        except Exception as e:
            messages.error(request, f'备份文件解析失败：{e}')
            return redirect('games:restore')

        imported = 0
        errors = []
        with transaction.atomic():
            for i, gd in enumerate(games_data, 1):
                try:
                    from datetime import datetime
                    from django.utils import timezone as tz
                    gt = datetime.fromisoformat(gd['game_time'])
                    if gt.tzinfo is None:
                        gt = tz.make_aware(gt)

                    players = []
                    total = 0
                    for pd in gd.get('players', []):
                        u = User.objects.filter(username=pd['username']).first()
                        if not u:
                            errors.append(f'第{i}条：用户 {pd["username"]} 不存在，已跳过')
                            break
                        players.append((u, pd['score'], pd.get('is_winner', pd['score'] > 0)))
                        total += pd['score']
                    else:
                        if len(players) < 2:
                            errors.append(f'第{i}条：玩家数不足，已跳过')
                            continue
                        creator = User.objects.filter(username=gd.get('creator', '')).first() or request.user
                        game = Game.objects.create(
                            game_time=gt,
                            location=gd.get('location', ''),
                            game_type=gd.get('game_type', 'mahjong_16'),
                            base_score=gd.get('base_score', 1),
                            notes=gd.get('notes', ''),
                            is_supplemental=gd.get('is_supplemental', True),
                            creator=creator,
                            status='completed',
                        )
                        for u, score, is_win in players:
                            GamePlayer.objects.create(game=game, user=u, score=score, is_winner=is_win)
                        imported += 1
                except Exception as e:
                    errors.append(f'第{i}条：导入失败 - {e}')

        # Recalculate all stats
        for stats in PlayerStats.objects.all():
            stats.recalculate()

        if imported:
            messages.success(request, f'成功恢复 {imported} 条战绩。')
        if errors:
            for err in errors[:10]:
                messages.warning(request, err)
        return redirect('games:list')

    return render(request, 'games/backup.html')


def add_snapshot(request, game_pk):
    """API endpoint to add a score snapshot during active game"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)

    game = get_object_or_404(Game, pk=game_pk, status='active')
    import json
    try:
        data = json.loads(request.body)
        from .models import GameSnapshot
        for entry in data.get('scores', []):
            user = User.objects.get(pk=entry['user_id'])
            GameSnapshot.objects.create(
                game=game,
                player=user,
                round_number=data.get('round', 1),
                cumulative_score=entry['score'],
            )
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def pattern_stats(request):
    """牌型命中统计查询接口

    支持按时间范围、牌型分类、番数区间和玩家维度筛选，
    返回命中次数、命中人数、最近出现时间与最高得分关联。

    Query Parameters:
        - date_from: 开始日期 (YYYY-MM-DD)
        - date_to: 结束日期 (YYYY-MM-DD)
        - category: 牌型分类 (special/color/honor/basic/combo/custom)
        - min_fan: 最小番数
        - max_fan: 最大番数
        - player_id: 玩家ID（限定统计范围）
        - group_by: 分组维度 (pattern/category/player)，默认 pattern
        - sort_by: 排序字段 (hit_count/player_count/fan_count/last_occurrence/highest_score)
        - order: 排序方向 (asc/desc)，默认 desc
        - limit: 返回条数限制，默认 50
    """
    from django.db.models import Count, Max, Min, Sum, Q
    from django.utils import timezone
    from datetime import datetime, timedelta

    date_from_str = request.GET.get('date_from', '')
    date_to_str = request.GET.get('date_to', '')
    category = request.GET.get('category', '')
    min_fan_str = request.GET.get('min_fan', '')
    max_fan_str = request.GET.get('max_fan', '')
    player_id_str = request.GET.get('player_id', '')
    group_by = request.GET.get('group_by', 'pattern')
    sort_by = request.GET.get('sort_by', 'hit_count')
    order = request.GET.get('order', 'desc')
    limit_str = request.GET.get('limit', '50')

    errors = []

    try:
        limit = max(1, min(int(limit_str), 200))
    except (ValueError, TypeError):
        limit = 50
        errors.append('limit 参数格式有误，已使用默认值 50')

    qs = GamePlayerPattern.objects.select_related(
        'tile_pattern', 'game_player', 'game_player__game', 'game_player__user'
    ).filter(
        game_player__game__status='completed'
    )

    if date_from_str:
        try:
            date_from = timezone.make_aware(datetime.strptime(date_from_str, '%Y-%m-%d'))
            qs = qs.filter(game_player__game__game_time__gte=date_from)
        except ValueError:
            errors.append('date_from 格式有误，应为 YYYY-MM-DD，已忽略')

    if date_to_str:
        try:
            date_to = timezone.make_aware(
                datetime.strptime(date_to_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            )
            qs = qs.filter(game_player__game__game_time__lte=date_to)
        except ValueError:
            errors.append('date_to 格式有误，应为 YYYY-MM-DD，已忽略')

    if category:
        valid_categories = [c[0] for c in TilePattern.CATEGORY_CHOICES]
        if category in valid_categories:
            qs = qs.filter(tile_pattern__category=category)
        else:
            errors.append(f'category 参数无效，有效值为 {", ".join(valid_categories)}，已忽略')

    min_fan = None
    if min_fan_str:
        try:
            min_fan = int(min_fan_str)
            if min_fan < 1:
                errors.append('min_fan 不能小于 1，已忽略')
                min_fan = None
            else:
                qs = qs.filter(tile_pattern__fan_count__gte=min_fan)
        except (ValueError, TypeError):
            errors.append('min_fan 格式有误，应为正整数，已忽略')

    max_fan = None
    if max_fan_str:
        try:
            max_fan = int(max_fan_str)
            if max_fan < 1:
                errors.append('max_fan 不能小于 1，已忽略')
                max_fan = None
            elif min_fan is not None and max_fan < min_fan:
                errors.append('max_fan 不能小于 min_fan，已忽略')
                max_fan = None
            else:
                qs = qs.filter(tile_pattern__fan_count__lte=max_fan)
        except (ValueError, TypeError):
            errors.append('max_fan 格式有误，应为正整数，已忽略')

    player_id = None
    if player_id_str:
        try:
            player_id = int(player_id_str)
            if player_id < 1:
                errors.append('player_id 不能小于 1，已忽略')
                player_id = None
            else:
                if not User.objects.filter(pk=player_id).exists():
                    errors.append(f'player_id={player_id} 玩家不存在，已忽略')
                    player_id = None
                else:
                    qs = qs.filter(game_player__user_id=player_id)
        except (ValueError, TypeError):
            errors.append('player_id 格式有误，应为正整数，已忽略')

    if group_by not in ('pattern', 'category', 'player'):
        return JsonResponse({'error': 'Invalid group_by value', 'errors': errors}, status=400)

    if group_by == 'pattern':
        stats = _get_pattern_grouped_stats(qs, sort_by, order, limit)
    elif group_by == 'category':
        stats = _get_category_grouped_stats(qs, sort_by, order, limit)
    else:
        stats = _get_player_grouped_stats(qs, sort_by, order, limit)

    return JsonResponse({
        'group_by': group_by,
        'stats': stats,
        'total': len(stats),
        'filters': {
            'date_from': date_from_str or None,
            'date_to': date_to_str or None,
            'category': category or None,
            'min_fan': min_fan,
            'max_fan': max_fan,
            'player_id': player_id,
        },
        'warnings': errors if errors else [],
    })


def _get_pattern_grouped_stats(qs, sort_by, order, limit):
    """按牌型分组统计"""
    from django.db.models import Count, Max, Min, Sum

    agg = qs.values(
        'tile_pattern_id',
        'tile_pattern__name',
        'tile_pattern__category',
        'tile_pattern__fan_count',
        'tile_pattern__rarity_score',
    ).annotate(
        hit_count=Count('id'),
        player_count=Count('game_player__user_id', distinct=True),
        last_occurrence=Max('game_player__game__game_time'),
        highest_score=Max('game_player__score'),
    )

    sort_map = {
        'hit_count': 'hit_count',
        'player_count': 'player_count',
        'fan_count': 'tile_pattern__fan_count',
        'last_occurrence': 'last_occurrence',
        'highest_score': 'highest_score',
    }
    sort_field = sort_map.get(sort_by, 'hit_count')
    order_expr = sort_field if order == 'asc' else f'-{sort_field}'
    agg = agg.order_by(order_expr, '-hit_count')

    pattern_ids = [item['tile_pattern_id'] for item in agg[:limit]]
    highest_score_map = {}
    if pattern_ids:
        for pid in pattern_ids:
            top_pattern = qs.filter(
                tile_pattern_id=pid
            ).select_related('game_player__user').order_by(
                '-game_player__score', '-game_player__game__game_time'
            ).first()
            if top_pattern:
                highest_score_map[pid] = {
                    'player_id': top_pattern.game_player.user_id,
                    'player_name': top_pattern.game_player.user.get_display_name(),
                    'game_id': top_pattern.game_player.game_id,
                    'score': top_pattern.game_player.score,
                }

    result = []
    for item in agg[:limit]:
        pid = item['tile_pattern_id']
        highest_info = highest_score_map.get(pid, {})
        result.append({
            'pattern_id': item['tile_pattern_id'],
            'pattern_name': item['tile_pattern__name'],
            'category': item['tile_pattern__category'],
            'category_name': dict(TilePattern.CATEGORY_CHOICES).get(item['tile_pattern__category'], ''),
            'fan_count': item['tile_pattern__fan_count'],
            'rarity_score': item['tile_pattern__rarity_score'],
            'hit_count': item['hit_count'],
            'player_count': item['player_count'],
            'last_occurrence': item['last_occurrence'].isoformat() if item['last_occurrence'] else None,
            'highest_score': item['highest_score'] or 0,
            'highest_score_player': highest_info.get('player_name', ''),
            'highest_score_player_id': highest_info.get('player_id'),
            'highest_score_game_id': highest_info.get('game_id'),
        })
    return result


def _get_category_grouped_stats(qs, sort_by, order, limit):
    """按牌型分类分组统计"""
    from django.db.models import Count, Max, Min, Sum

    agg = qs.values(
        'tile_pattern__category',
    ).annotate(
        hit_count=Count('id'),
        player_count=Count('game_player__user_id', distinct=True),
        pattern_count=Count('tile_pattern_id', distinct=True),
        last_occurrence=Max('game_player__game__game_time'),
        highest_score=Max('game_player__score'),
        total_fan=Sum('tile_pattern__fan_count'),
    )

    sort_map = {
        'hit_count': 'hit_count',
        'player_count': 'player_count',
        'pattern_count': 'pattern_count',
        'last_occurrence': 'last_occurrence',
        'highest_score': 'highest_score',
        'total_fan': 'total_fan',
    }
    sort_field = sort_map.get(sort_by, 'hit_count')
    order_expr = sort_field if order == 'asc' else f'-{sort_field}'
    agg = agg.order_by(order_expr)

    categories = [item['tile_pattern__category'] for item in agg]
    highest_score_map = {}
    if categories:
        for cat in categories:
            top_pattern = qs.filter(
                tile_pattern__category=cat
            ).select_related(
                'game_player__user', 'tile_pattern'
            ).order_by(
                '-game_player__score', '-game_player__game__game_time'
            ).first()
            if top_pattern:
                highest_score_map[cat] = {
                    'player_id': top_pattern.game_player.user_id,
                    'player_name': top_pattern.game_player.user.get_display_name(),
                    'game_id': top_pattern.game_player.game_id,
                    'pattern_id': top_pattern.tile_pattern_id,
                    'pattern_name': top_pattern.tile_pattern.name,
                    'score': top_pattern.game_player.score,
                }

    result = []
    for item in agg:
        cat = item['tile_pattern__category']
        highest_info = highest_score_map.get(cat, {})
        result.append({
            'category': cat,
            'category_name': dict(TilePattern.CATEGORY_CHOICES).get(cat, ''),
            'hit_count': item['hit_count'],
            'player_count': item['player_count'],
            'pattern_count': item['pattern_count'],
            'last_occurrence': item['last_occurrence'].isoformat() if item['last_occurrence'] else None,
            'highest_score': item['highest_score'] or 0,
            'highest_score_player': highest_info.get('player_name', ''),
            'highest_score_player_id': highest_info.get('player_id'),
            'highest_score_pattern': highest_info.get('pattern_name', ''),
            'highest_score_pattern_id': highest_info.get('pattern_id'),
            'highest_score_game_id': highest_info.get('game_id'),
            'total_fan': item['total_fan'] or 0,
        })
    return result


def _get_player_grouped_stats(qs, sort_by, order, limit):
    """按玩家分组统计"""
    from django.db.models import Count, Max, Min, Sum

    agg = qs.values(
        'game_player__user_id',
        'game_player__user__username',
        'game_player__user__nickname',
    ).annotate(
        hit_count=Count('id'),
        pattern_count=Count('tile_pattern_id', distinct=True),
        category_count=Count('tile_pattern__category', distinct=True),
        last_occurrence=Max('game_player__game__game_time'),
        highest_score=Max('game_player__score'),
        total_fan=Sum('tile_pattern__fan_count'),
    )

    sort_map = {
        'hit_count': 'hit_count',
        'pattern_count': 'pattern_count',
        'last_occurrence': 'last_occurrence',
        'highest_score': 'highest_score',
        'total_fan': 'total_fan',
    }
    sort_field = sort_map.get(sort_by, 'hit_count')
    order_expr = sort_field if order == 'asc' else f'-{sort_field}'
    agg = agg.order_by(order_expr)

    player_ids = [item['game_player__user_id'] for item in agg[:limit]]

    favorite_map = {}
    highest_score_map = {}
    if player_ids:
        for uid in player_ids:
            fav = qs.filter(
                game_player__user_id=uid
            ).values('tile_pattern__name').annotate(
                cnt=Count('id')
            ).order_by('-cnt').first()
            if fav:
                favorite_map[uid] = fav['tile_pattern__name']

            top_pattern = qs.filter(
                game_player__user_id=uid
            ).select_related(
                'tile_pattern'
            ).order_by(
                '-game_player__score', '-game_player__game__game_time'
            ).first()
            if top_pattern:
                highest_score_map[uid] = {
                    'pattern_id': top_pattern.tile_pattern_id,
                    'pattern_name': top_pattern.tile_pattern.name,
                    'pattern_category': top_pattern.tile_pattern.category,
                    'game_id': top_pattern.game_player.game_id,
                    'score': top_pattern.game_player.score,
                }

    result = []
    for item in agg[:limit]:
        uid = item['game_player__user_id']
        display_name = item['game_player__user__nickname'] or item['game_player__user__username']
        highest_info = highest_score_map.get(uid, {})
        result.append({
            'player_id': uid,
            'player_name': display_name,
            'hit_count': item['hit_count'],
            'pattern_count': item['pattern_count'],
            'category_count': item['category_count'],
            'last_occurrence': item['last_occurrence'].isoformat() if item['last_occurrence'] else None,
            'highest_score': item['highest_score'] or 0,
            'highest_score_pattern': highest_info.get('pattern_name', ''),
            'highest_score_pattern_id': highest_info.get('pattern_id'),
            'highest_score_pattern_category': highest_info.get('pattern_category', ''),
            'highest_score_game_id': highest_info.get('game_id'),
            'total_fan': item['total_fan'] or 0,
            'favorite_pattern': favorite_map.get(uid, ''),
        })
    return result


RARITY_DESCRIPTIONS = {
    1: '极其常见',
    2: '非常常见',
    3: '比较常见',
    4: '普通',
    5: '略稀有',
    6: '较稀有',
    7: '稀有',
    8: '非常稀有',
    9: '极其稀有',
    10: '传说级',
}


def _get_rarity_description(score):
    return RARITY_DESCRIPTIONS.get(score, '普通')


def _get_pattern_dict(pattern, hit_count=None, last_occurrence=None, highlight_count=None):
    from django.db.models import Count, Max

    if hit_count is None:
        if hasattr(pattern, 'hit_count'):
            hit_count = pattern.hit_count
        else:
            hit_count = pattern.game_occurrences.filter(
                game_player__game__status='completed'
            ).count()

    if last_occurrence is None:
        if hasattr(pattern, 'last_occurrence'):
            last_occurrence = pattern.last_occurrence
        else:
            last_occurrence = pattern.game_occurrences.filter(
                game_player__game__status='completed'
            ).aggregate(
                last=Max('game_player__game__game_time')
            )['last']

    if highlight_count is None:
        if hasattr(pattern, 'highlight_count'):
            highlight_count = pattern.highlight_count
        else:
            highlight_count = Highlight.objects.filter(
                game__players__patterns__tile_pattern=pattern,
                highlight_type='rare_pattern',
            ).distinct().count()

    return {
        'id': pattern.pk,
        'name': pattern.name,
        'category': pattern.category,
        'category_name': pattern.get_category_display(),
        'fan_count': pattern.fan_count,
        'description': pattern.description,
        'rarity_score': pattern.rarity_score,
        'rarity_description': _get_rarity_description(pattern.rarity_score),
        'hit_count': hit_count or 0,
        'last_occurrence': last_occurrence.isoformat() if last_occurrence else None,
        'highlight_count': highlight_count or 0,
        'is_active': pattern.is_active,
    }


def tile_pattern_list(request):
    """牌型百科列表查询接口

    支持按名称模糊检索、按类别浏览，返回牌型分类、番数、稀有度说明、
    最近被打出时间和关联高光数量，适用于「牌型图鉴」、「录入页提示」等场景。

    Query Parameters:
        - search: 名称模糊搜索关键词
        - category: 牌型分类 (special/color/honor/basic/combo/custom)
        - min_fan: 最小番数
        - max_fan: 最大番数
        - min_rarity: 最小稀有度 (1-10)
        - max_rarity: 最大稀有度 (1-10)
        - is_active: 是否只返回启用的牌型 (1/0)，默认 1
        - sort_by: 排序字段 (name/fan_count/rarity_score/hit_count/last_occurrence/highlight_count)，默认 rarity_score
        - order: 排序方向 (asc/desc)，默认 desc
        - page: 页码，默认 1
        - page_size: 每页数量，默认 20，最大 100
    """
    from django.db.models import Count, Max, Q

    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    min_fan_str = request.GET.get('min_fan', '')
    max_fan_str = request.GET.get('max_fan', '')
    min_rarity_str = request.GET.get('min_rarity', '')
    max_rarity_str = request.GET.get('max_rarity', '')
    is_active_str = request.GET.get('is_active', '1')
    sort_by = request.GET.get('sort_by', 'rarity_score')
    order = request.GET.get('order', 'desc')
    page_str = request.GET.get('page', '1')
    page_size_str = request.GET.get('page_size', '20')

    warnings = []

    qs = TilePattern.objects.all()

    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))

    if category:
        valid_categories = [c[0] for c in TilePattern.CATEGORY_CHOICES]
        if category in valid_categories:
            qs = qs.filter(category=category)
        else:
            warnings.append(f'category 参数无效，有效值为 {", ".join(valid_categories)}，已忽略')

    if min_fan_str:
        try:
            min_fan = int(min_fan_str)
            if min_fan >= 1:
                qs = qs.filter(fan_count__gte=min_fan)
            else:
                warnings.append('min_fan 不能小于 1，已忽略')
        except (ValueError, TypeError):
            warnings.append('min_fan 格式有误，应为正整数，已忽略')

    if max_fan_str:
        try:
            max_fan = int(max_fan_str)
            if max_fan >= 1:
                qs = qs.filter(fan_count__lte=max_fan)
            else:
                warnings.append('max_fan 不能小于 1，已忽略')
        except (ValueError, TypeError):
            warnings.append('max_fan 格式有误，应为正整数，已忽略')

    if min_rarity_str:
        try:
            min_rarity = int(min_rarity_str)
            if 1 <= min_rarity <= 10:
                qs = qs.filter(rarity_score__gte=min_rarity)
            else:
                warnings.append('min_rarity 应在 1-10 之间，已忽略')
        except (ValueError, TypeError):
            warnings.append('min_rarity 格式有误，应为 1-10 的整数，已忽略')

    if max_rarity_str:
        try:
            max_rarity = int(max_rarity_str)
            if 1 <= max_rarity <= 10:
                qs = qs.filter(rarity_score__lte=max_rarity)
            else:
                warnings.append('max_rarity 应在 1-10 之间，已忽略')
        except (ValueError, TypeError):
            warnings.append('max_rarity 格式有误，应为 1-10 的整数，已忽略')

    if is_active_str == '1':
        qs = qs.filter(is_active=True)
    elif is_active_str == '0':
        qs = qs.filter(is_active=False)

    try:
        page_size = max(1, min(int(page_size_str), 100))
    except (ValueError, TypeError):
        page_size = 20
        warnings.append('page_size 参数格式有误，已使用默认值 20')

    try:
        page = max(1, int(page_str))
    except (ValueError, TypeError):
        page = 1
        warnings.append('page 参数格式有误，已使用默认值 1')

    valid_sort_fields = [
        'name', 'fan_count', 'rarity_score', 'hit_count',
        'last_occurrence', 'highlight_count',
    ]
    if sort_by not in valid_sort_fields:
        sort_by = 'rarity_score'
        warnings.append(f'sort_by 参数无效，有效值为 {", ".join(valid_sort_fields)}，已使用默认值 rarity_score')

    if order not in ('asc', 'desc'):
        order = 'desc'
        warnings.append('order 参数无效，有效值为 asc/desc，已使用默认值 desc')

    qs = qs.annotate(
        hit_count=Count(
            'game_occurrences',
            filter=Q(game_occurrences__game_player__game__status='completed'),
            distinct=True
        ),
        last_occurrence=Max(
            'game_occurrences__game_player__game__game_time',
            filter=Q(game_occurrences__game_player__game__status='completed')
        ),
        highlight_count=Count(
            'game_occurrences__game_player__game__highlights',
            filter=Q(
                game_occurrences__game_player__game__status='completed',
                game_occurrences__game_player__game__highlights__highlight_type='rare_pattern',
            ),
            distinct=True
        ),
    )

    order_prefix = '' if order == 'asc' else '-'
    qs = qs.order_by(f'{order_prefix}{sort_by}', 'name')

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    results = []
    for pattern in page_obj:
        results.append(_get_pattern_dict(pattern))

    return JsonResponse({
        'results': results,
        'total': paginator.count,
        'page': page_obj.number,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'has_next': page_obj.has_next(),
        'has_previous': page_obj.has_previous(),
        'filters': {
            'search': search or None,
            'category': category or None,
            'min_fan': int(min_fan_str) if min_fan_str and min_fan_str.isdigit() else None,
            'max_fan': int(max_fan_str) if max_fan_str and max_fan_str.isdigit() else None,
            'min_rarity': int(min_rarity_str) if min_rarity_str and min_rarity_str.isdigit() else None,
            'max_rarity': int(max_rarity_str) if max_rarity_str and max_rarity_str.isdigit() else None,
            'is_active': is_active_str == '1',
        },
        'sort': {
            'sort_by': sort_by,
            'order': order,
        },
        'warnings': warnings if warnings else [],
    })


def tile_pattern_detail(request, pk):
    """牌型百科详情查询接口

    返回指定牌型的详细信息，包括牌型分类、番数、稀有度说明、
    最近被打出时间和关联高光数量。

    Path Parameters:
        - pk: 牌型 ID
    """
    pattern = get_object_or_404(TilePattern, pk=pk)
    return JsonResponse(_get_pattern_dict(pattern))


def tile_pattern_categories(request):
    """牌型分类聚合接口

    返回按牌型分类聚合的统计信息，包含各类别的牌型数量、
    平均番数、平均稀有度等，适用于「牌型图鉴」分类浏览场景。
    """
    from django.db.models import Count, Avg, Max, Min

    categories = TilePattern.objects.filter(is_active=True).values(
        'category'
    ).annotate(
        pattern_count=Count('id'),
        avg_fan=Avg('fan_count'),
        avg_rarity=Avg('rarity_score'),
        max_fan=Max('fan_count'),
        min_fan=Min('fan_count'),
        max_rarity=Max('rarity_score'),
        min_rarity=Min('rarity_score'),
    ).order_by('category')

    result = []
    for cat in categories:
        cat_key = cat['category']
        cat_name = dict(TilePattern.CATEGORY_CHOICES).get(cat_key, cat_key)

        hit_count = GamePlayerPattern.objects.filter(
            tile_pattern__category=cat_key,
            game_player__game__status='completed',
        ).count()

        highlight_count = Highlight.objects.filter(
            game__players__patterns__tile_pattern__category=cat_key,
            highlight_type='rare_pattern',
        ).distinct().count()

        result.append({
            'category': cat_key,
            'category_name': cat_name,
            'pattern_count': cat['pattern_count'],
            'avg_fan': round(cat['avg_fan'] or 0, 1),
            'avg_rarity': round(cat['avg_rarity'] or 0, 1),
            'max_fan': cat['max_fan'] or 0,
            'min_fan': cat['min_fan'] or 0,
            'max_rarity': cat['max_rarity'] or 0,
            'min_rarity': cat['min_rarity'] or 0,
            'hit_count': hit_count,
            'highlight_count': highlight_count,
        })

    return JsonResponse({
        'categories': result,
        'total_categories': len(result),
        'total_patterns': sum(c['pattern_count'] for c in result),
    })
