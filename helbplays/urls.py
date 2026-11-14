from django.urls import path
from . import views

urlpatterns = [
    path("", views.chat, name="helbplays-chat"),
    path("feed/", views.feed, name="helbplays-feed"),
    path("send/", views.send, name="helbplays-send"),
    path("agent/", views.configure_agent, name="helbplays-agent"),
    path("agent/run/", views.run_agent, name="helbplays-agent-run"),
]
