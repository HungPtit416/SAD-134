from django.contrib.auth.models import User


def seed() -> None:
    users = [
        ("user1@gmail.com", "User One", "123456"),
        ("user2@gmail.com", "User Two", "123456"),
    ]

    for email, full_name, password in users:
        email = email.lower().strip()
        user, created = User.objects.get_or_create(username=email, defaults={"email": email, "first_name": full_name})
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        else:
            # Keep password as provided for demo if user has no usable password
            if not user.has_usable_password():
                user.set_password(password)
                user.save(update_fields=["password"])
            if user.email != email or user.first_name != full_name:
                user.email = email
                user.first_name = full_name
                user.save(update_fields=["email", "first_name"])

