from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("schools", "0036_alter_notification_kind")]

    operations = [
        migrations.CreateModel(
            name="SuperadminSecurity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("totp_secret", models.CharField(blank=True, max_length=64)),
                ("mfa_enabled", models.BooleanField(default=False)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("recovery_code_hashes", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="superadmin_security", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
