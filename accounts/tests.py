import re

from django.core import mail
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .forms import RegisterForm
from .models import Invoice, Profile


class RegisterFormTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            "first_name": "Maya",
            "last_name": "Patel",
            "username": "maya",
            "email": "maya@example.com",
            "role": "DISTRIBUTOR",
            "password": "S9!ample-Long-Password",
            "confirm_password": "S9!ample-Long-Password",
        }
        data.update(overrides)
        return data

    def test_registration_saves_user_and_profile_and_shows_login_success(self):
        response = self.client.post(reverse("home"), self.registration_data(), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse("login"), 302)])
        self.assertContains(response, "Your account is ready. Please log in.")
        user = User.objects.get(username="maya")
        self.assertTrue(user.check_password("S9!ample-Long-Password"))
        self.assertEqual(user.email, "maya@example.com")
        self.assertEqual(user.profile.role, Profile.ROLE_CHOICES[1][0])

    def test_registration_rejects_bad_email_short_password_and_mismatch(self):
        form = RegisterForm(
            self.registration_data(
                email="not-an-email",
                password="short",
                confirm_password="different",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        self.assertIn("password", form.errors)
        self.assertIn("confirm_password", form.errors)
        self.assertEqual(User.objects.count(), 0)

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        User.objects.create_user(username="existing", email="maya@example.com")
        form = RegisterForm(self.registration_data(email="MAYA@EXAMPLE.COM"))

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_public_registration_cannot_create_an_admin(self):
        form = RegisterForm(self.registration_data(role="ADMIN"))

        self.assertFalse(form.is_valid())
        self.assertIn("role", form.errors)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="maya",
            email="maya@example.com",
            password="S9!ample-Long-Password",
        )

    def test_login_has_forgot_password_link(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, reverse("password_reset"))
        self.assertLess(
            response.content.index(b"Create an account"),
            response.content.index(b"Forgot password?"),
        )

    def test_password_reset_email_link_changes_password(self):
        response = self.client.post(
            reverse("password_reset"),
            {"email": self.user.email},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check your inbox")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset your Billwise password", mail.outbox[0].subject)

        reset_path = re.search(r"http://testserver(/reset/\S+)", mail.outbox[0].body).group(1)
        reset_response = self.client.get(reset_path, follow=True)
        self.assertContains(reset_response, "Create a new password")
        self.assertContains(reset_response, "New password")
        self.assertContains(reset_response, "Confirm new password")
        confirm_path = reset_response.request["PATH_INFO"]

        response = self.client.post(
            confirm_path,
            {
                "new_password1": "New-S9!ample-Password",
                "new_password2": "New-S9!ample-Password",
            },
            follow=True,
        )

        self.assertContains(response, "Password updated")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-S9!ample-Password"))

    def test_unknown_email_does_not_disclose_account_existence(self):
        response = self.client.post(
            reverse("password_reset"),
            {"email": "unknown@example.com"},
            follow=True,
        )

        self.assertContains(response, "Check your inbox")
        self.assertEqual(len(mail.outbox), 0)


class DistributorAndInvoiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="distributor",
            email="distributor@example.com",
            password="S9!ample-Long-Password",
            first_name="Ravi",
            last_name="Shah",
        )
        Profile.objects.create(user=self.user, role="DISTRIBUTOR")

    def test_distributor_profile_shows_account_details(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("distributor_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Shah")
        self.assertContains(response, "distributor@example.com")
        self.assertContains(response, "Distributor")

    def test_dashboard_shows_recent_invoice_and_navigation(self):
        Invoice.objects.create(
            user=self.user,
            customer_name="Northwind Store",
            description="Monthly supplies",
            amount="125.50",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("distributor_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invoices created")
        self.assertContains(response, "Northwind Store")
        self.assertContains(response, "Create invoice")
        self.assertContains(response, "My profile")

    def test_invoice_is_saved_for_current_distributor_and_has_qr_payload(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("invoice_create"),
            {
                "customer_name": "Northwind Store",
                "customer_email": "billing@northwind.example",
                "description": "Monthly supplies",
                "amount": "125.50",
                "due_date": "2026-12-15",
            },
        )

        self.assertRedirects(response, reverse("invoices"))
        invoice = Invoice.objects.get(user=self.user)
        self.assertIn("Northwind Store", invoice.qr_payload)
        self.assertIn("125.50", invoice.qr_payload)
        self.assertContains(self.client.get(reverse("invoices")), "Northwind Store")

    def test_invoice_form_rejects_invalid_email_and_nonpositive_amount(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("invoice_create"),
            {
                "customer_name": "Northwind Store",
                "customer_email": "invalid-email",
                "description": "Monthly supplies",
                "amount": "0",
                "due_date": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address.")
        self.assertIn("customer_email", response.context["form"].errors)
        self.assertIn("amount", response.context["form"].errors)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_distributor_only_sees_their_own_invoices(self):
        other_user = User.objects.create_user(username="another", password="S9!ample-Long-Password")
        Invoice.objects.create(
            user=other_user,
            customer_name="Private Customer",
            description="Private bill",
            amount="10.00",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("invoices"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private Customer")
