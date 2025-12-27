from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils.html import escape
from django.utils.text import get_valid_filename
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.timezone import now
from datetime import date
import json
import base64

from .models import Chat, Message
from auth_man.models import Profile

# ------------------- CONFIG -------------------
MAX_TEXT_PER_DAY = 100
MAX_MEDIA_PER_DAY = 100

ALLOWED_MEDIA_TYPES = ["image/png", "image/jpeg", "image/gif"]
MAX_MEDIA_SIZE_MB = 5
# ----------------------------------------------


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]
        self.group_name = f"chat_{self.chat_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        print("Received message:", text_data)
        data = json.loads(text_data)
        sender = self.scope["user"]

        if not sender.is_authenticated:
            await self.send(json.dumps({"error": "Nicht angemeldet!"}))
            return

        encrypted_message = data.get("encrypted_message", "").strip()
        has_media = bool(data.get("media"))
        is_gif = data.get("media_type") == "gif"

        # ---------------- DETERMINE MESSAGE TYPE ----------------
        if is_gif:
            msg_type = Message.GIF
        elif has_media:
            msg_type = Message.MEDIA
        elif encrypted_message:
            msg_type = Message.TEXT
        else:
            await self.send(json.dumps({"error": "Leere Nachricht!"}))
            return

        # ---------------- DAILY LIMIT CHECK ----------------
        if msg_type == Message.TEXT:
            await self._check_daily_limit(sender, msg_type, MAX_TEXT_PER_DAY)

        if msg_type in (Message.MEDIA, Message.GIF):
            await self._check_daily_limit(sender, msg_type, MAX_MEDIA_PER_DAY)



        # ---------------- GIF COIN CHECK ----------------
        profile = await get_user_profile(sender)

        if msg_type == Message.GIF:
            price = int(data.get("price", 0))
            if profile.coins < price:
                await self.send(json.dumps({"error": "Nicht genügend Coins für dieses GIF!"}))
                return

        # ---------------- MEDIA DECODING ----------------
        media_file = None

        if has_media:
            try:
                header, encoded = data["media"].split(";base64,")
                mime_type = header.split(":")[1]

                if mime_type not in ALLOWED_MEDIA_TYPES:
                    await self.send(json.dumps({"error": "Nicht erlaubter Medientyp!"}))
                    return

                decoded = base64.b64decode(encoded)

                if len(decoded) > MAX_MEDIA_SIZE_MB * 1024 * 1024:
                    await self.send(json.dumps({"error": f"Datei zu groß (max {MAX_MEDIA_SIZE_MB}MB)"}))
                    return

                ext = mime_type.split("/")[-1]
                filename = get_valid_filename(
                    f"msg_{sender.id}_{int(now().timestamp())}.{ext}"
                )

                media_file = ContentFile(decoded, name=filename)

            except Exception:
                await self.send(json.dumps({"error": "Fehler beim Hochladen der Datei!"}))
                return

        # ---------------- CREATE MESSAGE (ATOMIC) ----------------
        try:
            message = await create_message_atomic(
                chat_id=self.chat_id,
                sender=sender,
                data=data,
                media_file=media_file,
                msg_type=msg_type
            )
        except ValueError as e:
            await self.send(json.dumps({"error": str(e)}))
            return

        # ---------------- BROADCAST ----------------
        payload = {
            "sender": escape(message.sender.username),
            "encrypted_message": escape(message.content),
            "media": message.media.url if message.media else None,
            "encrypted_key_recipient": escape(message.encrypted_key_recipient),
            "encrypted_key_sender": escape(message.encrypted_key_sender),
            "iv": escape(message.iv),
            "timestamp": str(message.timestamp),
        }

        await self.channel_layer.group_send(
            self.group_name,
            {"type": "chat_message", "message": payload}
        )

    async def chat_message(self, event):
        await self.send(json.dumps(event["message"]))

    # ---------------- HELPERS ----------------

    async def _check_daily_limit(self, user, msg_type, limit):
        count = await count_messages_today(self.chat_id, user, msg_type)
        print(f"User {user.username} has sent {count}/{limit} {msg_type} messages today.")
        if count >= limit:
            print(f"User {user.username} reached daily limit for {msg_type} messages.")
            await self.send(json.dumps({"error": "Tageslimit erreicht!"}))
            raise ValueError(
                f"Tageslimit erreicht ({limit} {msg_type}-Nachrichten)"
            )


# ================= DATABASE FUNCTIONS =================

@database_sync_to_async
def count_messages_today(chat_id, user, msg_type):
    today = now().date()
    return Message.objects.filter(
        chat_id=chat_id,
        sender=user,
        message_type=msg_type,
        timestamp__date=today
    ).count()


@database_sync_to_async
def get_user_profile(user):
    return Profile.objects.select_for_update().get(user=user)


@database_sync_to_async
def create_message_atomic(chat_id, sender, data, media_file, msg_type):
    with transaction.atomic():
        chat = Chat.objects.select_for_update().get(id=chat_id)

        if sender not in (chat.user1, chat.user2):
            raise ValueError("User not in this chat")

        profile = Profile.objects.select_for_update().get(user=sender)

        # GIF cost
        if msg_type == Message.GIF:
            price = int(data.get("price", 0))
            if profile.coins < price:
                raise ValueError("Nicht genügend Coins")
            profile.coins -= price

        # Text reward
        if msg_type == Message.TEXT:
            profile.coins += 1

        profile.save()
        print("Creating message...")
        return Message.objects.create(
            chat=chat,
            sender=sender,
            content=data.get("encrypted_message", ""),
            media=media_file,
            message_type=msg_type,
            encrypted_key_recipient=data.get("encrypted_key_recipient", ""),
            encrypted_key_sender=data.get("encrypted_key_sender", ""),
            iv=data.get("iv", ""),
        )
