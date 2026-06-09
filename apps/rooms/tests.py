from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.rooms.models import Room, RoomMember
from apps.games.models import Game, GamePlayer, GameSnapshot

User = get_user_model()


class RoomStatsSummaryTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username='host', password='test123')
        self.player1 = User.objects.create_user(username='player1', password='test123')
        self.player2 = User.objects.create_user(username='player2', password='test123')
        self.player3 = User.objects.create_user(username='player3', password='test123')

        self.room = Room.objects.create(
            name='测试房间',
            host=self.host,
            status='waiting',
            game_type='mahjong_16',
            max_players=4,
            base_score=1,
        )
        RoomMember.objects.create(room=self.room, user=self.host, is_active=True)
        RoomMember.objects.create(room=self.room, user=self.player1, is_active=True)
        RoomMember.objects.create(room=self.room, user=self.player2, is_active=True)
        RoomMember.objects.create(room=self.room, user=self.player3, is_active=True)

    def test_empty_room_no_games(self):
        stats = self.room.get_stats_summary()
        self.assertEqual(stats['total_games'], 0)
        self.assertEqual(stats['total_rounds'], 0)
        self.assertIsNone(stats['last_active_at'])
        self.assertEqual(len(stats['regular_players']), 0)
        self.assertEqual(len(stats['top_winners']), 0)

    def test_active_game_only_no_completed(self):
        game = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='active',
            game_time=timezone.now(),
        )
        GamePlayer.objects.create(game=game, user=self.host, score=0, is_winner=False)
        GamePlayer.objects.create(game=game, user=self.player1, score=0, is_winner=False)
        GamePlayer.objects.create(game=game, user=self.player2, score=0, is_winner=False)
        GamePlayer.objects.create(game=game, user=self.player3, score=0, is_winner=False)

        stats = self.room.get_stats_summary()
        self.assertEqual(stats['total_games'], 0)
        self.assertEqual(stats['total_rounds'], 0)
        self.assertIsNotNone(stats['last_active_at'])
        self.assertEqual(stats['last_active_at'], game.game_time)
        self.assertEqual(len(stats['regular_players']), 0)

    def test_completed_games_only(self):
        game1 = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='completed',
            game_time=timezone.now(),
        )
        GamePlayer.objects.create(game=game1, user=self.host, score=10, rank=1, is_winner=True)
        GamePlayer.objects.create(game=game1, user=self.player1, score=-5, rank=2, is_winner=False)
        GamePlayer.objects.create(game=game1, user=self.player2, score=-3, rank=3, is_winner=False)
        GamePlayer.objects.create(game=game1, user=self.player3, score=-2, rank=4, is_winner=False)

        stats = self.room.get_stats_summary()
        self.assertEqual(stats['total_games'], 1)
        self.assertIsNotNone(stats['last_active_at'])
        self.assertEqual(stats['last_active_at'], game1.game_time)
        self.assertEqual(stats['host_win_rate'], 100.0)
        self.assertEqual(stats['host_wins'], 1)
        self.assertEqual(stats['host_games'], 1)
        self.assertEqual(stats['total_amount'], 10)

    def test_both_active_and_completed_games(self):
        completed_game = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='completed',
            game_time=timezone.now(),
        )
        GamePlayer.objects.create(game=completed_game, user=self.host, score=10, rank=1, is_winner=True)
        GamePlayer.objects.create(game=completed_game, user=self.player1, score=-5, rank=2, is_winner=False)
        GamePlayer.objects.create(game=completed_game, user=self.player2, score=-3, rank=3, is_winner=False)
        GamePlayer.objects.create(game=completed_game, user=self.player3, score=-2, rank=4, is_winner=False)

        active_game_time = timezone.now()
        active_game = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='active',
            game_time=active_game_time,
        )
        GamePlayer.objects.create(game=active_game, user=self.host, score=0, is_winner=False)
        GamePlayer.objects.create(game=active_game, user=self.player1, score=0, is_winner=False)
        GamePlayer.objects.create(game=active_game, user=self.player2, score=0, is_winner=False)
        GamePlayer.objects.create(game=active_game, user=self.player3, score=0, is_winner=False)

        stats = self.room.get_stats_summary()
        self.assertEqual(stats['total_games'], 1)
        self.assertIsNotNone(stats['last_active_at'])
        self.assertEqual(stats['last_active_at'], active_game_time)

    def test_last_active_at_prefers_latest_game(self):
        old_game = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='completed',
            game_time=timezone.datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        GamePlayer.objects.create(game=old_game, user=self.host, score=10, rank=1, is_winner=True)
        GamePlayer.objects.create(game=old_game, user=self.player1, score=-10, rank=2, is_winner=False)

        new_game = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='completed',
            game_time=timezone.datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        GamePlayer.objects.create(game=new_game, user=self.player1, score=20, rank=1, is_winner=True)
        GamePlayer.objects.create(game=new_game, user=self.host, score=-20, rank=2, is_winner=False)

        stats = self.room.get_stats_summary()
        self.assertEqual(stats['last_active_at'], new_game.game_time)
        self.assertEqual(stats['total_games'], 2)
        self.assertEqual(stats['host_wins'], 1)
        self.assertEqual(stats['host_games'], 2)
        self.assertEqual(stats['host_win_rate'], 50.0)

    def test_regular_players_sorted_by_games(self):
        for i in range(5):
            game = Game.objects.create(
                room=self.room,
                creator=self.host,
                game_type='mahjong_16',
                base_score=1,
                status='completed',
                game_time=timezone.now(),
            )
            GamePlayer.objects.create(game=game, user=self.host, score=i, rank=1, is_winner=True)
            GamePlayer.objects.create(game=game, user=self.player1, score=-i, rank=2, is_winner=False)
            if i < 3:
                GamePlayer.objects.create(game=game, user=self.player2, score=0, rank=3, is_winner=False)
            if i < 1:
                GamePlayer.objects.create(game=game, user=self.player3, score=0, rank=4, is_winner=False)

        stats = self.room.get_stats_summary()
        regular = stats['regular_players']
        self.assertGreaterEqual(len(regular), 3)
        self.assertEqual(regular[0]['player'].pk, self.host.pk)
        self.assertEqual(regular[0]['games_played'], 5)
        self.assertEqual(regular[1]['player'].pk, self.player1.pk)
        self.assertEqual(regular[1]['games_played'], 5)
        self.assertEqual(regular[2]['player'].pk, self.player2.pk)
        self.assertEqual(regular[2]['games_played'], 3)

    def test_top_winners_sorted_by_score(self):
        game1 = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='completed',
            game_time=timezone.now(),
        )
        GamePlayer.objects.create(game=game1, user=self.host, score=50, rank=1, is_winner=True)
        GamePlayer.objects.create(game=game1, user=self.player1, score=-20, rank=2, is_winner=False)
        GamePlayer.objects.create(game=game1, user=self.player2, score=-20, rank=3, is_winner=False)
        GamePlayer.objects.create(game=game1, user=self.player3, score=-10, rank=4, is_winner=False)

        game2 = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='completed',
            game_time=timezone.now(),
        )
        GamePlayer.objects.create(game=game2, user=self.player1, score=30, rank=1, is_winner=True)
        GamePlayer.objects.create(game=game2, user=self.host, score=-30, rank=2, is_winner=False)
        GamePlayer.objects.create(game=game2, user=self.player2, score=0, rank=3, is_winner=False)
        GamePlayer.objects.create(game=game2, user=self.player3, score=0, rank=4, is_winner=False)

        stats = self.room.get_stats_summary()
        top = stats['top_winners']
        self.assertEqual(len(top), 3)
        self.assertEqual(top[0]['player'].pk, self.host.pk)
        self.assertEqual(top[0]['total_score'], 20)
        self.assertEqual(top[1]['player'].pk, self.player1.pk)
        self.assertEqual(top[1]['total_score'], 10)

    def test_total_rounds_with_snapshots(self):
        game = Game.objects.create(
            room=self.room,
            creator=self.host,
            game_type='mahjong_16',
            base_score=1,
            status='completed',
            game_time=timezone.now(),
        )
        GamePlayer.objects.create(game=game, user=self.host, score=30, rank=1, is_winner=True)
        GamePlayer.objects.create(game=game, user=self.player1, score=-10, rank=2, is_winner=False)
        GamePlayer.objects.create(game=game, user=self.player2, score=-10, rank=3, is_winner=False)
        GamePlayer.objects.create(game=game, user=self.player3, score=-10, rank=4, is_winner=False)

        for round_num in range(1, 4):
            for player in [self.host, self.player1, self.player2, self.player3]:
                GameSnapshot.objects.create(
                    game=game,
                    player=player,
                    round_number=round_num,
                    cumulative_score=round_num * 10 if player == self.host else -round_num * 3,
                )

        stats = self.room.get_stats_summary()
        self.assertEqual(stats['total_rounds'], 3)
