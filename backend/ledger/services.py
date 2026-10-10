"""All financial business logic. Every money-moving operation is atomic."""
import json, uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException
from .models import *

ZERO = Decimal("0")
class BizError(APIException):
    status_code = 400
    default_detail = "Invalid request."

def num(prefix): return f"{prefix}-{timezone.now():%y%m%d}-{uuid.uuid4().hex[:6].upper()}"
def audit(user, action, obj, old=None, new=None):
    j = lambda d: json.loads(json.dumps(d, default=str)) if d is not None else None
    AuditLog.objects.create(user=user, action=action, entity_type=type(obj).__name__, entity_id=obj.pk, old_data=j(old), new_data=j(new))

@transaction.atomic
def create_loan(user, customer, principal, interest, start, end, installments=4, loan_number=None):
    if principal <= 0: raise BizError("Principal must be greater than zero.")
    if end <= start: raise BizError("End date must be after start date.")
    total = principal + interest
    loan = Loan.objects.create(loan_number=loan_number or num("LN"), customer=customer, principal_amount=principal,
        interest_amount=interest, outstanding_amount=total, start_date=start, end_date=end)
    try: n = max(int(installments), 1)
    except (ValueError, TypeError): n = 4
    each = (total / n).quantize(Decimal("0.01")); step = (end - start) / n
    for i in range(1, n + 1):
        due = total - each * (n - 1) if i == n else each  # last installment absorbs rounding
        RepaymentSchedule.objects.create(loan=loan, due_date=start + step * i, due_amount=due, remaining_amount=due)
    audit(user, "LOAN_CREATED", loan, new={"total": total})
    return loan

@transaction.atomic
def record_collection(user, loan_id, amount, payment_date=None, payment_mode="CASH", remarks="",
                      receipt_number=None, allow_over=False, confirm_duplicate=False):
    if amount is None or amount <= 0: raise BizError("Payment amount must be greater than zero.")
    try: loan = Loan.objects.select_for_update().select_related("customer").get(pk=loan_id)
    except Loan.DoesNotExist: raise BizError("Loan not found.")
    if user.role == "COLLECTION_AGENT" and loan.customer.branch_id != user.branch_id:
        raise BizError("This loan does not belong to your branch.")
    if loan.status != "ACTIVE": raise BizError("Loan is closed.")
    payment_date = payment_date or timezone.localdate()
    if receipt_number and Collection.objects.filter(receipt_number=receipt_number).exists():
        raise BizError("Duplicate receipt number.")
    if not confirm_duplicate and Collection.objects.filter(loan=loan, agent=user, amount=amount, payment_date=payment_date).exists():
        raise BizError("Duplicate collection: same loan, amount and date already recorded.")
    excess = max(amount - loan.outstanding_amount, ZERO)
    if excess and not allow_over:
        raise BizError("Payment exceeds outstanding amount.")
    applied, first = amount - excess, None
    for s in loan.schedule.select_for_update().exclude(status="PAID").order_by("due_date"):
        if applied <= 0: break
        pay = min(applied, s.remaining_amount)
        s.paid_amount += pay; s.remaining_amount -= pay
        s.status = "PAID" if s.remaining_amount == 0 else "PARTIAL"
        s.save(); applied -= pay; first = first or s
    loan.outstanding_amount -= (amount - excess)
    if loan.outstanding_amount == 0: loan.status = "CLOSED"
    loan.save()
    col = Collection.objects.create(receipt_number=receipt_number or num("RCP"), customer=loan.customer, loan=loan,
        repayment_schedule=first, agent=user, branch=loan.customer.branch, amount=amount, excess_amount=excess,
        flag="OVER_COLLECTION" if excess else "NONE", payment_date=payment_date, payment_mode=payment_mode, remarks=remarks)
    audit(user, "COLLECTION_RECORDED", col, new={"amount": amount, "excess": excess, "loan": loan.loan_number})
    return col

@transaction.atomic
def create_submission(user, remarks="", date=None):
    cols = list(Collection.objects.select_for_update().filter(agent=user, status="COLLECTED"))
    if not cols: raise BizError("No unsubmitted collections to submit.")
    total = sum((c.amount for c in cols), ZERO)
    branch = user.branch or (cols[0].branch if cols else None)
    if not branch: raise BizError("Agent must be assigned to a branch.")
    sub = CashSubmission.objects.create(submission_number=num("SUB"), agent=user, branch=branch,
        submission_date=date or timezone.localdate(), expected_amount=total, remarks=remarks)
    Collection.objects.filter(pk__in=[c.pk for c in cols]).update(status="SUBMITTED", submission=sub)
    Reconciliation.objects.create(cash_submission=sub, expected_amount=total)
    audit(user, "CASH_SUBMITTED", sub, new={"expected": total, "count": len(cols)})
    return sub

def _lock(sub_id):
    sub = CashSubmission.objects.select_for_update().get(pk=sub_id)
    if sub.status in ("APPROVED", "REJECTED"): raise BizError("Cash submission has already been reconciled.")
    return sub

@transaction.atomic
def verify_submission(sub_id, user, received, remarks=""):
    sub = _lock(sub_id)
    try: received = Decimal(str(received))
    except Exception: raise BizError("Received amount is invalid.")
    if received < 0: raise BizError("Received amount cannot be negative.")
    r = sub.reconciliation
    r.received_amount, r.difference = received, sub.expected_amount - received
    r.status = "MATCHED" if r.difference == 0 else "DISCREPANCY"
    r.verified_by, r.verified_at, r.remarks = user, timezone.now(), remarks
    r.save(); sub.status = "VERIFIED"; sub.save()
    audit(user, "CASH_VERIFIED", sub, new={"received": received, "difference": r.difference})
    return sub

@transaction.atomic
def approve_submission(sub_id, user, remarks=""):
    sub = _lock(sub_id); r = sub.reconciliation
    if sub.status != "VERIFIED": raise BizError("Verify the cash submission before approving.")
    if r.difference != 0 and not (remarks or r.remarks): raise BizError("Remarks are required to approve a cash discrepancy.")
    if remarks: r.remarks = remarks
    r.status = "APPROVED"; r.save(); sub.status = "APPROVED"; sub.save()
    sub.collections.update(status="BRANCH_RECEIVED")
    audit(user, "CASH_APPROVED", sub, new={"difference": r.difference})
    return sub

@transaction.atomic
def reject_submission(sub_id, user, remarks=""):
    sub = _lock(sub_id)
    if not remarks: raise BizError("A reason is required to reject a cash submission.")
    sub.collections.update(status="COLLECTED", submission=None)  # agent can resubmit
    r = sub.reconciliation; r.status = "REJECTED"; r.remarks = remarks; r.verified_by = user; r.verified_at = timezone.now(); r.save()
    sub.status = "REJECTED"; sub.remarks = remarks; sub.save()
    audit(user, "CASH_REJECTED", sub, new={"reason": remarks})
    return sub

@transaction.atomic
def create_deposit(user, reconciliation_id, bank_name, amount, deposit_date, transaction_reference):
    try: rec = Reconciliation.objects.select_for_update().select_related("cash_submission").get(pk=reconciliation_id)
    except Reconciliation.DoesNotExist: raise BizError("Reconciliation not found.")
    if user.role == "BRANCH_MANAGER" and rec.cash_submission.branch_id != user.branch_id:
        raise BizError("You do not have permission to perform this action.")
    ref = (transaction_reference or "").strip()
    if not ref: raise BizError("Transaction reference is required.")
    if not (bank_name or "").strip(): raise BizError("Bank name is required.")
    if amount is None or amount <= 0: raise BizError("Deposit amount must be greater than zero.")
    if rec.status != "APPROVED": raise BizError("Only approved reconciliations can be deposited.")
    if BankDeposit.objects.filter(reconciliation=rec).exists(): raise BizError("A deposit already exists for this reconciliation.")
    if BankDeposit.objects.filter(transaction_reference=ref).exists(): raise BizError("Duplicate transaction reference.")
    ok = amount == rec.received_amount
    dep = BankDeposit.objects.create(deposit_number=num("DEP"), branch=rec.cash_submission.branch, reconciliation=rec,
        bank_name=bank_name, amount=amount, deposit_date=deposit_date, transaction_reference=ref,
        status="DEPOSITED" if ok else "MISMATCH")
    Settlement.objects.create(bank_deposit=dep, settlement_amount=amount,
        remarks="" if ok else "Deposit amount differs from cash received")
    if ok: rec.cash_submission.collections.update(status="DEPOSITED")
    audit(user, "BANK_DEPOSIT_CREATED" if ok else "BANK_DEPOSIT_MISMATCH", dep, new={"amount": amount, "expected": rec.received_amount})
    return dep

@transaction.atomic
def settle(st_id, user, remarks="", success=True):
    st = Settlement.objects.select_for_update().select_related("bank_deposit__reconciliation__cash_submission").get(pk=st_id)
    if st.status != "PENDING": raise BizError("Settlement has already been processed.")
    dep = st.bank_deposit
    if success:
        if dep.status != "DEPOSITED": raise BizError("Bank deposit mismatch must be resolved before settlement.")
        st.status, st.settlement_date = "SETTLED", timezone.localdate()
        dep.status = "SETTLED"; dep.save()
        dep.reconciliation.cash_submission.collections.update(status="SETTLED")
    else: st.status = "FAILED"
    st.remarks = remarks or st.remarks; st.save()
    audit(user, "SETTLEMENT_" + st.status, st, new={"amount": st.settlement_amount})
    return st
