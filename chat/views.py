from django.shortcuts import render
from django.http import HttpResponse
from .models import *
# Create your views here.
def check(request):
    return HttpResponse("It works!")

def index(request):
    return render(request, 'index.html')

def test(request):
    return render(request, 'test.html')

def chat(request, id=None):
    chat = Chat.objects.get(id=id) if id else None
    messages = Message.objects.filter(chat=chat).order_by('-timestamp') if chat else None
    user_chats = Chat.objects.filter(user1=request.user) | Chat.objects.filter(user2=request.user)

    return render(request, 'chat.html', {"chat": chat, "messages": messages, "user_chats": user_chats})
