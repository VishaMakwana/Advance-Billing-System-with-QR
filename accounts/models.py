from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('DISTRIBUTOR', 'Distributor'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='DISTRIBUTOR')

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Invoice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="invoices")
    customer_name = models.CharField(max_length=150)
    customer_email = models.EmailField(blank=True)
    description = models.CharField(max_length=500)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Invoice #{self.pk} for {self.customer_name}"

    @property
    def qr_payload(self):
        due_date = self.due_date.isoformat() if self.due_date else "Not specified"
        return (
            f"Billing System invoice #{self.pk}\n"
            f"Customer: {self.customer_name}\n"
            f"Description: {self.description}\n"
            f"Amount: {self.amount:.2f}\n"
            f"Due date: {due_date}"
        )