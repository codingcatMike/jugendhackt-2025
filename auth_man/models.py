from django.db import models

# Create your models here.
from django.db import models
#imort the User model from django
from django.contrib.auth.models import User
# Create your models here.
class Profile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    coins = models.IntegerField(default=25)
    nickname = models.CharField(max_length=15, default="")
    profile_pic = models.ImageField(upload_to='profile_pics/', default='default.jpg')
    public_key = models.TextField(default="")
    def __str__(self):
        return self.user.username

    