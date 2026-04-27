from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update a staff user (Django auth User)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--full-name", default="")
        parser.add_argument("--superuser", action="store_true")

    def handle(self, *args, **options):
        email = str(options["email"]).lower().strip()
        password = str(options["password"])
        full_name = str(options.get("full_name") or "")
        is_superuser = bool(options.get("superuser"))

        user, _created = User.objects.get_or_create(username=email, defaults={"email": email})
        user.email = email
        user.first_name = full_name
        user.is_staff = True
        user.is_superuser = is_superuser
        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(f"OK staff user: {email} (superuser={is_superuser})"))

