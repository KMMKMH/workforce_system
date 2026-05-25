import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from core.models import User


class Command(BaseCommand):
    help = "Create the high-priority CEO account from the terminal."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="CEO username.")
        parser.add_argument("--email", help="CEO email address.")
        parser.add_argument("--password", help="CEO password. Omit to enter it securely.")
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update the existing CEO account instead of failing when one already exists.",
        )

    def handle(self, *args, **options):
        existing_ceo = User.objects.filter(role="CEO").order_by("id").first()

        if existing_ceo and not options["update_existing"]:
            raise CommandError(
                "A CEO account already exists. Use --update-existing if you intentionally want to update it."
            )

        username = (options["username"] or input("CEO username: ")).strip()
        email = (options["email"] or input("CEO email: ")).strip()
        password = options["password"] or self._prompt_password()

        self._validate_identity(username, email, existing_ceo)
        self._validate_password(password, existing_ceo)

        with transaction.atomic():
            ceo = existing_ceo or User(role="CEO")
            ceo.username = username
            ceo.email = email
            ceo.role = "CEO"
            ceo.is_staff = False
            ceo.is_superuser = False
            ceo.set_password(password)
            ceo.save()

            ceo.profile.position = ceo.profile.position or "Chief Executive Officer"
            ceo.profile.department = ceo.profile.department or "Executive"
            ceo.profile.save(update_fields=["position", "department"])

        action = "Updated" if existing_ceo else "Created"
        self.stdout.write(self.style.SUCCESS(f"{action} CEO account: {ceo.username}"))

    def _prompt_password(self):
        password = getpass.getpass("CEO password: ")
        confirm_password = getpass.getpass("Confirm CEO password: ")

        if password != confirm_password:
            raise CommandError("Passwords do not match.")

        return password

    def _validate_identity(self, username, email, existing_ceo):
        if not username:
            raise CommandError("Username cannot be empty.")

        if not email:
            raise CommandError("Email cannot be empty.")

        try:
            validate_email(email)
        except ValidationError:
            raise CommandError("Please enter a valid email address.")

        users = User.objects.all()
        if existing_ceo:
            users = users.exclude(pk=existing_ceo.pk)

        if users.filter(username=username).exists():
            raise CommandError("That username is already taken.")

        if users.filter(email=email).exists():
            raise CommandError("That email address is already used.")

    def _validate_password(self, password, user):
        if not password:
            raise CommandError("Password cannot be empty.")

        try:
            validate_password(password, user=user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages))
