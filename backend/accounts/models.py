from django.contrib.auth.models import AbstractUser
from django.db import models

class Branch(models.Model):
    branch_code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.branch_code} {self.name}"

class User(AbstractUser):
    ROLES = [("ADMIN", "Admin"), ("COLLECTION_AGENT", "Collection Agent"),
             ("BRANCH_MANAGER", "Branch Manager"), ("COMPANY_ADMIN", "Company Admin")]
    role = models.CharField(max_length=20, choices=ROLES, default="COLLECTION_AGENT", db_index=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="users")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
