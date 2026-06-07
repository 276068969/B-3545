from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, label='邮箱')
    nickname = forms.CharField(max_length=50, required=False, label='昵称')

    class Meta:
        model = User
        fields = ('username', 'email', 'nickname', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        self.fields['username'].label = '用户名'
        self.fields['password1'].label = '密码'
        self.fields['password2'].label = '确认密码'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.nickname = self.cleaned_data.get('nickname', '')
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['username'].label = '用户名'
        self.fields['password'].widget.attrs['class'] = 'form-control'
        self.fields['password'].label = '密码'


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('nickname', 'bio')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        self.fields['nickname'].label = '昵称'
        self.fields['bio'].label = '个人简介'
        self.fields['bio'].widget = forms.Textarea(attrs={'class': 'form-control', 'rows': 3})


class AvatarForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('avatar',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avatar'].widget.attrs['class'] = 'form-control'
        self.fields['avatar'].label = '头像图片'
