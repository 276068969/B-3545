from django.urls import path
from . import views

app_name = 'games'

urlpatterns = [
    path('', views.game_list, name='list'),
    path('create/', views.create_game, name='create'),
    path('<int:pk>/', views.game_detail, name='detail'),
    path('<int:pk>/edit/', views.edit_game, name='edit'),
    path('<int:pk>/delete/', views.delete_game, name='delete'),
    path('<int:game_pk>/snapshot/', views.add_snapshot, name='snapshot'),
    path('batch-delete/', views.batch_delete_games, name='batch_delete'),
    path('backup/', views.backup_data, name='backup'),
    path('restore/', views.restore_data, name='restore'),
    path('import/', views.import_games, name='import'),
    path('import/template/', views.download_template, name='download_template'),
    path('export/', views.export_games, name='export'),
    path('highlights/<int:pk>/collect/', views.collect_highlight, name='collect_highlight'),
    path('highlights/<int:pk>/featured/', views.toggle_highlight_featured, name='toggle_highlight_featured'),
    path('highlights/<int:pk>/pinned/', views.toggle_highlight_pinned, name='toggle_highlight_pinned'),
    path('api/pattern-stats/', views.pattern_stats, name='pattern_stats'),
    path('api/tile-patterns/categories/', views.tile_pattern_categories, name='tile_pattern_categories'),
    path('api/tile-patterns/<int:pk>/', views.tile_pattern_detail, name='tile_pattern_detail'),
    path('api/tile-patterns/', views.tile_pattern_list, name='tile_pattern_list'),
    path('api/playmate-stats/', views.playmate_stats, name='playmate_stats'),
]
