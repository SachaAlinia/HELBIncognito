from django.contrib import admin

from .models import Game, GamePlayer, Message, Round, RoundAlias, Script, Vote

admin.site.register(Game)
admin.site.register(GamePlayer)
admin.site.register(Round)
admin.site.register(RoundAlias)
admin.site.register(Message)
admin.site.register(Vote)
admin.site.register(Script)