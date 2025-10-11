from django.contrib import admin
from .models import Profile
from chat.models import Chat, Message
# Register your models here.
admin.site.register(Profile)
admin.site.register(Chat)
admin.site.register(Message)
