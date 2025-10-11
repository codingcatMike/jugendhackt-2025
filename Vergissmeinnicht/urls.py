"""
URL configuration for Vergissmeinnicht project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from chat.views import *
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('admin/', admin.site.urls),
    #path('check/', check, name='check'),
    path('', index, name='index'),
    path('accounts/', include('django.contrib.auth.urls')),#
    path('accounts/', include('auth_man.urls')),#
    #path('test/', test, name='test'),
    path('chat/<id>',  chat , name='chat'),
    path('chat/',  chat , name='chat'),
    path('api/get-public-key/<id>/', get_public_key, name='get_public_key'),#
    path("upload_public_key/", upload_public_key, name="upload_public_key"),
    path('api/gifs/', gif_list, name='gif-list'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)