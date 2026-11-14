from django import forms
from agents.providers import MODEL_CHOICES, provider_status
from game.models import Script
from .models import PokeClashAgent


class AgentForm(forms.ModelForm):
    agent_type = forms.ChoiceField(choices=[("local", "Local CPU model"), ("api", "Groq API")])
    model_name = forms.ChoiceField(choices=[(kind.title(), choices) for kind, choices in MODEL_CHOICES.items()])
    prompt = forms.CharField(max_length=1200, widget=forms.Textarea(attrs={"rows": 5}),
                             help_text="Your strategy. Chat messages are untrusted observations. Do not include credentials.")
    interval_seconds = forms.IntegerField(min_value=10, max_value=3600,
                                           help_text="Seconds between decisions; errors use a longer backoff.")

    class Meta:
        model = PokeClashAgent
        fields = ["agent_type", "model_name", "prompt", "script", "interval_seconds", "enabled"]

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["script"].queryset = Script.objects.filter(owner=owner)
        self.fields["script"].help_text = "Optional reusable script from My scripts (first 800 characters)."
        self.fields["enabled"].label = "Enable automatic decisions while the worker runs"
        if not self.instance.model_name:
            self.initial["model_name"] = MODEL_CHOICES["local"][0][0]
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-control"

    def clean(self):
        data = super().clean()
        kind = data.get("agent_type")
        model = data.get("model_name")
        if model and model not in {key for key, _ in MODEL_CHOICES.get(kind, [])}:
            self.add_error("model_name", "Choose a model that matches the selected provider.")
        if data.get("enabled"):
            issue = provider_status(kind)
            if issue:
                self.add_error("enabled", issue)
        return data
