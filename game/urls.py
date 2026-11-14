from django.urls import path

from . import views

urlpatterns = [
    # Assisted by OpenAI Codex: private script library and per-player configuration.
    path("scripts/", views.script_list, name="script-list"),
    path("scripts/new/", views.script_edit, name="script-create"),
    path("scripts/<int:script_id>/edit/", views.script_edit, name="script-edit"),
    path("scripts/<int:script_id>/delete/", views.script_delete, name="script-delete"),
    path("game/<int:game_id>/agent/", views.configure_agent, name="game-agent"),
    path("game/<int:game_id>/state/", views.state, name="game-state"),
    path("game/<int:game_id>/action/", views.action, name="game-action"),
    path("", views.home, name="game-home"),
    path("game/new/", views.create_game, name="game-create"),
    path("game/<int:game_id>/", views.game_detail, name="game-detail"),
    path("game/<int:game_id>/join/", views.join_game, name="game-join"),
]
