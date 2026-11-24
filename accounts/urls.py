from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from . import views

urlpatterns = [
    path("", views.register, name="home"),
    path("login/", views.custom_login, name="login"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="Accounts/password_reset_form.html",
            email_template_name="Accounts/password_reset_email.txt",
            subject_template_name="Accounts/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="Accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="Accounts/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="Accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    path("logout/", views.custom_logout, name="logout"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("distributor-dashboard/", views.distributor_dashboard, name="distributor_dashboard"),
    path("distributor-profile/", views.distributor_profile, name="distributor_profile"),
    path("invoices/", views.invoice_list, name="invoices"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
]