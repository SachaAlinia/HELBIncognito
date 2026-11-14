from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("game", "0001_initial")]

    operations = [
        migrations.AddField(model_name="gameplayer", name="ai_config_revision", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="gameplayer", name="ai_last_error", field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name="gameplayer", name="ai_last_run_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="gameplayer", name="ai_next_run_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="gameplayer", name="ai_failure_count", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="gameplayer", name="ai_lease_token", field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(model_name="gameplayer", name="ai_lease_until", field=models.DateTimeField(blank=True, null=True)),
    ]
