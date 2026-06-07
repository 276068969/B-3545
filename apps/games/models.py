from django.db import models
from django.conf import settings
from django.utils import timezone


class TilePattern(models.Model):
    CATEGORY_CHOICES = [
        ('special', '特殊牌型'),
        ('color', '花色牌型'),
        ('honor', '字牌牌型'),
        ('basic', '基础牌型'),
        ('combo', '组合牌型'),
        ('custom', '自定义'),
    ]

    name = models.CharField('牌型名称', max_length=50, unique=True)
    category = models.CharField('牌型类别', max_length=20, choices=CATEGORY_CHOICES, default='basic')
    fan_count = models.IntegerField('番数', default=1)
    description = models.TextField('牌型描述', blank=True)
    rarity_score = models.IntegerField('稀有度评分', default=1, help_text='1-10, 用于高光时刻评分')
    is_active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '麻将牌型'
        verbose_name_plural = '麻将牌型列表'
        ordering = ['-rarity_score', 'name']

    def __str__(self):
        return f'{self.name}（{self.fan_count}番）'


class Game(models.Model):
    STATUS_CHOICES = [
        ('active', '进行中'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
    ]
    GAME_TYPE_CHOICES = [
        ('mahjong_16', '16张麻将'),
        ('mahjong_13', '13张麻将'),
        ('guangdong', '广东麻将'),
        ('sichuan', '四川麻将'),
        ('other', '其他'),
    ]

    room = models.ForeignKey(
        'rooms.Room', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='games', verbose_name='关联房间'
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='created_games', verbose_name='录入人'
    )
    game_time = models.DateTimeField('游戏时间', default=timezone.now)
    location = models.CharField('游戏地点', max_length=100, blank=True)
    game_type = models.CharField('游戏类型', max_length=20, choices=GAME_TYPE_CHOICES, default='mahjong_16')
    base_score = models.IntegerField('基础分值', default=1, help_text='每分对应的金额（元）')
    is_supplemental = models.BooleanField('是否为补录', default=False)
    notes = models.TextField('备注', blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField('录入时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '游戏记录'
        verbose_name_plural = '游戏记录列表'
        ordering = ['-game_time']

    def __str__(self):
        return f'游戏#{self.pk} - {self.game_time.strftime("%Y-%m-%d %H:%M")}'

    def get_winner(self):
        winner = self.players.filter(is_winner=True).first()
        return winner

    def is_domination(self):
        """全场通吃：只有一个赢家且其他所有人都是负分"""
        players = list(self.players.all())
        if len(players) < 2:
            return False
        winners = [p for p in players if p.score > 0]
        losers = [p for p in players if p.score < 0]
        return len(winners) == 1 and len(losers) == len(players) - 1

    def get_score_balance(self):
        from django.db.models import Sum
        return self.players.aggregate(total=Sum('score'))['total'] or 0


class GamePlayer(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='players', verbose_name='游戏')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='game_participations', verbose_name='玩家'
    )
    score = models.IntegerField('得分', default=0, help_text='正数为赢，负数为输')
    rank = models.IntegerField('排名', default=1)
    is_winner = models.BooleanField('是否获胜', default=False)

    class Meta:
        verbose_name = '游戏玩家'
        verbose_name_plural = '游戏玩家列表'
        unique_together = ('game', 'user')
        ordering = ['-score']

    def __str__(self):
        return f'{self.user.get_display_name()} - {self.score}分'

    def get_amount(self):
        return self.score * self.game.base_score


class GamePlayerPattern(models.Model):
    game_player = models.ForeignKey(
        GamePlayer, on_delete=models.CASCADE,
        related_name='patterns', verbose_name='游戏玩家'
    )
    tile_pattern = models.ForeignKey(
        TilePattern, on_delete=models.CASCADE,
        related_name='game_occurrences', verbose_name='牌型'
    )
    is_self_draw = models.BooleanField('是否自摸', default=False)
    shooter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='shot_patterns', verbose_name='点炮者'
    )
    zhongma_count = models.IntegerField('中码数量', default=0)
    consecutive_dealer = models.IntegerField('连庄次数', default=0)
    round_number = models.IntegerField('第几局', default=1)
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('记录时间', auto_now_add=True)

    class Meta:
        verbose_name = '牌型记录'
        verbose_name_plural = '牌型记录列表'

    def __str__(self):
        return f'{self.game_player.user.get_display_name()} - {self.tile_pattern.name}'


class GameSnapshot(models.Model):
    """游戏过程中的分数快照，用于追踪逆转"""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='snapshots', verbose_name='游戏')
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='game_snapshots', verbose_name='玩家'
    )
    round_number = models.IntegerField('局数')
    cumulative_score = models.IntegerField('累计分数')
    created_at = models.DateTimeField('记录时间', auto_now_add=True)

    class Meta:
        verbose_name = '分数快照'
        verbose_name_plural = '分数快照列表'
        ordering = ['round_number']


class HighlightCollection(models.Model):
    """高光收藏关系"""
    highlight = models.ForeignKey(
        'Highlight', on_delete=models.CASCADE,
        related_name='collections', verbose_name='高光'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='highlight_collections', verbose_name='用户'
    )
    created_at = models.DateTimeField('收藏时间', auto_now_add=True)

    class Meta:
        verbose_name = '高光收藏'
        verbose_name_plural = '高光收藏列表'
        unique_together = ('highlight', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.get_display_name()} 收藏了 {self.highlight.title}'


class Highlight(models.Model):
    """高光时刻记录"""
    HIGHLIGHT_TYPE_CHOICES = [
        ('domination', '全场通吃'),
        ('comeback', '反败为胜'),
        ('big_win', '大胜局'),
        ('rare_pattern', '稀有牌型'),
        ('other', '其他精彩'),
    ]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='highlights', verbose_name='游戏')
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='highlights', verbose_name='主角'
    )
    highlight_type = models.CharField('高光类型', max_length=20, choices=HIGHLIGHT_TYPE_CHOICES, default='other')
    title = models.CharField('标题', max_length=100)
    description = models.TextField('描述', blank=True)
    highlight_score = models.IntegerField('精彩评分', default=0, help_text='自动计算的精彩程度评分')
    is_comeback = models.BooleanField('是否逆转', default=False)
    comeback_deficit = models.IntegerField('最大落后分', default=0)
    is_domination = models.BooleanField('是否全场通吃', default=False)
    domination_score = models.IntegerField('通吃分数', default=0)
    is_featured = models.BooleanField('精选', default=False)
    collected_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        through='HighlightCollection',
        related_name='collected_highlights', verbose_name='收藏者'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '高光时刻'
        verbose_name_plural = '高光时刻列表'
        ordering = ['-highlight_score', '-created_at']

    def __str__(self):
        return self.title


class PlayerStats(models.Model):
    """玩家统计数据（缓存，每局结束后更新）"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='player_stats', verbose_name='玩家'
    )
    total_games = models.IntegerField('总场次', default=0)
    wins = models.IntegerField('胜场', default=0)
    losses = models.IntegerField('负场', default=0)
    win_rate = models.FloatField('胜率', default=0.0)
    total_score = models.IntegerField('总得分', default=0)
    avg_score = models.FloatField('场均得分', default=0.0)
    max_score = models.IntegerField('最高单场得分', default=0)
    min_score = models.IntegerField('最低单场得分', default=0)
    max_consecutive_wins = models.IntegerField('最大连胜', default=0)
    max_consecutive_losses = models.IntegerField('最大连败', default=0)
    current_consecutive_wins = models.IntegerField('当前连胜', default=0)
    current_consecutive_losses = models.IntegerField('当前连败', default=0)
    domination_count = models.IntegerField('全场通吃次数', default=0)
    comeback_count = models.IntegerField('逆转胜利次数', default=0)
    last_updated = models.DateTimeField('最后更新', auto_now=True)

    class Meta:
        verbose_name = '玩家统计'
        verbose_name_plural = '玩家统计列表'

    def __str__(self):
        return f'{self.user.get_display_name()} 的统计'

    def recalculate(self):
        """重新计算所有统计数据"""
        from django.db.models import Sum, Avg, Max, Min, Count

        game_players = GamePlayer.objects.filter(
            user=self.user,
            game__status='completed'
        ).select_related('game').order_by('game__game_time')

        total = game_players.count()
        wins = game_players.filter(is_winner=True).count()
        losses = total - wins

        agg = game_players.aggregate(
            total_score=Sum('score'),
            avg_score=Avg('score'),
            max_score=Max('score'),
            min_score=Min('score'),
        )

        self.total_games = total
        self.wins = wins
        self.losses = losses
        self.win_rate = (wins / total * 100) if total > 0 else 0
        self.total_score = agg['total_score'] or 0
        self.avg_score = round(agg['avg_score'] or 0, 2)
        self.max_score = agg['max_score'] or 0
        self.min_score = agg['min_score'] or 0

        # Calculate consecutive wins/losses
        max_cw = 0
        max_cl = 0
        curr_cw = 0
        curr_cl = 0
        for gp in game_players:
            if gp.is_winner:
                curr_cw += 1
                curr_cl = 0
            else:
                curr_cl += 1
                curr_cw = 0
            max_cw = max(max_cw, curr_cw)
            max_cl = max(max_cl, curr_cl)

        self.max_consecutive_wins = max_cw
        self.max_consecutive_losses = max_cl
        self.current_consecutive_wins = curr_cw
        self.current_consecutive_losses = curr_cl

        # Count dominations
        domination_games = [
            gp for gp in game_players
            if gp.is_winner and gp.game.is_domination()
        ]
        self.domination_count = len(domination_games)

        # Count comebacks
        self.comeback_count = Highlight.objects.filter(
            winner=self.user, is_comeback=True
        ).count()

        self.save()
