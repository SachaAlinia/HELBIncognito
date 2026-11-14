from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import helbplays.models


class Migration(migrations.Migration):
    dependencies = [("helbplays", "0001_initial"), ("game", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="PokeClashAgent", fields=[
            ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("enabled", models.BooleanField(default=False)),
            ("run_requested", models.BooleanField(default=False)),
            ("agent_type", models.CharField(default="local", max_length=10)),
            ("model_name", models.CharField(blank=True, max_length=100)),
            ("prompt", models.TextField(default=helbplays.models.DEFAULT_PROMPT)),
            ("interval_seconds", models.PositiveIntegerField(default=30)),
            ("next_run_at", models.DateTimeField(blank=True, null=True)),
            ("last_run_at", models.DateTimeField(blank=True, null=True)),
            ("last_result", models.CharField(blank=True, max_length=240)),
            ("failure_count", models.PositiveIntegerField(default=0)),
            ("revision", models.PositiveIntegerField(default=0)),
            ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pokeclash_agent", to=settings.AUTH_USER_MODEL)),
            ("script", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="game.script")),
        ]),
        migrations.AddField(model_name="gatewaystate", name="lease_token", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="gatewaystate", name="lease_expires_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="gatewaystate", name="active_agent", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="helbplays.pokeclashagent")),
    ]
