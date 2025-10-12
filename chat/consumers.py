from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils.html import escape
from django.utils.text import get_valid_filename
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.timezone import now
from .models import Chat, Message
from auth_man.models import Profile
import json
import base64
from datetime import date

# ------------------- CONFIG -------------------
MAX_MESSAGES_PER_DAY = 5
MAX_MEDIA_PER_DAY = 10
ALLOWED_MEDIA_TYPES = ["image/png", "image/jpeg", "image/gif"]
MAX_MEDIA_SIZE_MB = 5
# ----------------------------------------------

class ChatConsumer(AsyncWebsocketConsumer):
    # Store daily counters in-memory per consumer instance
    daily_text_count = {}
    daily_media_count = {}

    async def connect(self):
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]
        self.group_name = f"chat_{self.chat_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"[WS] Connected to {self.group_name}")

        # Initialize daily counters for this user
        user = self.scope["user"]
        today_str = str(date.today())
        if user.is_authenticated:
            self.daily_text_count[(user.id, today_str)] = await count_text_messages_today_db(self.chat_id, user)
            self.daily_media_count[(user.id, today_str)] = await count_media_today_db(self.chat_id, user)
            print(f"[DEBUG] Initial counts for user {user.username}: text={self.daily_text_count[(user.id, today_str)]}, media={self.daily_media_count[(user.id, today_str)]}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print(f"[WS] Disconnected from {self.group_name}")

    async def receive(self, text_data):
        data = json.loads(text_data)
        sender = self.scope["user"]

        if not sender.is_authenticated:
            await self.send(json.dumps({"error": "Nicht angemeldet!"}))
            return

        today_str = str(date.today())
        is_gif = data.get("media_type") == "gif"
        has_media = "media" in data and bool(data["media"])

        # --- TEXT LIMIT ---
        if "encrypted_message" in data and data["encrypted_message"].strip() and not has_media and not is_gif:
            current_count = self.daily_text_count.get((sender.id, today_str), 0)
            print(f"[DEBUG] Text messages sent today (before increment): {current_count}")
            if current_count >= MAX_MESSAGES_PER_DAY:
                await self.send(json.dumps({"error": f"Du kannst heute nur {MAX_MESSAGES_PER_DAY} Textnachricht(en) senden!"}))
                return
            self.daily_text_count[(sender.id, today_str)] = current_count + 1

        # --- MEDIA/GIF LIMIT ---
        if has_media or is_gif:
            current_media_count = self.daily_media_count.get((sender.id, today_str), 0)
            print(f"[DEBUG] Media messages sent today (before increment): {current_media_count}")
            if current_media_count >= MAX_MEDIA_PER_DAY:
                await self.send(json.dumps({"error": f"Du kannst heute nur {MAX_MEDIA_PER_DAY} Mediendatei(en) senden!"}))
                return
            self.daily_media_count[(sender.id, today_str)] = current_media_count + 1

        # --- GIF COIN CHECK ---
        if is_gif:
            try:
                price = int(data.get("price", 0))
            except (ValueError, TypeError):
                price = 0
            profile = await get_user_profile(sender)
            if profile.coins < price:
                await self.send(json.dumps({"error": "Nicht genügend Coins für dieses GIF!"}))
                return
            await deduct_coins(profile, price)

        # --- MEDIA DECODING ---
        media_file = None
        if has_media:
            try:
                format, imgstr = data["media"].split(";base64,")
                mime_type = format.split(":")[-1]
                if mime_type not in ALLOWED_MEDIA_TYPES:
                    await self.send(json.dumps({"error": "Nicht erlaubter Medientyp!"}))
                    return
                decoded_file = base64.b64decode(imgstr)
                if len(decoded_file) > MAX_MEDIA_SIZE_MB * 1024 * 1024:
                    await self.send(json.dumps({"error": f"Datei zu groß! Max {MAX_MEDIA_SIZE_MB}MB"}))
                    return
                ext = mime_type.split("/")[-1]
                filename = get_valid_filename(f"msg_{sender.id}_{int(now().timestamp())}.{ext}")
                media_file = ContentFile(decoded_file, name=filename)
            except Exception as e:
                print(f"[WS] Failed to decode media: {e}")
                await self.send(json.dumps({"error": "Fehler beim Hochladen der Datei!"}))
                return

        # --- ADD COINS FOR TEXT ---
        if not is_gif and not has_media and "encrypted_message" in data and data["encrypted_message"].strip():
            profile = await get_user_profile(sender)
            await increment_coins(profile, 1)

        # --- CREATE MESSAGE ---
        try:
            message = await create_message(self.chat_id, sender, data, media_file)
            print(f"[DEBUG] Message created: {message}")
        except Exception as e:
            await self.send(json.dumps({"error": str(e)}))
            return

        # --- SEND MESSAGE TO GROUP ---
        payload = {
            "sender": escape(message.sender.username),
            "encrypted_message": escape(message.content),
            "media": message.media.url if message.media else None,
            "encrypted_key_recipient": escape(message.encrypted_key_recipient),
            "encrypted_key_sender": escape(message.encrypted_key_sender),
            "iv": escape(message.iv),
            "timestamp": str(message.timestamp)
        }

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat_message",
                "message": payload
            }
        )

    async def chat_message(self, event):
        await self.send(json.dumps(event["message"]))

# ----------------- DATABASE FUNCTIONS -----------------

@database_sync_to_async
def create_message(chat_id, user, data, media_file=None):
    chat = Chat.objects.get(id=chat_id)
    if user != chat.user1 and user != chat.user2:
        raise PermissionError("User not part of this chat")
    return Message.objects.create(
        chat=chat,
        sender=user,
        content=data.get("encrypted_message", ""),
        media=media_file,
        encrypted_key_recipient=data.get("encrypted_key_recipient", ""),
        encrypted_key_sender=data.get("encrypted_key_sender", ""),
        iv=data.get("iv", "")
    )

@database_sync_to_async
def count_text_messages_today_db(chat_id, user):
    # initial DB count (used only on connect)
    today = now().date()
    return Message.objects.filter(
        chat_id=chat_id,
        sender=user,
        media__isnull=True,
        timestamp__date=today
    ).count()

@database_sync_to_async
def count_media_today_db(chat_id, user):
    today = now().date()
    return Message.objects.filter(
        chat_id=chat_id,
        sender=user,
        timestamp__date=today
    ).exclude(media__isnull=True).count()

@database_sync_to_async
def get_user_profile(user):
    return Profile.objects.get(user=user)

@database_sync_to_async
def deduct_coins(profile, amount):
    with transaction.atomic():
        profile.coins -= amount
        profile.save()
        print(f"[DEBUG] Deducted {amount} coins from {profile.user.username}, now has {profile.coins}")

@database_sync_to_async
def increment_coins(profile, amount=1):
    with transaction.atomic():
        profile.coins += amount
        profile.save()
        print(f"[DEBUG] Added {amount} coins to {profile.user.username}, now has {profile.coins}")
