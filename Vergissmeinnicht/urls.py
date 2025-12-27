from django.contrib import admin
from django.urls import path, include
from chat.views import *
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Home / index
    path('', index, name='index'),

    # Authentication
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('auth_man.urls')),

    # Chat
    path('chat/<id>/', chat, name='chat'),
    path('chat/', chat_selection, name='chat'),
    path('start_chat/', start_chat, name='start_chat'),
    path('activate_chat/<int:chat_id>/', activate_chat, name='activate_chat'),

    # API
    path('api/get-public-key/<id>/', get_public_key, name='get_public_key'),
    path('upload_public_key/', upload_public_key, name='upload_public_key'),
    path('api/gifs/', gif_list, name='gif-list'),
    path("chat/<int:chat_id>/load/", load_messages, name="load_messages"),
    path("search/<db_model>/<search_for>/", search, name="search"),
    path("search_chats_for_user/", search_chats_for_user, name="search_chats_for_user"),

    # Private Key Management
    path('keys/', manage_keys, name='manage_keys'),               # Export / Import page
    path('keys/import/', import_private_key, name='import_private_key'),
]

# Serve media files during development
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
