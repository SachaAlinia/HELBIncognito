"""Advance game clocks without a connected browser. Assisted by OpenAI Codex."""
import time
from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections
from game.models import Game
from game.services import advance_game


class Command(BaseCommand):
    help = "Advance waiting and active games (one worker per deployment)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        try:
            while True:
                close_old_connections()
                for pk in Game.objects.exclude(status=Game.Status.FINISHED).values_list("pk", flat=True):
                    try:
                        advance_game(pk)
                    except OperationalError:
                        self.stderr.write("Database busy; the next tick will retry.")
                if options["once"]:
                    return
                time.sleep(1)
        except KeyboardInterrupt:
            return
