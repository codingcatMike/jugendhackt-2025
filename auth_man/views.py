from django.shortcuts import render
from .forms import SignUpForm
# Create your views here.
def signup(request):
    form = SignUpForm()
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, 'signup.html', {"form": form, "success": True})
    return render(request, 'registration/signup.html', {"form": form})