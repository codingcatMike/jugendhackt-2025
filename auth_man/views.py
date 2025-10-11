from django.shortcuts import render, redirect
from .forms import SignUpForm
from django.contrib.auth import logout
# Create your views here.
def signup(request):
    form = SignUpForm()
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, 'registration/signup.html', {"form": form, "success": True})
    return render(request, 'registration/signup.html', {"form": form})

def logoutn(request):
    logout(request)
    return redirect('login')