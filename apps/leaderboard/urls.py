from django.urls import path
from . import views

app_name = 'leaderboard'

urlpatterns = [
    path('', views.main_leaderboard, name='main'),
    path('domination/', views.domination_board, name='domination'),
    path('comeback/', views.comeback_board, name='comeback'),
    path('highlights/', views.highlights_board, name='highlights'),
    path('vs/', views.player_vs_player, name='vs'),
]
