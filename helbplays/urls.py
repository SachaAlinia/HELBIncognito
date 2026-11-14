from django.urls import path
from . import views

urlpatterns = [
    path("", views.chat, name="helbplays-chat"),
    path("feed/", views.feed, name="helbplays-feed"),
    path("send/", views.send, name="helbplays-send"),
]
