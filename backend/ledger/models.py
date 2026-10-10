from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q
from accounts.models import Branch

U = settings.AUTH_USER_MODEL
def money(**k): return models.DecimalField(max_digits=14, decimal_places=2, **k)

class Customer(models.Model):
    customer_code = models.CharField(max_length=30, unique=True)
    full_name = models.CharField(max_length=150, db_index=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="customers")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Loan(models.Model):
    loan_number = models.CharField(max_length=30, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="loans")
    principal_amount = money()
    interest_amount = money(default=Decimal("0"))
    outstanding_amount = money()
    start_date = models.DateField(); end_date = models.DateField()
    status = models.CharField(max_length=10, default="ACTIVE", db_index=True)  # ACTIVE / CLOSED
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(principal_amount__gt=0), name="loan_principal_pos"),
                       models.CheckConstraint(condition=Q(outstanding_amount__gte=0), name="loan_outstanding_nonneg")]

class RepaymentSchedule(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="schedule")
    due_date = models.DateField(db_index=True)
    due_amount = money(); paid_amount = money(default=Decimal("0")); remaining_amount = money()
    status = models.CharField(max_length=10, default="PENDING", db_index=True)  # PENDING/PARTIAL/PAID
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["due_date"]

class CashSubmission(models.Model):
    submission_number = models.CharField(max_length=40, unique=True)
    agent = models.ForeignKey(U, on_delete=models.PROTECT, related_name="submissions")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    submission_date = models.DateField()
    expected_amount = money()
    status = models.CharField(max_length=10, default="PENDING", db_index=True)  # PENDING/VERIFIED/APPROVED/REJECTED
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Collection(models.Model):
    # status lifecycle: COLLECTED -> SUBMITTED -> BRANCH_RECEIVED -> DEPOSITED -> SETTLED
    receipt_number = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name="collections")
    repayment_schedule = models.ForeignKey(RepaymentSchedule, null=True, on_delete=models.PROTECT)
    agent = models.ForeignKey(U, on_delete=models.PROTECT, related_name="collections")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    amount = money()
    excess_amount = money(default=Decimal("0"))
    flag = models.CharField(max_length=20, default="NONE")  # NONE / OVER_COLLECTION
    payment_date = models.DateField(db_index=True)
    payment_mode = models.CharField(max_length=10, default="CASH")
    status = models.CharField(max_length=20, default="COLLECTED", db_index=True)
    submission = models.ForeignKey(CashSubmission, null=True, blank=True, on_delete=models.SET_NULL, related_name="collections")
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="collection_amount_pos")]
        ordering = ["-created_at"]

class Reconciliation(models.Model):
    cash_submission = models.OneToOneField(CashSubmission, on_delete=models.PROTECT, related_name="reconciliation")
    expected_amount = money(); received_amount = money(default=Decimal("0")); difference = money(default=Decimal("0"))
    verified_by = models.ForeignKey(U, null=True, blank=True, on_delete=models.PROTECT)
    verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default="PENDING", db_index=True)  # PENDING/MATCHED/DISCREPANCY/APPROVED/REJECTED
    remarks = models.TextField(blank=True)

class BankDeposit(models.Model):
    deposit_number = models.CharField(max_length=40, unique=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    reconciliation = models.OneToOneField(Reconciliation, on_delete=models.PROTECT, related_name="deposit")
    bank_name = models.CharField(max_length=100)
    amount = money()
    deposit_date = models.DateField()
    transaction_reference = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=10, default="DEPOSITED", db_index=True)  # DEPOSITED/MISMATCH/SETTLED
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="deposit_amount_pos")]

class Settlement(models.Model):
    bank_deposit = models.OneToOneField(BankDeposit, on_delete=models.PROTECT, related_name="settlement")
    settlement_amount = money()
    settlement_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, default="PENDING", db_index=True)  # PENDING/SETTLED/FAILED
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class AuditLog(models.Model):
    user = models.ForeignKey(U, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60, db_index=True)
    entity_type = models.CharField(max_length=40); entity_id = models.PositiveIntegerField()
    old_data = models.JSONField(null=True, blank=True); new_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: indexes = [models.Index(fields=["entity_type", "entity_id"])]
