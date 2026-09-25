import unittest

from pydantic import ValidationError

from app.api.auth import LoginRequest, RegisterRequest


class AuthRequestValidationTests(unittest.TestCase):
    """Guard the EmailStr dependency so registration/login validation stays importable and enforced."""

    def test_valid_registration_is_accepted(self):
        item = RegisterRequest(
            email="owner@example.com",
            full_name="Owner",
            password="a-strong-password",
            workspace_name="RSS Workspace",
        )
        self.assertEqual(item.email, "owner@example.com")

    def test_invalid_registration_email_is_rejected(self):
        with self.assertRaises(ValidationError):
            RegisterRequest(
                email="not-an-email",
                full_name="Owner",
                password="a-strong-password",
                workspace_name="RSS Workspace",
            )

    def test_short_registration_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            RegisterRequest(
                email="owner@example.com",
                full_name="Owner",
                password="short",
                workspace_name="RSS Workspace",
            )

    def test_login_requires_a_valid_email(self):
        with self.assertRaises(ValidationError):
            LoginRequest(email="bad", password="any-password")


if __name__ == "__main__":
    unittest.main()
