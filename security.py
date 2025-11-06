from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


class Hasher:
    _ph = PasswordHasher()

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Generate a secure Argon2 hash for the given password."""
        return Hasher._ph.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify that the given plain password matches the stored Argon2 hash."""
        try:
            return Hasher._ph.verify(hashed_password, plain_password)
        except VerifyMismatchError:
            return False
