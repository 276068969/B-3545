from django.urls import path
from . import views

app_name = 'rooms'

urlpatterns = [
    path('', views.room_list, name='list'),
    path('create/', views.create_room, name='create'),
    path('<int:pk>/', views.room_detail, name='detail'),
    path('<int:pk>/join/', views.join_room, name='join'),
    path('<int:pk>/leave/', views.leave_room, name='leave'),
    path('<int:pk>/ready/', views.toggle_ready, name='toggle_ready'),
    path('<int:pk>/close/', views.close_room, name='close'),
    path('<int:pk>/start/', views.start_game, name='start_game'),
    path('<int:pk>/scoreboard/start/', views.start_scoreboard, name='start_scoreboard'),
    path('<int:pk>/scoreboard/record/', views.record_round, name='record_round'),
    path('<int:pk>/scoreboard/api/', views.scoreboard_api, name='scoreboard_api'),
    path('<int:pk>/scoreboard/end/', views.end_scoreboard, name='end_scoreboard'),
    path('join-by-code/', views.join_by_code, name='join_by_code'),
]
