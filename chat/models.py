from django.db import models
from django.contrib.auth.models import User

class Chat(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats_initiated')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats_received')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat between {self.user1.username} and {self.user2.username}"


class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(blank=True)  # AES-encrypted text
    media = models.FileField(upload_to='chat_media/', blank=True, null=True)  # für Bilder/GIFs
    encrypted_key_recipient = models.TextField(blank=True)  
    encrypted_key_sender = models.TextField(blank=True)  
    iv = models.TextField(blank=True)  
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.media:
            return f"Media message from {self.sender.username} at {self.timestamp}"
        return f"Text message from {self.sender.username} at {self.timestamp}"


class GIF(models.Model):
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='gifs/')
    price = models.IntegerField(default=0)  # will save in MEDIA_ROOT/gifs/

    def __str__(self):
        return self.name# Create your models here.


    