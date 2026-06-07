from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .forms import RegisterForm, LoginForm, ProfileForm, AvatarForm
from .models import User


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'欢迎加入，{user.get_display_name()}！')
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', 'home')
            messages.success(request, f'欢迎回来，{user.get_display_name()}！')
            return redirect(next_url)
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, '已成功退出登录。')
    return redirect('home')


def profile_view(request, username=None):
    if username:
        profile_user = get_object_or_404(User, username=username)
    else:
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        profile_user = request.user

    from apps.games.models import GamePlayer, Game
    from django.db.models import Count, Sum, Avg, Q
    import json

    recent_games = GamePlayer.objects.filter(
        user=profile_user,
        game__status='completed'
    ).select_related('game').order_by('-game__game_time')[:10]

    stats = profile_user.stats

    # Last 10 games score trend
    score_trend = list(
        GamePlayer.objects.filter(
            user=profile_user,
            game__status='completed'
        ).order_by('-game__game_time')[:10].values_list('score', flat=True)
    )
    score_trend.reverse()

    context = {
        'profile_user': profile_user,
        'recent_games': recent_games,
        'stats': stats,
        'score_trend': json.dumps(score_trend),
        'is_own_profile': request.user == profile_user,
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, '个人资料已更新！')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'accounts/edit_profile.html', {'form': form})


@login_required
@require_POST
def upload_avatar(request):
    form = AvatarForm(request.POST, request.FILES, instance=request.user)
    if form.is_valid():
        old_avatar = request.user.avatar
        form.save()
        if old_avatar and hasattr(old_avatar, 'path'):
            import os
            try:
                if os.path.exists(old_avatar.path):
                    os.remove(old_avatar.path)
            except Exception:
                pass
        messages.success(request, '头像已更新！')
    else:
        messages.error(request, '头像上传失败，请选择有效的图片文件。')
    return redirect('accounts:profile')
