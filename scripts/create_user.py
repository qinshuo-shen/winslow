"""
One-time account creation -- there is no self-serve signup (exactly 2
users are expected: the app owner + one friend). Run this once per
account, directly on whichever machine holds the real data/sessions.db
(local dev, or the VPS over `ssh`), same "run it directly against the file
that matters" precedent as generate_vapid_keys.py.
"""
import getpass

from procrastination_tool import auth


def main() -> None:
    username = input("Username: ").strip()
    if not username:
        print("Username can't be empty.")
        return
    if auth.get_user_by_username(username):
        print(f"{username!r} already exists -- refusing to overwrite.")
        return

    password = getpass.getpass("Password: ")
    if not password:
        print("Password can't be empty.")
        return
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords didn't match.")
        return

    user = auth.create_user(username, password)
    print(f"Created user {user.username!r} (id={user.id}).")


if __name__ == "__main__":
    main()
