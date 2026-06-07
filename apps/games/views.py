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

    paginator = Paginator(games, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Build query string without 'page' for use in pagination links
    params = request.GET.copy()
    params.pop('page', None)
    base_query = params.urlencode()  # e.g. "player=3&date_range=week"

    # Pick up import errors/result stored in session by import_games view
    import_errors = request.session.pop('import_errors', None)
    import_result = request.session.pop('import_result', None)

    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_count': games.count(),
        'base_query': base_query,
        'import_errors': import_errors,
        'import_result': import_result,
    }
    return render(request, 'games/list.html', context)


def game_detail(request, pk):
    game = get_object_or_404(Game, pk=pk)
    players = game.players.select_related('user').prefetch_related('patterns__tile_pattern').order_by('-score')
    highlights = game.highlights.all()
    snapshots = game.snapshots.select_related('player').order_by('round_number')

    # Prepare chart data
    import json
    score_data = {
        'players': [p.user.get_display_name() for p in players],
        'scores': [p.score for p in players],
    }

    context = {
        'game': game,
        'players': players,
        'highlights': highlights,
        'snapshots': snapshots,
        'score_data': json.dumps(score_data),
        'can_edit': request.user.is_authenticated and (
            game.creator == request.user or request.user.is_staff
        ),
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
    if fmt == 'pdf':
        return export_games_to_pdf(games)
    return export_games_to_excel(games)


@login_required
@require_POST
def collect_highlight(request, pk):
    highlight = get_object_or_404(Highlight, pk=pk)
    if request.user in highlight.collected_by.all():
        highlight.collected_by.remove(request.user)
        collected = False
    else:
        highlight.collected_by.add(request.user)
        collected = True
    return JsonResponse({'collected': collected, 'count': highlight.collected_by.count()})


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
