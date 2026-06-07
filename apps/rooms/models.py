import random
import string
from django.db import models
from django.conf import settings


def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


class Room(models.Model):
    GAME_TYPE_CHOICES = [
        ('mahjong_16', '16张麻将'),
        ('mahjong_13', '13张麻将'),
        ('guangdong', '广东麻将'),
        ('sichuan', '四川麻将'),
        ('other', '其他'),
    ]
    STATUS_CHOICES = [
        ('waiting', '等待中'),
        ('playing', '游戏中'),
        ('finished', '已结束'),
    ]

    name = models.CharField('房间名称', max_length=100)
    code = models.CharField('房间码', max_length=10, unique=True, default=generate_room_code)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='hosted_rooms', verbose_name='房主'
    )
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='waiting')
    game_type = models.CharField('游戏类型', max_length=20, choices=GAME_TYPE_CHOICES, default='mahjong_16')
    max_players = models.IntegerField('最大人数', default=4)
    base_score = models.IntegerField('基础分值', default=1, help_text='每分对应的金额（元）')
    description = models.TextField('房间描述', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '游戏房间'
        verbose_name_plural = '游戏房间列表'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} [{self.code}]'

    def get_player_count(self):
        return self.members.filter(is_active=True).count()

    def is_full(self):
        return self.get_player_count() >= self.max_players

    def can_join(self, user):
        if self.status != 'waiting':
            return False, '房间已关闭'
        if self.is_full():
            return False, '房间已满'
        if self.members.filter(user=user, is_active=True).exists():
            return False, '您已在房间中'
        return True, '可以加入'

    def get_active_game(self):
        return self.games.filter(status='active').order_by('-created_at').first()

    def get_current_round(self):
        game = self.get_active_game()
        if not game:
            return 0
        from apps.games.models import GameSnapshot
        max_round = GameSnapshot.objects.filter(game=game).aggregate(
            max_round=models.Max('round_number')
        )['max_round']
        return max_round or 0

    def get_latest_snapshots(self):
        game = self.get_active_game()
        if not game:
            return []
        current_round = self.get_current_round()
        if current_round == 0:
            return []
        from apps.games.models import GameSnapshot
        return GameSnapshot.objects.filter(
            game=game, round_number=current_round
        ).select_related('player').order_by('-cumulative_score')

    def get_scoreboard_data(self):
        game = self.get_active_game()
        if not game:
            return {
                'has_active_game': False,
                'current_round': 0,
                'players': [],
                'leader': None,
                'trailer': None,
                'lead_gap': 0,
                'comeback_candidates': [],
                'round_history': [],
            }
        current_round = self.get_current_round()
        snapshots = self.get_latest_snapshots()
        
        players = []
        leader = None
        trailer = None
        lead_gap = 0
        comeback_candidates = []
        
        if snapshots:
            sorted_snaps = sorted(snapshots, key=lambda s: s.cumulative_score, reverse=True)
            leader = sorted_snaps[0]
            trailer = sorted_snaps[-1]
            lead_gap = leader.cumulative_score - trailer.cumulative_score
            
            for rank, snap in enumerate(sorted_snaps, 1):
                players.append({
                    'player': snap.player,
                    'score': snap.cumulative_score,
                    'rank': rank,
                    'snapshot': snap,
                })
            
            if current_round >= 2:
                from apps.games.models import GameSnapshot
                prev_snapshots = GameSnapshot.objects.filter(
                    game=game, round_number=current_round - 1
                ).select_related('player')
                prev_scores = {s.player_id: s.cumulative_score for s in prev_snapshots}
                
                for snap in sorted_snaps:
                    prev_score = prev_scores.get(snap.player_id, 0)
                    if prev_score < 0 and snap.cumulative_score > 0:
                        comeback_candidates.append({
                            'player': snap.player,
                            'deficit': abs(prev_score),
                            'current_score': snap.cumulative_score,
                        })
        
        from apps.games.models import GameSnapshot
        all_rounds = sorted(set(
            GameSnapshot.objects.filter(game=game).values_list('round_number', flat=True)
        ))
        round_history = []
        for rnd in all_rounds:
            round_snaps = GameSnapshot.objects.filter(
                game=game, round_number=rnd
            ).select_related('player').order_by('-cumulative_score')
            round_history.append({
                'round': rnd,
                'snapshots': [
                    {'player': s.player, 'score': s.cumulative_score}
                    for s in round_snaps
                ]
            })
        
        return {
            'has_active_game': True,
            'game': game,
            'current_round': current_round,
            'players': players,
            'leader': leader,
            'trailer': trailer,
            'lead_gap': lead_gap,
            'comeback_candidates': comeback_candidates,
            'round_history': round_history,
        }


class RoomMember(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members', verbose_name='房间')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='room_memberships', verbose_name='玩家'
    )
    joined_at = models.DateTimeField('加入时间', auto_now_add=True)
    is_active = models.BooleanField('活跃状态', default=True)
    is_ready = models.BooleanField('准备状态', default=False)

    class Meta:
        verbose_name = '房间成员'
        verbose_name_plural = '房间成员列表'
        unique_together = ('room', 'user')

    def __str__(self):
        return f'{self.user.get_display_name()} in {self.room.name}'
