from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.contrib.auth.models import User
from auth_man.models import Profile
from .models import Chat, Message, GIF
import json


def check(request):
    return HttpResponse("It works!")


def index(request):
    return render(request, 'index.html')


def test(request):
    return render(request, 'test.html')


@login_required
def chat(request, id=None):
    """
    Zeigt die Chatseite:
    - Links: alle Chats des eingeloggten Nutzers, sortiert nach letzter Aktivität
    - Rechts: der aktuell ausgewählte Chat (wenn 'id' angegeben)
    """
    user = request.user

    # Liste aller Chats, bei denen der User beteiligt ist
    user_chats = Chat.objects.filter(Q(user1=user) | Q(user2=user))

    # Aktuellen Chat laden (wenn vorhanden)
    chat = get_object_or_404(Chat, id=id) if id else None

    # Nachrichten des aktuellen Chats nach Zeit (neueste unten)
    messages = Message.objects.filter(chat=chat).order_by('timestamp') if chat else []

    # Daten an Template übergeben
    return render(request, 'chat.html', {
        "chat": chat,
        "messages": messages,
        "user_chats": user_chats,
    })


def get_public_key(request, id):
    """Liefert den Public Key eines Users, falls vorhanden."""
    try:
        user = User.objects.get(id=id)
        profile = Profile.objects.get(user=user)
        return HttpResponse(profile.public_key)
    except User.DoesNotExist:
        return HttpResponse("User not found", status=404)
    except Profile.DoesNotExist:
        return HttpResponse("Profile not found", status=404)


@csrf_exempt
@login_required
def upload_public_key(request):
    """
    Speichert den Public Key des eingeloggten Users.
    Wird per JS-POST aufgerufen.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        public_key = data.get("public_key")

        if not public_key:
            return JsonResponse({"error": "No public_key provided"}, status=400)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.public_key = public_key
        profile.save()

        return JsonResponse({"status": "success"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def gif_list(request):
    """Gibt eine JSON-Liste aller gespeicherten GIFs zurück."""
    gifs = GIF.objects.all()
    data = [
        {'id': gif.id, 'name': gif.name, 'url': gif.file.url, 'price': gif.price}
        for gif in gifs
    ]
    return JsonResponse(data, safe=False)
