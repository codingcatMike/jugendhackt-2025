from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Max
from django.contrib.auth.models import User
from auth_man.models import Profile
from .models import Chat, Message, GIF
import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from .models import Message, Chat



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
    messages = Message.objects.filter(chat=chat).order_by("-timestamp")[:20] if chat else []
    messages = reversed(messages)


    return render(request, 'chat.html', {
        "chat": chat,
        "messages": messages,
        "user_chats": user_chats,
        "recipient_id": recipient_id,
    })

def chat_selection(request):
    """Zeigt eine Seite zur Auswahl eines Chats."""
    user = request.user

    # Liste aller Chats, bei denen der User beteiligt ist
    user_chats = Chat.objects.filter(Q(user1=user) | Q(user2=user))

    # Annotate each chat with the timestamp of its last message
    user_chats = user_chats.annotate(last_msg_time=Max('messages__timestamp'))

    return render(request, 'chat_selection.html', {
        "chats": user_chats,
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


from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Chat, Message

def start_chat(request):
    # Check if the form was submitted
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

    # GET request — check if username was passed via URL
    prefill_username = request.GET.get("user", "")
    return render(request, 'start_chat.html', {"prefill_username": prefill_username})



def activate_chat(request, chat_id):
    """Aktiviert einen Chat, damit Nachrichten gesendet werden können."""
    chat = get_object_or_404(Chat, id=chat_id)
    if request.user != chat.user1 and request.user != chat.user2:
        return HttpResponse("You are not part of this chat.", status=403)
    chat.activated = True
    chat.save()
    return redirect('chat', id=chat_id)



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


@login_required
def load_messages(request, chat_id):
    page = int(request.GET.get("page", 1))

    try:
        chat = Chat.objects.get(id=chat_id)
    except Chat.DoesNotExist:
        return JsonResponse({"error": "Chat not found"}, status=404)

    if request.user not in [chat.user1, chat.user2]:
        return JsonResponse({"error": "Forbidden"}, status=403)

    qs = Message.objects.filter(chat=chat).order_by("-timestamp")

    paginator = Paginator(qs, 20)  # 👈 batch size
    page_obj = paginator.get_page(page)

    messages = []
    for m in page_obj.object_list:
        messages.append({
            "id": m.id,
            "sender": m.sender.username,
            "encrypted_message": m.content,
            "encrypted_key_sender": m.encrypted_key_sender,
            "encrypted_key_recipient": m.encrypted_key_recipient,
            "iv": m.iv,
            "media": m.media.url if m.media else None,
            "timestamp": m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "is_me": m.sender == request.user,
        })

    return JsonResponse({
        "messages": messages,
        "has_more": page_obj.has_next()
    })


from django.apps import apps
from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt  # optional if you’re calling via AJAX from JS
def search(request, db_model, search_for):
    """
    Universal search view for any model and any field.

    Parameters:
    - db_model: Name of the model (e.g., 'User', 'Profile', 'Chat')
    - search_for: Field name to search (e.g., 'username', 'nickname', 'title')

    Returns:
    - JSON response with results
    """

    query = request.GET.get('q', '').strip()
    results = []

    # Find the model in any installed app
    model = None
    for app_conf in apps.get_app_configs():
        try:
            model = app_conf.get_model(db_model)
            break
        except LookupError:
            continue

    if not model:
        return JsonResponse({"results": [], "error": f"Model '{db_model}' not found."})

    if query:
        filter_kwargs = {f"{search_for}__icontains": query}
        results = model.objects.filter(**filter_kwargs)

    # Build universal JSON response
    data = []
    for obj in results:
        obj_dict = model_to_dict(obj)
        entry = {"id": obj_dict.get("id")}
        # Include the field we searched for
        if search_for in obj_dict:
            entry[search_for] = obj_dict[search_for]
        # Optionally include all other fields:
        # entry.update(obj_dict)  
        data.append(entry)

    return JsonResponse({"results": data})

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Q
from .models import Chat
from auth_man.models import Profile

def search_chats_for_user(request):
    """
    Search for users for chat selection:
    - If a chat exists with the current user, return the chat id.
    - If no chat exists, return None (frontend can go to creation page).
    """
    query = request.GET.get("q", "").strip()
    user = request.user
    if not query:
        return JsonResponse({"results": []})

    # Find users by username or profile nickname
    user_matches = User.objects.filter(
        Q(username__icontains=query) |
        Q(profile__nickname__icontains=query)  # use reverse FK lookup
    ).exclude(id=user.id)

    results = []
    for u in user_matches:
        # Check if a chat exists between the logged-in user and this user
        chat = Chat.objects.filter(Q(user1=user, user2=u) | Q(user1=u, user2=user)).first()

        # Get nickname from Profile if it exists
        profile = Profile.objects.filter(user=u).first()
        nickname = profile.nickname if profile else ""

        results.append({
            "id": chat.id if chat else None,  # chat exists?
            "username": u.username,
            "nickname": nickname,
        })

    return JsonResponse({"results": results})
