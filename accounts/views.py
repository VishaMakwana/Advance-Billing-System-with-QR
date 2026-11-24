from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import InvoiceForm, RegisterForm
from .models import Invoice, Profile


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
    return render(request, "Accounts/distributor_profile.html", {"profile": profile})


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
