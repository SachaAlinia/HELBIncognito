from django.urls import path

from . import views

urlpatterns = [
    path("game/<int:game_id>/state/", views.state, name="game-state"),
    path("game/<int:game_id>/action/", views.action, name="game-action"),
    path("", views.home, name="game-home"),
    path("game/new/", views.create_game, name="game-create"),
    path("game/<int:game_id>/", views.game_detail, name="game-detail"),
    path("game/<int:game_id>/join/", views.join_game, name="game-join"),
]
