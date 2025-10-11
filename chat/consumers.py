from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
import json
from .models import Chat, Message

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]
        self.group_name = f"chat_{self.chat_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        sender = self.scope["user"]

        if sender.is_authenticated:
            message = await self.create_message(sender, data)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat_message",
                    "message": {
                        "sender": sender.username,
                        "encrypted_message": message.content,
                        "encrypted_key": message.encrypted_key,
                        "iv": message.iv,
                        "timestamp": message.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    }
                }
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    @database_sync_to_async
    def create_message(self, user, data):
        chat = Chat.objects.get(id=self.chat_id)
        if user != chat.user1 and user != chat.user2:
            raise PermissionError("User not part of this chat")
        return Message.objects.create(
            chat=chat,
            sender=user,
            content=data["encrypted_message"],
            encrypted_key=data["encrypted_key"],
            iv=data["iv"]
        )
