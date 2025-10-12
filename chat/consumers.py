from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import escape
from django.core.files.base import ContentFile
from django.db import transaction
from .models import Chat, Message
from auth_man.models import Profile  # Profile für Coins
import json
import base64

# ------------------- CONFIG -------------------
# Anzahl der maximalen Nachrichten pro Tag pro Nutzer
MAX_MESSAGES_PER_DAY = 5
# ----------------------------------------------


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]
        self.group_name = f"chat_{self.chat_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"[WS] Connected to {self.group_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print(f"[WS] Disconnected from {self.group_name}")

    async def receive(self, text_data):
        data = json.loads(text_data)
        sender = self.scope["user"]

        if not sender.is_authenticated:
            await self.send(text_data=json.dumps({
                "error": "Nicht angemeldet!"
            }))
            return

        # Nachrichtenlimit prüfen
        if "encrypted_message" in data and data["encrypted_message"].strip():
            messages_sent_today = await count_messages_today(self.chat_id, sender)
            if messages_sent_today >= MAX_MESSAGES_PER_DAY:
                await self.send(text_data=json.dumps({
                    "error": f"Du kannst heute nur {MAX_MESSAGES_PER_DAY} Nachricht(en) senden!"
                }))
                return

        # GIF-Check: Coins prüfen
        is_gif = data.get("media_type") == "gif"
        if is_gif:
            price = int(data.get("price", 0))
            profile = await get_user_profile(sender)
            if profile.coins < price:
                await self.send(text_data=json.dumps({
                    "error": "Nicht genügend Coins für dieses GIF!"
                }))
                return
            await deduct_coins(profile, price)

        # Media file decoding
        media_file = None
        if "media" in data:
            try:
                format, imgstr = data["media"].split(";base64,")
                ext = format.split("/")[-1]
                media_file = ContentFile(
                    base64.b64decode(imgstr),
                    name=f"msg_{sender.id}_{timezone.now().timestamp()}.{ext}"
                )
            except Exception as e:
                print(f"[WS] Failed to decode media: {e}")
                media_file = None

        # Increment coins for normal messages (not GIFs)
        if not is_gif and ("encrypted_message" in data and data["encrypted_message"].strip()):
            profile = await get_user_profile(sender)
            await increment_coins(profile, 1)

        # Create message
        try:
            message = await create_message(self.chat_id, sender, data, media_file)
        except Exception as e:
            await self.send(text_data=json.dumps({
                "error": str(e)
            }))
            return

        payload = {
            "sender": escape(message.sender.username),
            "encrypted_message": escape(message.content),
            "media": message.media.url if message.media else None,
            "encrypted_key_recipient": message.encrypted_key_recipient,
            "encrypted_key_sender": message.encrypted_key_sender,
            "iv": message.iv,
            "timestamp": str(message.timestamp)
        }

        # Broadcast an alle im Chat
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat_message",
                "message": payload
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))


# ----------------- Database functions -----------------

@database_sync_to_async
def create_message(chat_id, user, data, media_file=None):
    chat = Chat.objects.get(id=chat_id)
    if user != chat.user1 and user != chat.user2:
        raise PermissionError("User not part of this chat")
    if chat.activated is False:
        raise PermissionError("Chat not activated yet")

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
def count_messages_today(chat_id, user):
    today = timezone.now().date()
    return Message.objects.filter(chat_id=chat_id, timestamp__date=today, sender=user).count()


@database_sync_to_async
def get_user_profile(user):
    return Profile.objects.get(user=user)


@database_sync_to_async
def deduct_coins(profile, amount):
    with transaction.atomic():
        profile.coins -= amount
        profile.save()


@database_sync_to_async
def increment_coins(profile, amount=1):
    with transaction.atomic():
        profile.coins += amount
        profile.save()
