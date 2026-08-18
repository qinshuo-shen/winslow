"""
Password reset for someone who's locked out -- the "forgot password" path.
Unlike procrastination_tool.auth.change_password() (the self-service
in-app flow, for someone who still remembers their current password),
this doesn't check the old password at all -- it can't, that's the whole
point. Only the app owner can run this (shell access to whichever machine
holds the real data/sessions.db).

Run this, tell the locked-out person their new (temporary) password over
a channel you trust, then have them open the app and use "Change
password" themselves right away -- that puts it back to being something
only they know, same as right after scripts/create_user.py first created
their account.
"""
import getpass

from procrastination_tool import auth


def main() -> None:
    username = input("Username to reset: ").strip()
    user = auth.get_user_by_username(username)
    if user is None:
        print(f"No account named {username!r}.")
        return

    password = getpass.getpass("New (temporary) password: ")
    if not password:
        print("Password can't be empty.")
        return
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        print("Passwords didn't match.")
        return

    auth.set_password(user.id, password)
    print(f"Password reset for {user.username!r}. Every device that was signed in got logged out.")
    print("Tell them the new password over a channel you trust, and have them")
    print("change it themselves (Change password, in the app) as soon as they're back in.")


if __name__ == "__main__":
    main()
