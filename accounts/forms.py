from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Customer, Invoice


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "email", "phone", "address"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Customer or business name"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "name@example.com", "autocomplete": "email"}
            ),
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Phone number", "autocomplete": "tel"}
            ),
            "address": forms.Textarea(
                attrs={"class": "form-control", "placeholder": "Street, city, and postal code", "rows": 3}
            ),
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "family-name"}),
            "username": forms.TextInput(attrs={"class": "form-control", "autocomplete": "username"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("An account with this email address already exists.")
        return email


class RegisterForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "First name", "autocomplete": "given-name"}
        ),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Last name", "autocomplete": "family-name"}
        ),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "you@example.com", "autocomplete": "email"}
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "At least 8 characters", "autocomplete": "new-password"}
        )
    )
    confirm_password = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Repeat your password", "autocomplete": "new-password"}
        ),
    )
    role = forms.ChoiceField(
        choices=[("DISTRIBUTOR", "Distributor"), ("CUSTOMER", "Customer")],
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Choose Distributor to create invoices or Customer to access the customer dashboard.",
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email"]
        widgets = {
            "username": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Choose a username", "autocomplete": "username"}
            ),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        candidate_user = User(
            username=self.cleaned_data.get("username", ""),
            email=self.cleaned_data.get("email", ""),
        )
        validate_password(password, user=candidate_user)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password", self.data.get("password"))
        confirm_password = cleaned_data.get("confirm_password", self.data.get("confirm_password"))
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "The passwords do not match.")
        return cleaned_data


class InvoiceForm(forms.ModelForm):
    description = forms.CharField(
        max_length=500,
        widget=forms.Textarea(
            attrs={"class": "form-control", "placeholder": "What is this invoice for?", "rows": 3}
        ),
    )

    class Meta:
        model = Invoice
        fields = ["customer_name", "customer_email", "description", "amount", "due_date"]
        widgets = {
            "customer_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Customer or business name"}
            ),
            "customer_email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "Optional customer email"}
            ),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0.00", "min": "0.01", "step": "0.01"}
            ),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )
    )


class PasswordResetOTPForm(forms.Form):
    otp = forms.RegexField(
        regex=r"\A\d{6}\Z",
        error_messages={"invalid": "Enter the 6-digit code sent to your email."},
        widget=forms.TextInput(
            attrs={
                "class": "form-control otp-input",
                "placeholder": "000000",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "maxlength": "6",
                "pattern": "[0-9]{6}",
            }
        ),
    )
