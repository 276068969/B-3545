from django import forms
from django.forms import formset_factory
from .models import Game, GamePlayer, GamePlayerPattern, TilePattern
from apps.accounts.models import User
from django.utils import timezone


class GameForm(forms.ModelForm):
    game_time = forms.DateTimeField(
        label='游戏时间',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        initial=timezone.now
    )

    class Meta:
        model = Game
        fields = ('game_time', 'location', 'game_type', 'base_score', 'is_supplemental', 'notes')
        widgets = {
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '如：家里、茶馆...'}),
            'game_type': forms.Select(attrs={'class': 'form-select'}),
            'base_score': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 1000}),
            'is_supplemental': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'location': '游戏地点',
            'game_type': '游戏类型',
            'base_score': '底分（元/分）',
            'is_supplemental': '是否补录',
            'notes': '备注',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['game_time'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')


class PlayerScoreForm(forms.Form):
    user_id = forms.IntegerField(widget=forms.HiddenInput())
    score = forms.IntegerField(
        label='得分',
        widget=forms.NumberInput(attrs={'class': 'form-control score-input', 'placeholder': '正数赢，负数输'})
    )
    patterns = forms.ModelMultipleChoiceField(
        queryset=TilePattern.objects.filter(is_active=True),
        required=False,
        label='牌型',
        widget=forms.CheckboxSelectMultiple()
    )


class GameEditForm(forms.ModelForm):
    game_time = forms.DateTimeField(
        label='游戏时间',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'})
    )

    class Meta:
        model = Game
        fields = ('game_time', 'location', 'game_type', 'base_score', 'notes', 'status')
        widgets = {
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'game_type': forms.Select(attrs={'class': 'form-select'}),
            'base_score': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class GameFilterForm(forms.Form):
    DATE_RANGE_CHOICES = [
        ('', '全部时间'),
        ('today', '今天'),
        ('week', '本周'),
        ('month', '本月'),
        ('custom', '自定义'),
    ]

    date_range = forms.ChoiceField(
        choices=DATE_RANGE_CHOICES, required=False, label='时间范围',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date_from = forms.DateField(
        required=False, label='开始日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    date_to = forms.DateField(
        required=False, label='结束日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    player = forms.ModelChoiceField(
        queryset=User.objects.all(), required=False, label='玩家筛选',
        empty_label='全部玩家',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    game_type = forms.ChoiceField(
        choices=[('', '全部类型')] + Game.GAME_TYPE_CHOICES,
        required=False, label='游戏类型',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    is_supplemental = forms.ChoiceField(
        choices=[('', '全部'), ('0', '正常录入'), ('1', '补录')],
        required=False, label='录入类型',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    supplemental_source = forms.ChoiceField(
        choices=[('', '全部来源')] + Game.SUPPLEMENTAL_SOURCE_CHOICES,
        required=False, label='补录来源',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    search = forms.CharField(
        required=False, label='搜索',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '搜索地点、备注...'})
    )
