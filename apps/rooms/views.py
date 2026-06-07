from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from .models import Room, RoomMember
from apps.games.models import Game, GamePlayer, GameSnapshot
from apps.accounts.models import User
import json


def room_list(request):
    rooms = Room.objects.filter(status__in=['waiting', 'playing']).select_related('host').prefetch_related('members')
    context = {'rooms': rooms}
    return render(request, 'rooms/list.html', context)


@login_required
def create_room(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        game_type = request.POST.get('game_type', 'mahjong_16')
        max_players = int(request.POST.get('max_players', 4))
        base_score = int(request.POST.get('base_score', 1))
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, '请输入房间名称。')
            return render(request, 'rooms/create.html', {
                'game_type_choices': Room.GAME_TYPE_CHOICES
            })

        with transaction.atomic():
            room = Room.objects.create(
                name=name,
                host=request.user,
                game_type=game_type,
                max_players=max_players,
                base_score=base_score,
                description=description,
            )
            RoomMember.objects.create(room=room, user=request.user, is_active=True)

        messages.success(request, f'房间 "{name}" 创建成功！房间码：{room.code}')
        return redirect('rooms:detail', pk=room.pk)

    return render(request, 'rooms/create.html', {
        'game_type_choices': Room.GAME_TYPE_CHOICES
    })


def room_detail(request, pk):
    room = get_object_or_404(Room, pk=pk)
    members = room.members.filter(is_active=True).select_related('user')
    games = Game.objects.filter(room=room).order_by('-game_time')[:10]
    user_in_room = False
    is_host = False
    if request.user.is_authenticated:
        user_in_room = room.members.filter(user=request.user, is_active=True).exists()
        is_host = room.host == request.user
    
    scoreboard = room.get_scoreboard_data()
    
    context = {
        'room': room,
        'members': members,
        'games': games,
        'user_in_room': user_in_room,
        'is_host': is_host,
        'scoreboard': scoreboard,
    }
    return render(request, 'rooms/detail.html', context)


@login_required
@require_POST
def join_room(request, pk):
    room = get_object_or_404(Room, pk=pk)
    can_join, msg = room.can_join(request.user)
    if not can_join:
        messages.error(request, msg)
        return redirect('rooms:detail', pk=pk)

    RoomMember.objects.get_or_create(room=room, user=request.user, defaults={'is_active': True})
    messages.success(request, f'成功加入房间 "{room.name}"！')
    return redirect('rooms:detail', pk=pk)


@login_required
def join_by_code(request):
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        try:
            room = Room.objects.get(code=code)
            can_join, msg = room.can_join(request.user)
            if not can_join:
                if msg == '您已在房间中':
                    return redirect('rooms:detail', pk=room.pk)
                messages.error(request, msg)
                return redirect('rooms:list')
            RoomMember.objects.get_or_create(room=room, user=request.user, defaults={'is_active': True})
            messages.success(request, f'成功加入房间 "{room.name}"！')
            return redirect('rooms:detail', pk=room.pk)
        except Room.DoesNotExist:
            messages.error(request, '房间码不存在，请检查后重试。')
    return redirect('rooms:list')


@login_required
@require_POST
def leave_room(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if room.host == request.user:
        messages.warning(request, '房主无法直接退出房间，请先转让房主或关闭房间。')
        return redirect('rooms:detail', pk=pk)
    RoomMember.objects.filter(room=room, user=request.user).update(is_active=False)
    messages.info(request, f'已退出房间 "{room.name}"。')
    return redirect('rooms:list')


@login_required
@require_POST
def close_room(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if room.host != request.user and not request.user.is_staff:
        messages.error(request, '只有房主可以关闭房间。')
        return redirect('rooms:detail', pk=pk)
    room.status = 'finished'
    room.save()
    messages.info(request, f'房间 "{room.name}" 已关闭。')
    return redirect('rooms:list')


@login_required
def start_game(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if room.host != request.user:
        messages.error(request, '只有房主可以开始游戏。')
        return redirect('rooms:detail', pk=pk)
    if room.get_player_count() < 2:
        messages.error(request, '至少需要2名玩家才能开始游戏。')
        return redirect('rooms:detail', pk=pk)

    return redirect(f'/games/create/?room={pk}')


@login_required
@require_POST
def start_scoreboard(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if room.host != request.user:
        return JsonResponse({'error': '只有房主可以开启记分台'}, status=403)
    
    active_game = room.get_active_game()
    if active_game:
        return JsonResponse({'error': '当前已有进行中的游戏'}, status=400)
    
    player_count = room.get_player_count()
    if player_count < 2:
        return JsonResponse({'error': '至少需要2名玩家才能开始游戏'}, status=400)
    
    with transaction.atomic():
        game = Game.objects.create(
            room=room,
            creator=request.user,
            game_time=timezone.now(),
            game_type=room.game_type,
            base_score=room.base_score,
            status='active',
            notes='房间实时记分台游戏',
        )
        
        members = room.members.filter(is_active=True).select_related('user')
        for member in members:
            GamePlayer.objects.create(
                game=game,
                user=member.user,
                score=0,
                is_winner=False,
            )
        
        room.status = 'playing'
        room.save()
    
    return JsonResponse({
        'status': 'ok',
        'game_id': game.pk,
    })


@login_required
@require_POST
def record_round(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if room.host != request.user:
        return JsonResponse({'error': '只有房主可以录入分数'}, status=403)
    
    game = room.get_active_game()
    if not game:
        return JsonResponse({'error': '当前没有进行中的游戏'}, status=400)
    
    try:
        data = json.loads(request.body)
        scores = data.get('scores', {})
        
        if not scores:
            return JsonResponse({'error': '请输入各玩家分数'}, status=400)
        
        game_players = list(game.players.all())
        valid_player_ids = {gp.user_id for gp in game_players}
        
        parsed_scores = {}
        for user_id_str, score_str in scores.items():
            try:
                user_id = int(user_id_str)
                score = int(score_str)
            except (ValueError, TypeError):
                return JsonResponse({'error': '分数必须为整数'}, status=400)
            
            if user_id not in valid_player_ids:
                return JsonResponse({'error': f'无效的玩家ID: {user_id}'}, status=400)
            
            parsed_scores[user_id] = score
        
        if len(parsed_scores) != len(valid_player_ids):
            return JsonResponse({'error': '请输入所有玩家的分数'}, status=400)
        
        total = sum(parsed_scores.values())
        if total != 0:
            return JsonResponse({'error': f'所有玩家得分之和必须为0（当前为{total}）'}, status=400)
        
        current_round = room.get_current_round()
        next_round = current_round + 1
        
        with transaction.atomic():
            for user_id, score in parsed_scores.items():
                GameSnapshot.objects.create(
                    game=game,
                    player_id=user_id,
                    round_number=next_round,
                    cumulative_score=score,
                )
        
        scoreboard = room.get_scoreboard_data()
        return JsonResponse({
            'status': 'ok',
            'round': next_round,
            'scoreboard': serialize_scoreboard(scoreboard),
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON数据'}, status=400)


@login_required
def scoreboard_api(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if not room.members.filter(user=request.user, is_active=True).exists():
        return JsonResponse({'error': '您不在此房间中'}, status=403)
    
    scoreboard = room.get_scoreboard_data()
    return JsonResponse({
        'status': 'ok',
        'scoreboard': serialize_scoreboard(scoreboard),
    })


@login_required
@require_POST
def end_scoreboard(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if room.host != request.user:
        return JsonResponse({'error': '只有房主可以结束游戏'}, status=403)
    
    game = room.get_active_game()
    if not game:
        return JsonResponse({'error': '当前没有进行中的游戏'}, status=400)
    
    with transaction.atomic():
        latest_snapshots = room.get_latest_snapshots()
        if latest_snapshots:
            for snap in latest_snapshots:
                gp = game.players.filter(user_id=snap.player_id).first()
                if gp:
                    gp.score = snap.cumulative_score
                    gp.save()
            
            sorted_players = sorted(game.players.all(), key=lambda p: p.score, reverse=True)
            max_score = sorted_players[0].score if sorted_players else 0
            for rank, gp in enumerate(sorted_players, 1):
                gp.rank = rank
                gp.is_winner = (gp.score == max_score and gp.score > 0)
                gp.save()
        
        game.status = 'completed'
        game.save()
        
        remaining_active = room.games.filter(status='active').count()
        if remaining_active == 0:
            room.status = 'waiting'
            room.save()
    
    return JsonResponse({
        'status': 'ok',
        'game_id': game.pk,
    })


def serialize_scoreboard(scoreboard):
    if not scoreboard['has_active_game']:
        return {
            'has_active_game': False,
            'current_round': 0,
            'players': [],
            'leader': None,
            'lead_gap': 0,
            'comeback_candidates': [],
            'round_history': [],
        }
    
    return {
        'has_active_game': True,
        'current_round': scoreboard['current_round'],
        'players': [
            {
                'player_id': p['player'].pk,
                'player_name': p['player'].get_display_name(),
                'player_avatar': p['player'].get_avatar_url,
                'score': p['score'],
                'rank': p['rank'],
            }
            for p in scoreboard['players']
        ],
        'leader': {
            'player_id': scoreboard['leader'].player.pk,
            'player_name': scoreboard['leader'].player.get_display_name(),
            'score': scoreboard['leader'].cumulative_score,
        } if scoreboard['leader'] else None,
        'lead_gap': scoreboard['lead_gap'],
        'comeback_candidates': [
            {
                'player_id': c['player'].pk,
                'player_name': c['player'].get_display_name(),
                'deficit': c['deficit'],
                'current_score': c['current_score'],
            }
            for c in scoreboard['comeback_candidates']
        ],
        'round_history': [
            {
                'round': h['round'],
                'snapshots': [
                    {
                        'player_id': s['player'].pk,
                        'player_name': s['player'].get_display_name(),
                        'score': s['score'],
                    }
                    for s in h['snapshots']
                ]
            }
            for h in scoreboard['round_history']
        ],
    }
