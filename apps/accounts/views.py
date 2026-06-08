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

    from apps.games.models import GamePlayer, Game, Highlight, HighlightCollection
    from django.db.models import Count, Sum, Avg, Q
    import json

    recent_games = GamePlayer.objects.filter(
        user=profile_user,
        game__status='completed'
    ).select_related('game').order_by('-game__game_time')[:10]

    stats = profile_user.stats

    collected_count = 0
    collected_highlights = []
    if request.user == profile_user:
        collected_count = HighlightCollection.objects.filter(user=profile_user).count()
        collected_highlights = HighlightCollection.objects.filter(
            user=profile_user
        ).select_related(
            'highlight', 'highlight__game', 'highlight__winner'
        ).prefetch_related(
            'highlight__game__players__user'
        ).order_by('-created_at')[:4]

    user_highlights = Highlight.objects.filter(
        winner=profile_user
    ).select_related(
        'game'
    ).prefetch_related(
        'game__players__user'
    ).order_by('-is_pinned', '-is_featured', '-highlight_score', '-created_at')[:4]

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
        'collected_count': collected_count,
        'collected_highlights': collected_highlights,
        'user_highlights': user_highlights,
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


@login_required
def my_collected_highlights(request):
    from apps.games.models import Highlight, HighlightCollection
    from django.core.paginator import Paginator

    sort_by = request.GET.get('sort', 'collect_time')
    highlight_type = request.GET.get('type', '')

    collections_qs = HighlightCollection.objects.filter(
        user=request.user
    ).select_related(
        'highlight', 'highlight__game', 'highlight__winner'
    ).prefetch_related(
        'highlight__game__players__user'
    )

    if highlight_type:
        collections_qs = collections_qs.filter(highlight__highlight_type=highlight_type)

    if sort_by == 'score':
        collections_qs = collections_qs.order_by('-highlight__highlight_score', '-created_at')
    elif sort_by == 'type':
        collections_qs = collections_qs.order_by('highlight__highlight_type', '-created_at')
    else:
        collections_qs = collections_qs.order_by('-created_at')

    paginator = Paginator(collections_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    params = request.GET.copy()
    params.pop('page', None)
    base_query = params.urlencode()

    context = {
        'page_obj': page_obj,
        'sort_by': sort_by,
        'highlight_type': highlight_type,
        'highlight_type_choices': Highlight.HIGHLIGHT_TYPE_CHOICES,
        'base_query': base_query,
        'total_count': collections_qs.count(),
    }
    return render(request, 'accounts/my_highlights.html', context)


def pattern_profile_view(request, username=None):
    if username:
        profile_user = get_object_or_404(User, username=username)
    else:
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        profile_user = request.user

    from apps.games.models import GamePlayerPattern, TilePattern, Highlight
    from django.db.models import Count, Sum, Max, Q
    import json

    patterns_qs = GamePlayerPattern.objects.filter(
        game_player__user=profile_user,
        game_player__game__status='completed'
    ).select_related(
        'tile_pattern', 'game_player', 'game_player__game'
    )

    total_pattern_count = patterns_qs.count()

    pattern_stats = patterns_qs.values(
        'tile_pattern__id',
        'tile_pattern__name',
        'tile_pattern__category',
        'tile_pattern__fan_count',
        'tile_pattern__rarity_score',
        'tile_pattern__description',
    ).annotate(
        count=Count('id'),
        self_draw_count=Count('id', filter=Q(is_self_draw=True)),
        total_fan=Sum('tile_pattern__fan_count'),
    ).order_by('-count', '-tile_pattern__fan_count')

    top_patterns = list(pattern_stats[:10])

    category_stats = patterns_qs.values(
        'tile_pattern__category'
    ).annotate(
        count=Count('id')
    ).order_by('-count')

    category_dict = {}
    for cat in category_stats:
        category_dict[cat['tile_pattern__category']] = cat['count']

    category_display = dict(TilePattern.CATEGORY_CHOICES)
    categories_data = []
    for cat_key, cat_label in category_display.items():
        count = category_dict.get(cat_key, 0)
        percentage = round(count / total_pattern_count * 100, 1) if total_pattern_count > 0 else 0
        categories_data.append({
            'key': cat_key,
            'label': cat_label,
            'count': count,
            'percentage': percentage,
        })
    categories_data.sort(key=lambda x: x['count'], reverse=True)

    highest_fan_pattern = None
    if pattern_stats.exists():
        highest_fan_pattern = pattern_stats.order_by('-tile_pattern__fan_count').first()

    self_draw_count = patterns_qs.filter(is_self_draw=True).count()
    self_draw_rate = (self_draw_count / total_pattern_count * 100) if total_pattern_count > 0 else 0

    rare_patterns_count = patterns_qs.filter(tile_pattern__rarity_score__gte=8).count()

    rare_highlights = Highlight.objects.filter(
        winner=profile_user,
        highlight_type='rare_pattern'
    ).select_related('game').order_by('-highlight_score', '-created_at')[:6]

    total_fan_sum = patterns_qs.aggregate(total=Sum('tile_pattern__fan_count'))['total'] or 0
    avg_fan = round(total_fan_sum / total_pattern_count, 1) if total_pattern_count > 0 else 0

    pattern_trend = []
    recent_patterns = patterns_qs.order_by('-game_player__game__game_time')[:20]
    pattern_trend_labels = []
    pattern_trend_data = []
    for i, p in enumerate(recent_patterns[::-1]):
        pattern_trend_labels.append(f'第{i+1}次')
        pattern_trend_data.append(p.tile_pattern.fan_count)

    context = {
        'profile_user': profile_user,
        'is_own_profile': request.user == profile_user,
        'total_pattern_count': total_pattern_count,
        'top_patterns': top_patterns,
        'categories_data': categories_data,
        'highest_fan_pattern': highest_fan_pattern,
        'self_draw_count': self_draw_count,
        'self_draw_rate': round(self_draw_rate, 1),
        'rare_patterns_count': rare_patterns_count,
        'rare_highlights': rare_highlights,
        'total_fan_sum': total_fan_sum,
        'avg_fan': avg_fan,
        'pattern_trend_labels': json.dumps(pattern_trend_labels),
        'pattern_trend_data': json.dumps(pattern_trend_data),
        'category_choices': TilePattern.CATEGORY_CHOICES,
    }
    return render(request, 'accounts/pattern_profile.html', context)
