import os
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from apps.games.models import TilePattern, Game, GamePlayer, PlayerStats

User = get_user_model()

TILE_PATTERNS = [
    # 特殊牌型 (天花板级别)
    ('天胡', 'special', 88, '开局第一张牌就胡牌（庄家开局胡牌）', 10),
    ('地胡', 'special', 88, '摸第一张牌就胡牌', 10),
    ('大三元', 'special', 88, '和牌中包含中发白三元牌的三个刻子', 10),
    ('大四喜', 'special', 88, '和牌中包含东南西北四张风牌的刻子', 10),
    ('九莲宝灯', 'special', 88, '清一色加上任意一张可胡牌', 10),
    ('绿一色', 'special', 88, '全部由绿色牌（二三四六八竹及发）组成', 10),
    ('四杠', 'special', 88, '手中有四个杠子', 10),
    ('小三元', 'special', 64, '两副三元牌刻子加一对三元牌对子', 9),
    ('小四喜', 'special', 64, '三副风牌刻子加一对风牌对子', 9),
    ('字一色', 'special', 64, '所有牌均为字牌（风牌和三元牌）', 9),
    ('四暗刻', 'combo', 64, '四个暗刻（包括单骑和牌）', 9),
    # 花色牌型
    ('清一色', 'color', 24, '所有牌均为同一种花色（筒、条或万）', 8),
    ('混一色', 'color', 6, '一种花色加字牌组成', 5),
    ('断幺九', 'color', 2, '所有牌均非一九字牌', 4),
    ('碰碰胡', 'color', 6, '所有面子均为刻子（没有顺子）', 6),
    ('七对', 'color', 4, '由七对牌构成的和牌', 6),
    ('豪华七对', 'color', 8, '七对中有一个四张相同的牌', 7),
    ('双豪华七对', 'color', 24, '七对中有两个四张相同的牌', 8),
    ('全带幺', 'color', 4, '每个面子和对子都包含幺九牌', 6),
    # 组合牌型
    ('一条龙', 'combo', 16, '同种花色1-9各一张连续顺子', 7),
    ('三色同刻', 'combo', 8, '三种花色相同数字的刻子各一组', 6),
    ('三色同顺', 'combo', 2, '三种花色相同数字的顺子各一组', 4),
    ('三暗刻', 'combo', 16, '三个暗刻（没有副露）', 7),
    ('混全带幺九', 'combo', 4, '每组牌都带幺九字牌（含字牌）', 5),
    ('纯全带幺九', 'combo', 16, '每组牌都带幺九牌（不含字牌）', 7),
    # 基础牌型
    ('自摸', 'basic', 1, '自己摸牌胡牌，不需要他人放炮', 2),
    ('门前清', 'basic', 2, '没有任何副露的情况下胡牌', 3),
    ('平胡', 'basic', 1, '无特殊牌型，基本胡牌', 1),
    ('海底捞月', 'basic', 1, '摸到牌河最后一张牌胡牌', 3),
    ('河底捞鱼', 'basic', 1, '他人打出最后一张牌时点炮胡牌', 3),
    ('岭上开花', 'basic', 1, '补杠后摸到的牌胡牌', 3),
    ('抢杠', 'basic', 1, '他人进行明杠时以该牌胡牌', 4),
]

# 默认演示账号
DEMO_USERS = [
    {
        'username': 'zhangsan',
        'nickname': '张三',
        'password': 'demo123456',
        'email': 'zhangsan@mahjong.local',
    },
    {
        'username': 'lisi',
        'nickname': '李四',
        'password': 'demo123456',
        'email': 'lisi@mahjong.local',
    },
    {
        'username': 'wangwu',
        'nickname': '王五',
        'password': 'demo123456',
        'email': 'wangwu@mahjong.local',
    },
    {
        'username': 'zhaoliu',
        'nickname': '赵六',
        'password': 'demo123456',
        'email': 'zhaoliu@mahjong.local',
    },
]

# 演示战绩数据（4人局，得分之和为0）
DEMO_GAMES = [
    # (地点, 距今天数, [(用户名, 得分), ...])
    ('茶馆',  1, [('zhangsan', 45), ('lisi', -15), ('wangwu', -20), ('zhaoliu', -10)]),
    ('家里',  2, [('lisi', 60), ('zhangsan', -20), ('wangwu', -25), ('zhaoliu', -15)]),
    ('茶馆',  3, [('wangwu', 30), ('zhaoliu', 10), ('zhangsan', -15), ('lisi', -25)]),
    ('办公室', 5, [('zhangsan', 50), ('lisi', -10), ('wangwu', -15), ('zhaoliu', -25)]),
    ('家里',  6, [('zhaoliu', 70), ('wangwu', -10), ('zhangsan', -30), ('lisi', -30)]),
    ('茶馆',  8, [('lisi', 25), ('zhangsan', 15), ('wangwu', -20), ('zhaoliu', -20)]),
    ('家里', 10, [('wangwu', 55), ('zhaoliu', -5), ('lisi', -20), ('zhangsan', -30)]),
    ('茶馆', 12, [('zhangsan', 80), ('lisi', -20), ('wangwu', -30), ('zhaoliu', -30)]),
    ('办公室',14, [('zhaoliu', 40), ('lisi', 20), ('wangwu', -25), ('zhangsan', -35)]),
    ('家里', 16, [('lisi', 65), ('zhangsan', -15), ('wangwu', -20), ('zhaoliu', -30)]),
    ('茶馆', 18, [('wangwu', 35), ('zhangsan', 25), ('lisi', -30), ('zhaoliu', -30)]),
    ('家里', 20, [('zhangsan', 90), ('zhaoliu', -10), ('lisi', -35), ('wangwu', -45)]),
    ('茶馆', 22, [('zhaoliu', 55), ('wangwu', -5), ('zhangsan', -20), ('lisi', -30)]),
    ('办公室',24, [('lisi', 45), ('zhangsan', 15), ('wangwu', -25), ('zhaoliu', -35)]),
    ('家里', 26, [('wangwu', 60), ('zhaoliu', 10), ('lisi', -30), ('zhangsan', -40)]),
]


class Command(BaseCommand):
    help = '初始化默认数据（管理员账号、演示账号、麻将牌型、演示战绩）'

    def handle(self, *args, **options):
        self.stdout.write('🀄 正在初始化麻将战绩系统数据...')
        self.create_default_avatar()
        self.create_admin()
        self.create_tile_patterns()
        users = self.create_demo_users()
        if users:
            self.create_demo_games(users)
        self.stdout.write(self.style.SUCCESS('✅ 初始化完成！'))
        self.stdout.write(self.style.SUCCESS('📌 管理员账号: admin / admin123456'))
        self.stdout.write(self.style.SUCCESS('👥 演示账号（密码均为 demo123456）: zhangsan / lisi / wangwu / zhaoliu'))
        self.stdout.write(self.style.SUCCESS('🌐 访问地址: http://localhost:8888'))

    def create_default_avatar(self):
        img_dir = os.path.join(settings.STATIC_ROOT or settings.STATICFILES_DIRS[0], 'img')
        os.makedirs(img_dir, exist_ok=True)
        avatar_path = os.path.join(img_dir, 'default_avatar.png')
        if not os.path.exists(avatar_path):
            try:
                from PIL import Image, ImageDraw
                img = Image.new('RGBA', (100, 100), (30, 52, 72, 255))
                draw = ImageDraw.Draw(img)
                draw.ellipse([30, 15, 70, 55], fill=(201, 162, 39, 255))
                draw.ellipse([15, 58, 85, 100], fill=(201, 162, 39, 200))
                img.save(avatar_path, 'PNG')
                self.stdout.write('✅ 默认头像创建成功')
            except Exception:
                self.stdout.write('ℹ️  默认头像将使用 CSS fallback')

    def create_admin(self):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@mahjong.local',
                password='admin123456',
                nickname='管理员',
            )
            self.stdout.write(self.style.SUCCESS('✅ 管理员账号创建成功 (admin / admin123456)'))
        else:
            self.stdout.write('ℹ️  管理员账号已存在，跳过')

    def create_tile_patterns(self):
        created = 0
        for name, category, fan_count, description, rarity_score in TILE_PATTERNS:
            _, is_created = TilePattern.objects.get_or_create(
                name=name,
                defaults={
                    'category': category,
                    'fan_count': fan_count,
                    'description': description,
                    'rarity_score': rarity_score,
                    'is_active': True,
                }
            )
            if is_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(
            f'✅ 麻将牌型初始化完成（新增 {created} 种，共 {TilePattern.objects.count()} 种）'
        ))

    def create_demo_users(self):
        users = {}
        created_count = 0
        for info in DEMO_USERS:
            if not User.objects.filter(username=info['username']).exists():
                user = User.objects.create_user(
                    username=info['username'],
                    nickname=info['nickname'],
                    email=info['email'],
                    password=info['password'],
                )
                users[info['username']] = user
                created_count += 1
            else:
                users[info['username']] = User.objects.get(username=info['username'])

        if created_count:
            self.stdout.write(self.style.SUCCESS(
                f'✅ 演示账号创建成功（新增 {created_count} 个）：' +
                ' / '.join(u['nickname'] for u in DEMO_USERS)
            ))
        else:
            self.stdout.write('ℹ️  演示账号已存在，跳过')
        return users

    def create_demo_games(self, users):
        # 只在没有战绩时才创建演示数据
        if Game.objects.filter(creator=users.get('zhangsan')).exists():
            self.stdout.write('ℹ️  演示战绩已存在，跳过')
            return

        admin_user = User.objects.filter(username='admin').first()
        creator = admin_user or list(users.values())[0]
        now = timezone.now()
        created_count = 0

        for location, days_ago, player_scores in DEMO_GAMES:
            # 随机偏移小时和分钟，让时间更自然
            random_hours = random.randint(18, 22)
            random_minutes = random.choice([0, 15, 30, 45])
            game_time = (now - timedelta(days=days_ago)).replace(
                hour=random_hours, minute=random_minutes, second=0, microsecond=0
            )

            game = Game.objects.create(
                creator=creator,
                game_time=game_time,
                location=location,
                game_type='mahjong_16',
                base_score=1,
                is_supplemental=False,
                status='completed',
                notes='',
            )

            max_score = max(score for _, score in player_scores)
            for rank, (username, score) in enumerate(
                sorted(player_scores, key=lambda x: x[1], reverse=True), 1
            ):
                user = users.get(username)
                if user:
                    GamePlayer.objects.create(
                        game=game,
                        user=user,
                        score=score,
                        rank=rank,
                        is_winner=(score == max_score and score > 0),
                    )
            created_count += 1

        # 更新所有演示玩家统计
        for user in users.values():
            stats, _ = PlayerStats.objects.get_or_create(user=user)
            stats.recalculate()

        self.stdout.write(self.style.SUCCESS(f'✅ 演示战绩创建成功（{created_count} 场）'))
