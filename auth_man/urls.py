from django.contrib import admin
from django.urls import path, include
from auth_man.views import *
urlpatterns = [
    path('admin/', admin.site.urls),
    path('signup/', signup, name='signup'),
]