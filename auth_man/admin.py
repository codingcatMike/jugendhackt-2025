from django.contrib import admin
from .models import Profile
from chat.models import *
# Register your models here.
admin.site.register(Profile)
admin.site.register(Chat)
admin.site.register(Message)
admin.site.register(GIF)