from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Max
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
    recipient_id = None
    if chat:
        recipient_id = chat.user2.id if chat.user1 == request.user else chat.user1.id

    # Annotate each chat with the timestamp of its last message
    user_chats = user_chats.annotate(last_msg_time=Max('messages__timestamp'))

    # Nachrichten des aktuellen Chats nach Zeit (neueste unten)
    messages = Message.objects.filter(chat=chat).order_by('timestamp') if chat else []

    return render(request, 'chat.html', {
        "chat": chat,
        "messages": messages,
        "user_chats": user_chats,
        "recipient_id": recipient_id,
    })


def get_public_key(request, id):
    """Liefert den Public Key eines Users, falls vorhanden."""
    try:
        user = User.objects.get(id=id)
        profile = Profile.objects.get(user=user)
        return HttpResponse(profile.public_key or "")
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


def start_chat(request):
    if request.method == "POST":
        username = request.POST.get("username")
        if not username:
            return render(request, 'start_chat.html', {"error": "Bitte einen Benutzernamen eingeben."})

        try:
            other_user = User.objects.get(username=username)
            if other_user == request.user:
                return render(request, 'start_chat.html', {"error": "Du kannst keinen Chat mit dir selbst starten."})
        except User.DoesNotExist:
            return render(request, 'start_chat.html', {"error": "Benutzer nicht gefunden."})

        # Prüfen, ob bereits ein Chat zwischen den beiden Nutzern existiert
        chat = Chat.objects.filter(
            (Q(user1=request.user) & Q(user2=other_user)) |
            (Q(user1=other_user) & Q(user2=request.user))
        ).first()

        if not chat:
            chat = Chat.objects.create(user1=request.user, user2=other_user)

        return render(request, 'chat.html', {
            "chat": chat,
            "messages": Message.objects.filter(chat=chat).order_by('timestamp'),
            "user_chats": Chat.objects.filter(Q(user1=request.user) | Q(user2=request.user)),
        })

    return render(request, 'start_chat.html', {})


def activate_chat(request, chat_id):
    """Aktiviert einen Chat, damit Nachrichten gesendet werden können."""
    chat = get_object_or_404(Chat, id=chat_id)
    if request.user != chat.user1 and request.user != chat.user2:
        return HttpResponse("You are not part of this chat.", status=403)
    chat.activated = True
    chat.save()
    return render(request, 'chat.html', {
        "chat": chat,
        "messages": Message.objects.filter(chat=chat).order_by('timestamp'),
        "user_chats": Chat.objects.filter(Q(user1=request.user) | Q(user2=request.user)),
        "info": "Chat aktiviert! Du kannst jetzt Nachrichten senden."
    })




@login_required
def manage_keys(request):
    """
    Shows the Export / Import keys page.
    Private keys are only handled in localStorage, not saved in the DB.
    """
    return render(request, 'manage_keys.html', {
        'username': request.user.username
    })


@login_required
@csrf_exempt
def import_private_key(request):
    """
    Speichert einen hochgeladenen privaten Schlüssel
    """
    if request.method != "POST":
        return JsonResponse({"error": "Nur POST erlaubt"}, status=405)

    try:
        data = json.loads(request.body)
        private_key_b64 = data.get("private_key")
        if not private_key_b64:
            return JsonResponse({"error": "Keine private key Daten erhalten"}, status=400)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.private_key = private_key_b64
        profile.save()
        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
