import secrets
import time

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.crypto import constant_time_compare, salted_hmac

from .forms import (
    InvoiceForm,
    PasswordResetOTPForm,
    PasswordResetRequestForm,
    ProfileForm,
    RegisterForm,
)
from .models import Invoice, Profile

PASSWORD_RESET_OTP_SESSION_KEY = "password_reset_otp"
PASSWORD_RESET_USER_SESSION_KEY = "password_reset_user_id"
OTP_TTL_SECONDS = 600
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
OTP_MAX_SENDS = 4


def register(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password"])
            user.save()
            Profile.objects.create(user=user, role=form.cleaned_data["role"])

        messages.success(request, "Your account is ready. Please log in.")
        return redirect("login")

    return render(request, "Accounts/register.html", {"form": form})


def custom_login(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect_by_role(user)
        messages.error(request, "Invalid username or password.")

    return render(request, "Accounts/login.html")


def password_reset_request(request):
    if request.method == "GET" and request.GET.get("change") == "1":
        request.session.pop(PASSWORD_RESET_OTP_SESSION_KEY, None)
        request.session.pop(PASSWORD_RESET_USER_SESSION_KEY, None)

    state = _get_active_otp_state(request)
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if (
                state
                and state["email"] == email
                and time.time() - state["sent_at"] < OTP_RESEND_SECONDS
            ):
                remaining = OTP_RESEND_SECONDS - int(time.time() - state["sent_at"])
                messages.info(request, f"Please wait {remaining} seconds before requesting another code.")
            elif state and state["email"] == email and state["send_count"] >= OTP_MAX_SENDS:
                messages.error(request, "You have reached the code resend limit. Request a new code later.")
            else:
                _send_password_reset_otp(request, email, user, state)
                messages.info(
                    request,
                    "If an account exists for that email, a verification code has been sent.",
                )
            return redirect("password_reset")
    else:
        form = PasswordResetRequestForm()

    state = _get_active_otp_state(request)
    return render(
        request,
        "Accounts/password_reset_form.html",
        {
            "form": form,
            "otp_form": PasswordResetOTPForm(),
            "otp_sent": bool(state),
            "email": state["email"] if state else "",
            "resend_wait": (
                max(0, OTP_RESEND_SECONDS - int(time.time() - state["sent_at"]))
                if state
                else 0
            ),
        },
    )


def password_reset_verify(request):
    if request.method != "POST":
        return redirect("password_reset")

    state = _get_active_otp_state(request)
    if not state:
        messages.error(request, "Your code expired. Request a new one.")
        return redirect("password_reset")
    if state["attempts"] >= OTP_MAX_ATTEMPTS:
        request.session.pop(PASSWORD_RESET_OTP_SESSION_KEY, None)
        messages.error(request, "Too many incorrect attempts. Request a new code.")
        return redirect("password_reset")

    form = PasswordResetOTPForm(request.POST)
    valid_code = (
        form.is_valid()
        and state.get("otp_digest")
        and constant_time_compare(
            state["otp_digest"],
            _otp_digest(form.cleaned_data["otp"]),
        )
    )
    if not valid_code:
        state["attempts"] += 1
        request.session[PASSWORD_RESET_OTP_SESSION_KEY] = state
        if state["attempts"] >= OTP_MAX_ATTEMPTS:
            request.session.pop(PASSWORD_RESET_OTP_SESSION_KEY, None)
            messages.error(request, "Too many incorrect attempts. Request a new code.")
            return redirect("password_reset")
        messages.error(request, "That code is invalid. Check it and try again.")
        return redirect("password_reset")

    user = User.objects.filter(
        pk=state.get("user_id"),
        email__iexact=state["email"],
        is_active=True,
    ).first()
    if user is None:
        messages.error(request, "That code is invalid. Request a new code.")
        request.session.pop(PASSWORD_RESET_OTP_SESSION_KEY, None)
        return redirect("password_reset")

    request.session.pop(PASSWORD_RESET_OTP_SESSION_KEY, None)
    request.session[PASSWORD_RESET_USER_SESSION_KEY] = {
        "user_id": user.pk,
        "expires_at": time.time() + OTP_TTL_SECONDS,
    }
    request.session.set_expiry(OTP_TTL_SECONDS)
    return redirect("password_reset_new_password")


def password_reset_resend(request):
    if request.method != "POST":
        return redirect("password_reset")

    state = _get_active_otp_state(request)
    if not state:
        messages.error(request, "Your code expired. Request a new one.")
        return redirect("password_reset")

    elapsed = time.time() - state["sent_at"]
    if elapsed < OTP_RESEND_SECONDS:
        remaining = OTP_RESEND_SECONDS - int(elapsed)
        messages.info(request, f"Please wait {remaining} seconds before requesting another code.")
        return redirect("password_reset")
    if state["send_count"] >= OTP_MAX_SENDS:
        messages.error(request, "You have reached the code resend limit. Request a new code later.")
        return redirect("password_reset")

    user = User.objects.filter(pk=state.get("user_id"), is_active=True).first()
    _send_password_reset_otp(request, state["email"], user, state)
    messages.info(
        request,
        "If an account exists for that email, a new verification code has been sent.",
    )
    return redirect("password_reset")


def password_reset_new_password(request):
    reset_state = request.session.get(PASSWORD_RESET_USER_SESSION_KEY)
    if not reset_state or reset_state["expires_at"] <= time.time():
        request.session.pop(PASSWORD_RESET_USER_SESSION_KEY, None)
        messages.error(request, "Your verification expired. Request a new code.")
        return redirect("password_reset")

    user = User.objects.filter(pk=reset_state["user_id"], is_active=True).first()
    if user is None:
        request.session.pop(PASSWORD_RESET_USER_SESSION_KEY, None)
        messages.error(request, "Your verification expired. Request a new code.")
        return redirect("password_reset")

    form = SetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        request.session.pop(PASSWORD_RESET_USER_SESSION_KEY, None)
        messages.success(request, "Your password was reset. Please sign in.")
        return redirect("login")

    return render(
        request,
        "Accounts/password_reset_password.html",
        {"form": form},
    )


def _otp_digest(code):
    return salted_hmac("accounts.password_reset_otp", code).hexdigest()


def _get_active_otp_state(request):
    state = request.session.get(PASSWORD_RESET_OTP_SESSION_KEY)
    if state and state["expires_at"] > time.time():
        return state
    request.session.pop(PASSWORD_RESET_OTP_SESSION_KEY, None)
    return None


def _send_password_reset_otp(request, email, user, previous_state=None):
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = time.time()
    send_count = previous_state["send_count"] + 1 if previous_state else 1
    request.session[PASSWORD_RESET_OTP_SESSION_KEY] = {
        "email": email,
        "user_id": user.pk if user else None,
        "otp_digest": _otp_digest(code) if user else "",
        "sent_at": now,
        "expires_at": now + OTP_TTL_SECONDS,
        "attempts": 0,
        "send_count": send_count,
    }
    request.session.pop(PASSWORD_RESET_USER_SESSION_KEY, None)
    request.session.set_expiry(OTP_TTL_SECONDS)

    if user:
        send_mail(
            subject="Your Billwise password reset code",
            message=(
                f"Your Billwise password reset code is {code}.\n\n"
                "It expires in 10 minutes. Do not share this code with anyone."
            ),
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )


def redirect_by_role(user):
    if _is_admin(user):
        return redirect("admin_dashboard")
    return redirect("distributor_dashboard")


@login_required
def admin_dashboard(request):
    if not _is_admin(request.user):
        return redirect("distributor_dashboard")
    return render(request, "Accounts/admin_dashboard.html")


@login_required
def distributor_dashboard(request):
    if _is_admin(request.user):
        return redirect("admin_dashboard")
    invoices = Invoice.objects.filter(user=request.user)
    return render(
        request,
        "Accounts/distributor_dashboard.html",
        {"invoice_count": invoices.count(), "recent_invoices": invoices[:3]},
    )


@login_required
def distributor_profile(request):
    if _is_admin(request.user):
        return redirect("admin_dashboard")
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile was updated.")
        return redirect("distributor_profile")
    return render(
        request,
        "Accounts/distributor_profile.html",
        {"profile": profile, "form": form},
    )


@login_required
def invoice_list(request):
    if _is_admin(request.user):
        return redirect("admin_dashboard")
    invoices = Invoice.objects.filter(user=request.user)
    return render(request, "Accounts/invoices.html", {"invoices": invoices})


@login_required
def invoice_create(request):
    if _is_admin(request.user):
        return redirect("admin_dashboard")
    form = InvoiceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        invoice = form.save(commit=False)
        invoice.user = request.user
        invoice.save()
        messages.success(request, f"Invoice #{invoice.pk} created successfully.")
        return redirect("invoices")
    return render(request, "Accounts/invoice_form.html", {"form": form})


def _is_admin(user):
    return user.is_superuser or (
        hasattr(user, "profile") and user.profile.role == "ADMIN"
    )


def custom_logout(request):
    logout(request)
    return redirect("login")
