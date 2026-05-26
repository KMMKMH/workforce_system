from django.db import migrations, models
from django.utils import timezone


def mark_existing_chats_seen(apps, schema_editor):
    ChatParticipant = apps.get_model("core", "ChatParticipant")
    ChatParticipant.objects.filter(last_seen_at__isnull=True).update(last_seen_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_leaverequest_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatparticipant",
            name="last_seen_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_chats_seen, migrations.RunPython.noop),
    ]
