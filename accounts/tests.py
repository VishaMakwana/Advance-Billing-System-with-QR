import re
import time

from django.core import mail
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .forms import RegisterForm
from .models import Customer, Invoice, Profile


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

    def test_customer_registration_then_login_opens_customer_dashboard(self):
        response = self.client.post(
            reverse("home"),
            self.registration_data(role="CUSTOMER"),
            follow=True,
        )

        self.assertEqual(response.redirect_chain, [(reverse("login"), 302)])
        self.assertContains(response, "Your account is ready. Please log in.")
        user = User.objects.get(username="maya")
        self.assertEqual(user.profile.role, "CUSTOMER")

        response = self.client.post(
            reverse("login"),
            {"username": "maya", "password": "S9!ample-Long-Password"},
            follow=True,
        )

        self.assertEqual(response.redirect_chain, [(reverse("customer_dashboard"), 302)])
        self.assertContains(response, "Customer dashboard")
        self.assertContains(response, "maya@example.com")

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

    def request_code(self, email=None):
        response = self.client.post(
            reverse("password_reset"),
            {"email": email or self.user.email},
            follow=True,
        )
        return response

    def test_password_reset_otp_sets_a_new_password(self):
        response = self.request_code()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "6-digit code")
        self.assertContains(response, "Resend code")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Your Billwise password reset code", mail.outbox[0].subject)

        code = re.search(r"code is (\d{6})", mail.outbox[0].body).group(1)
        response = self.client.post(
            reverse("password_reset_verify"),
            {"otp": code},
            follow=True,
        )
        self.assertContains(response, "Create a new password")
        self.assertContains(response, "New password")
        self.assertContains(response, "Confirm new password")

        response = self.client.post(
            reverse("password_reset_new_password"),
            {
                "new_password1": "New-S9!ample-Password",
                "new_password2": "New-S9!ample-Password",
            },
            follow=True,
        )

        self.assertContains(response, "Your password was reset. Please sign in.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-S9!ample-Password"))

    def test_unknown_email_does_not_disclose_account_existence(self):
        response = self.request_code(email="unknown@example.com")

        self.assertContains(response, "6-digit code")
        self.assertContains(response, "If an account exists for that email")
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_otp_is_limited_and_expires(self):
        self.request_code()
        for _ in range(5):
            response = self.client.post(
                reverse("password_reset_verify"),
                {"otp": "abcdef"},
                follow=True,
            )

        self.assertContains(response, "Too many incorrect attempts")
        self.assertNotIn("password_reset_otp", self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("S9!ample-Long-Password"))

    def test_resend_obeys_cooldown_and_sends_a_fresh_code(self):
        self.request_code()
        first_code = re.search(r"code is (\d{6})", mail.outbox[0].body).group(1)

        response = self.client.post(reverse("password_reset_resend"), follow=True)
        self.assertContains(response, "Please wait")
        self.assertEqual(len(mail.outbox), 1)

        session = self.client.session
        state = session["password_reset_otp"]
        state["sent_at"] = time.time() - 61
        session["password_reset_otp"] = state
        session.save()

        response = self.client.post(reverse("password_reset_resend"), follow=True)
        self.assertContains(response, "Resend code")
        self.assertEqual(len(mail.outbox), 2)
        second_code = re.search(r"code is (\d{6})", mail.outbox[1].body).group(1)
        self.assertNotEqual(first_code, second_code)

    def test_password_confirmation_must_match(self):
        self.request_code()
        code = re.search(r"code is (\d{6})", mail.outbox[0].body).group(1)
        self.client.post(reverse("password_reset_verify"), {"otp": code})

        response = self.client.post(
            reverse("password_reset_new_password"),
            {
                "new_password1": "New-S9!ample-Password",
                "new_password2": "Different-S9!ample-Password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The two password fields didn’t match")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("S9!ample-Long-Password"))


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

    def test_distributor_can_update_profile_fields(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("distributor_profile"),
            {
                "first_name": "Asha",
                "last_name": "Desai",
                "username": "asha",
                "email": "asha@example.com",
            },
        )

        self.assertRedirects(response, reverse("distributor_profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Asha")
        self.assertEqual(self.user.last_name, "Desai")
        self.assertEqual(self.user.username, "asha")
        self.assertEqual(self.user.email, "asha@example.com")

    def test_distributor_profile_rejects_invalid_or_duplicate_email(self):
        User.objects.create_user(username="other", email="used@example.com")
        self.client.force_login(self.user)
        original_email = self.user.email

        for email in ("not-an-email", "USED@example.com"):
            response = self.client.post(
                reverse("distributor_profile"),
                {
                    "first_name": "Asha",
                    "last_name": "Desai",
                    "username": "asha",
                    "email": email,
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("email", response.context["form"].errors)
            self.user.refresh_from_db()
            self.assertEqual(self.user.email, original_email)

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


class CustomerModelTests(TestCase):
    def test_customer_contact_details_are_saved_for_their_distributor(self):
        distributor = User.objects.create_user(username="customer-owner")

        customer = Customer.objects.create(
            user=distributor,
            name="Northwind Store",
            email="billing@northwind.example",
            phone="+1 555 0100",
            address="42 Market Street",
        )

        saved_customer = Customer.objects.get(pk=customer.pk)
        self.assertEqual(saved_customer.user, distributor)
        self.assertEqual(saved_customer.name, "Northwind Store")
        self.assertEqual(saved_customer.email, "billing@northwind.example")
        self.assertEqual(saved_customer.phone, "+1 555 0100")
        self.assertEqual(saved_customer.address, "42 Market Street")


class CustomerCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="customer-distributor")
        self.client.force_login(self.user)

    def test_customer_form_saves_for_current_user_and_shows_success_alert(self):
        response = self.client.post(
            reverse("customer_create"),
            {
                "name": "Northwind Store",
                "email": "billing@northwind.example",
                "phone": "+1 555 0100",
                "address": "42 Market Street",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse("customer_create"), 302)])
        self.assertContains(response, "Customer added successfully.")
        customer = Customer.objects.get(name="Northwind Store")
        self.assertEqual(customer.user, self.user)
        self.assertEqual(customer.email, "billing@northwind.example")
        self.assertEqual(customer.phone, "+1 555 0100")
        self.assertEqual(customer.address, "42 Market Street")

    def test_customer_form_rejects_missing_name_and_invalid_email(self):
        response = self.client.post(
            reverse("customer_create"),
            {
                "name": "",
                "email": "not-an-email",
                "phone": "555-0100",
                "address": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertIn("email", response.context["form"].errors)
        self.assertContains(response, "Enter a valid email address.")
        self.assertEqual(Customer.objects.count(), 0)


class CustomerDashboardAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="customer-user")
        Profile.objects.create(user=self.user, role="CUSTOMER")
        self.client.force_login(self.user)

    def test_customer_cannot_open_distributor_invoice_pages(self):
        response = self.client.get(reverse("invoices"))

        self.assertRedirects(response, reverse("customer_dashboard"))
        response = self.client.get(reverse("invoice_create"))
        self.assertRedirects(response, reverse("customer_dashboard"))

    def test_customer_dashboard_shows_customer_account(self):
        response = self.client.get(reverse("customer_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer account")
