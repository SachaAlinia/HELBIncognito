"""Profile updates and image processing. Assisted by OpenAI Codex."""
from django.db import transaction
from PIL import Image


@transaction.atomic
def update_profile(user_form, profile_form):
    user_form.save()
    profile = profile_form.save()
    # Never open the avatar when only account details have changed.
    if "image" in profile_form.changed_data and profile.image:
        with Image.open(profile.image.path) as image:
            if image.height > 300 or image.width > 300:
                image.thumbnail((300, 300))
                image.save(profile.image.path)
    return profile
