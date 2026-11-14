from django import forms

from .models import Game, GamePlayer, Script


class GameForm(forms.ModelForm):
    """Form used to create a new game with its settings."""

    class Meta:
        model = Game
        fields = [
            "name",
            "short_description",
            "total_rounds",
            "round_duration_seconds",
            "message_cooldown_seconds",
            "max_message_length",
            "min_players",
        ]


# Assisted by OpenAI Codex: reusable prompts and owner-scoped agent configuration.
class ScriptForm(forms.ModelForm):
    class Meta:
        model = Script
        fields = ["title", "content"]
        widgets = {"content": forms.Textarea(attrs={"rows": 7})}


class AgentConfigForm(forms.ModelForm):
    script = forms.ModelChoiceField(
        queryset=Script.objects.none(), required=False,
        label="Reusable script (prepended to the prompt)",
    )
    ai_model_name = forms.ChoiceField(label="Model", required=False)
    ai_prompt = forms.CharField(label="Prompt", required=False, max_length=2000,
                               widget=forms.Textarea(attrs={"rows": 5}))

    class Meta:
        model = GamePlayer
        fields = ["ai_enabled", "ai_agent_type", "ai_model_name", "ai_prompt"]
        labels = {"ai_enabled": "Enable agent", "ai_agent_type": "Provider", "ai_prompt": "Prompt"}
        widgets = {"ai_prompt": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, user, **kwargs):
        from agents.providers import MODEL_CHOICES, provider_status

        super().__init__(*args, **kwargs)
        self.fields["script"].queryset = Script.objects.filter(owner=user).order_by("title", "pk")
        self.model_choices = MODEL_CHOICES
        self.provider_readiness = {key: provider_status(key) for key in MODEL_CHOICES}
        agent_type = self.data.get("ai_agent_type") if self.is_bound else self.instance.ai_agent_type
        self.fields["ai_model_name"].choices = [("", "Select a model")] + list(MODEL_CHOICES.get(agent_type, []))
        self.fields["ai_prompt"].help_text = "Maximum 2,000 characters including any selected script. The script is copied when you save; later script edits do not change the running agent."

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("ai_enabled") and not cleaned.get("ai_model_name"):
            self.add_error("ai_model_name", "Select a model before enabling the agent.")
        script = cleaned.get("script")
        if script:
            cleaned["ai_prompt"] = "\n\n".join(filter(None, [script.content.strip(), cleaned.get("ai_prompt", "").strip()]))
        if len(cleaned.get("ai_prompt", "")) > 2000:
            self.add_error("ai_prompt", "The prompt including the selected script must be at most 2,000 characters.")
        return cleaned
