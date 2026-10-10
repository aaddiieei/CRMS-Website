from rest_framework import serializers
from .models import *

class CustomerSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    class Meta:
        model = Customer; fields = "__all__"
        extra_kwargs = {"branch": {"required": False}, "customer_code": {"required": False}}

class ScheduleSerializer(serializers.ModelSerializer):
    class Meta: model = RepaymentSchedule; fields = "__all__"

class LoanSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    class Meta:
        model = Loan; fields = "__all__"
        read_only_fields = ["outstanding_amount", "status"]
        extra_kwargs = {"loan_number": {"required": False}}

class CollectionSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    agent_name = serializers.CharField(source="agent.username", read_only=True)
    loan_number = serializers.CharField(source="loan.loan_number", read_only=True)
    class Meta: model = Collection; fields = "__all__"

class CollectionInput(serializers.Serializer):
    loan = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    payment_date = serializers.DateField(required=False)
    payment_mode = serializers.ChoiceField(["CASH", "UPI", "CHEQUE"], default="CASH")
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
    receipt_number = serializers.CharField(required=False, allow_blank=True)
    allow_over = serializers.BooleanField(default=False)
    confirm_duplicate = serializers.BooleanField(default=False)

class ReconciliationSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="cash_submission.agent.username", read_only=True)
    submission_number = serializers.CharField(source="cash_submission.submission_number", read_only=True)
    submission_status = serializers.CharField(source="cash_submission.status", read_only=True)
    branch = serializers.IntegerField(source="cash_submission.branch_id", read_only=True)
    class Meta: model = Reconciliation; fields = "__all__"

class SubmissionSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.username", read_only=True)
    reconciliation_id = serializers.IntegerField(source="reconciliation.id", read_only=True)
    difference = serializers.DecimalField(source="reconciliation.difference", max_digits=14, decimal_places=2, read_only=True)
    class Meta: model = CashSubmission; fields = "__all__"

class DepositSerializer(serializers.ModelSerializer):
    class Meta: model = BankDeposit; fields = "__all__"

class SettlementSerializer(serializers.ModelSerializer):
    deposit_number = serializers.CharField(source="bank_deposit.deposit_number", read_only=True)
    transaction_reference = serializers.CharField(source="bank_deposit.transaction_reference", read_only=True)
    class Meta: model = Settlement; fields = "__all__"
