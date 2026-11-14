"""Run explicitly enabled agents outside HTTP requests."""
import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections
from agents.worker import run_incognito_agents


class Command(BaseCommand):
    help = "Run opted-in agents. --dry-run checks eligibility without model calls or writes."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--incognito-only", action="store_true")

    def handle(self, *args, **options):
        try:
            while True:
                close_old_connections()
                try:
                    count = run_incognito_agents(dry_run=options["dry_run"])
                    if options["dry_run"]:
                        self.stdout.write(f"Incognito: {count} eligible agent(s); no actions performed.")
                    elif not options["incognito_only"]:
                        from helbplays.services import run_pokeclash_agents
                        run_pokeclash_agents(limit=10)
                except OperationalError:
                    self.stderr.write("Database busy; agents will retry on the next tick.")
                if options["once"] or options["dry_run"]:
                    return
                time.sleep(2)
        except KeyboardInterrupt:
            return
