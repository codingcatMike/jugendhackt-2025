from django import forms
from django.contrib.auth.models import User
from .models import Profile
from django.contrib.auth.forms import UserCreationForm

class SignUpForm(UserCreationForm):
    nickname = forms.CharField(max_length=30, required=False, help_text='Optional. 30 characters or fewer.')

    class Meta:
        model = User
        fields = ('username', "password1", "password2", 'nickname')
