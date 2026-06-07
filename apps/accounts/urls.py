from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/avatar/', views.upload_avatar, name='upload_avatar'),
    path('profile/highlights/', views.my_collected_highlights, name='my_highlights'),
    path('profile/patterns/', views.pattern_profile_view, name='pattern_profile'),
    path('profile/<str:username>/', views.profile_view, name='user_profile'),
    path('profile/<str:username>/patterns/', views.pattern_profile_view, name='user_pattern_profile'),
]
