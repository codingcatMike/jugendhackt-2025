from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import escape
from django.core.files.base import ContentFile
from .models import Chat, Message
import json
import base64


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
            return

        # Only block text if already sent today
        if "encrypted_message" in data and data["encrypted_message"].strip():
            already_sent = await has_message_been_sent_today(self.chat_id, sender)
            if already_sent:
                await self.send(text_data=json.dumps({
                    "error": "Du kannst heute nur eine Nachricht senden!"
                }))
                return

        # Create the message (text or media)
        message = await self.create_message(sender, data)

        payload = {
            "sender": escape(message.sender.username),
            "encrypted_message": escape(message.content),
            "media": message.media.url if message.media else None,
            "encrypted_key_recipient": message.encrypted_key_recipient,
            "encrypted_key_sender": message.encrypted_key_sender,
            "iv": message.iv,
            "timestamp": str(message.timestamp)
        }

        # Broadcast to all in chat
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat_message",
                "message": payload
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    @database_sync_to_async
    def create_message(self, user, data):
        chat = Chat.objects.get(id=self.chat_id)
        if user != chat.user1 and user != chat.user2:
            raise PermissionError("User not part of this chat")

        media_file = None
        if "media" in data:
            try:
                format, imgstr = data["media"].split(";base64,")
                ext = format.split("/")[-1]
                media_file = ContentFile(base64.b64decode(imgstr), name=f"msg_{user.id}_{timezone.now().timestamp()}.{ext}")
            except Exception as e:
                print(f"[WS] Failed to decode media: {e}")
                media_file = None

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
def has_message_been_sent_today(chat_id, user):
    today = timezone.now().date()
    return Message.objects.filter(chat_id=chat_id, timestamp__date=today, sender=user).exists()
