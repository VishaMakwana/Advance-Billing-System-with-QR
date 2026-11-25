from django.urls import path
from . import views

urlpatterns = [
    path("", views.register, name="home"),
    path("login/", views.custom_login, name="login"),
    path(
        "password-reset/",
        views.password_reset_request,
        name="password_reset",
    ),
    path("password-reset/verify/", views.password_reset_verify, name="password_reset_verify"),
    path("password-reset/resend/", views.password_reset_resend, name="password_reset_resend"),
    path(
        "password-reset/new-password/",
        views.password_reset_new_password,
        name="password_reset_new_password",
    ),
    path("logout/", views.custom_logout, name="logout"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("customer-dashboard/", views.customer_dashboard, name="customer_dashboard"),
    path("distributor-dashboard/", views.distributor_dashboard, name="distributor_dashboard"),
    path("distributor-profile/", views.distributor_profile, name="distributor_profile"),
    path("customers/new/", views.customer_create, name="customer_create"),
    path("invoices/", views.invoice_list, name="invoices"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
]