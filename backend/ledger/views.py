from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets, mixins
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from . import services as svc
from .models import *
from .serializers import *

ALL = ["ADMIN", "COLLECTION_AGENT", "BRANCH_MANAGER", "COMPANY_ADMIN"]
class RolePerm(BasePermission):
    message = "You do not have permission to perform this action."
    def has_permission(self, request, view):
        roles = getattr(view, "roles", {})
        allowed = roles.get(getattr(view, "action", None), roles.get("*", ALL))
        return request.user.role == "ADMIN" or request.user.role in allowed

def scope(qs, u, branch_f, agent_f=None):
    if u.role in ("ADMIN", "COMPANY_ADMIN"): return qs
    if u.role == "COLLECTION_AGENT" and agent_f: return qs.filter(**{agent_f: u})
    return qs.filter(**{branch_f: u.branch_id})

def filtered(qs, p, branch_f=None, agent_f=None, date_f=None, status_f="status"):
    if p.get("branch") and branch_f: qs = qs.filter(**{branch_f: p["branch"]})
    if p.get("agent") and agent_f: qs = qs.filter(**{agent_f: p["agent"]})
    if p.get("date") and date_f: qs = qs.filter(**{date_f: p["date"]})
    if p.get("status") and status_f: qs = qs.filter(**{status_f: p["status"]})
    return qs

class Base(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RolePerm]
    branch_f = "branch"; agent_f = None; date_f = None; status_f = "status"
    def get_queryset(self):
        qs = scope(super().get_queryset(), self.request.user, self.branch_f, self.agent_f)
        return filtered(qs, self.request.query_params, self.branch_f, self.agent_f, self.date_f, self.status_f)

READ = ["list", "retrieve"]
class CustomerViewSet(Base, viewsets.ModelViewSet):
    queryset = Customer.objects.select_related("branch").order_by("id"); serializer_class = CustomerSerializer
    roles = {"list": ALL, "retrieve": ALL, "create": ["BRANCH_MANAGER"], "update": ["BRANCH_MANAGER"],
             "partial_update": ["BRANCH_MANAGER"], "destroy": []}
    def get_queryset(self):
        qs = super().get_queryset(); q = self.request.query_params.get("search")
        if q: qs = qs.filter(full_name__icontains=q) | qs.filter(customer_code__icontains=q) | qs.filter(phone__icontains=q)
        return qs
    def perform_create(self, s):
        u = self.request.user; b = s.validated_data.get("branch") if u.role == "ADMIN" else u.branch
        if not b: raise svc.BizError("Branch is required.")
        code = s.validated_data.get("customer_code") or f"CUS{(Customer.objects.order_by('-id').values_list('id', flat=True).first() or 0) + 1:05d}"
        obj = s.save(branch=b, customer_code=code); svc.audit(u, "CUSTOMER_CREATED", obj, new=s.data)
    def perform_update(self, s):
        old = CustomerSerializer(s.instance).data
        obj = s.save(branch=s.instance.branch); svc.audit(self.request.user, "CUSTOMER_UPDATED", obj, old, s.data)
    def perform_destroy(self, obj):
        if obj.loans.exists(): raise svc.BizError("Customer has loans and cannot be deleted.")
        svc.audit(self.request.user, "CUSTOMER_DELETED", obj, CustomerSerializer(obj).data); obj.delete()

class LoanViewSet(Base, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    queryset = Loan.objects.select_related("customer").order_by("id"); serializer_class = LoanSerializer
    branch_f = "customer__branch"; status_f = "status"
    roles = {"list": ALL, "retrieve": ALL, "schedule": ALL, "repayments": ALL, "create": ["BRANCH_MANAGER"], "update": ["BRANCH_MANAGER"]}
    def create(self, request):
        s = LoanSerializer(data=request.data); s.is_valid(raise_exception=True); d = s.validated_data
        if request.user.role == "BRANCH_MANAGER" and d["customer"].branch_id != request.user.branch_id:
            raise PermissionDenied("You do not have permission to perform this action.")
        loan = svc.create_loan(request.user, d["customer"], d["principal_amount"], d.get("interest_amount", Decimal("0")),
            d["start_date"], d["end_date"], request.data.get("installments", 4), d.get("loan_number"))
        return Response(LoanSerializer(loan).data, status=201)
    def perform_update(self, s):  # financial amounts & balances are never editable after creation
        for f in ("principal_amount", "interest_amount", "customer"): s.validated_data.pop(f, None)
        old = LoanSerializer(s.instance).data; obj = s.save(); svc.audit(self.request.user, "LOAN_UPDATED", obj, old, s.data)
    @action(detail=True)
    def schedule(self, request, pk=None): return Response(ScheduleSerializer(self.get_object().schedule.all(), many=True).data)
    @action(detail=True)
    def repayments(self, request, pk=None): return Response(CollectionSerializer(self.get_object().collections.all(), many=True).data)

class CollectionViewSet(Base, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    queryset = Collection.objects.select_related("customer", "agent", "loan"); serializer_class = CollectionSerializer
    agent_f = "agent"; date_f = "payment_date"
    roles = {"list": ALL, "retrieve": ALL, "create": ["COLLECTION_AGENT"]}
    def create(self, request):
        s = CollectionInput(data=request.data); s.is_valid(raise_exception=True); d = s.validated_data
        col = svc.record_collection(request.user, d["loan"], d["amount"], d.get("payment_date"), d["payment_mode"],
            d["remarks"], d.get("receipt_number") or None, d["allow_over"], d["confirm_duplicate"])
        return Response(CollectionSerializer(col).data, status=201)

@api_view(["GET"])
def agent_today(request):
    if request.user.role not in ("COLLECTION_AGENT", "ADMIN"): raise PermissionDenied("You do not have permission to perform this action.")
    qs = Collection.objects.filter(payment_date=timezone.localdate())
    if request.user.role == "COLLECTION_AGENT": qs = qs.filter(agent=request.user)
    return Response({"total": qs.aggregate(t=Sum("amount"))["t"] or 0, "results": CollectionSerializer(qs, many=True).data})

class SubmissionViewSet(Base, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    queryset = CashSubmission.objects.select_related("agent", "reconciliation").order_by("-id"); serializer_class = SubmissionSerializer
    agent_f = "agent"; date_f = "submission_date"
    mgr = ["BRANCH_MANAGER"]
    roles = {"list": ALL, "retrieve": ALL, "create": ["COLLECTION_AGENT"], "verify": mgr, "approve": mgr, "reject": mgr}
    def create(self, request):
        sub = svc.create_submission(request.user, request.data.get("remarks", ""))
        return Response(SubmissionSerializer(sub).data, status=201)
    def _act(self, fn, request, **kw):
        sub = fn(self.get_object().pk, request.user, **kw); return Response(SubmissionSerializer(sub).data)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None): return self._act(svc.verify_submission, request, received=request.data.get("received_amount"), remarks=request.data.get("remarks", ""))
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None): return self._act(svc.approve_submission, request, remarks=request.data.get("remarks", ""))
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None): return self._act(svc.reject_submission, request, remarks=request.data.get("remarks", ""))

class ReconciliationViewSet(Base, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    queryset = Reconciliation.objects.select_related("cash_submission__agent").order_by("-id"); serializer_class = ReconciliationSerializer
    branch_f = "cash_submission__branch"; agent_f = "cash_submission__agent"; date_f = "cash_submission__submission_date"
    roles = {"list": ALL, "retrieve": ALL, "verify": ["BRANCH_MANAGER"]}
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        rec = self.get_object()
        svc.verify_submission(rec.cash_submission_id, request.user, request.data.get("received_amount"), request.data.get("remarks", ""))
        rec.refresh_from_db(); return Response(ReconciliationSerializer(rec).data)

class DepositViewSet(Base, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    queryset = BankDeposit.objects.order_by("-id"); serializer_class = DepositSerializer; date_f = "deposit_date"
    roles = {"list": ["BRANCH_MANAGER", "COMPANY_ADMIN"], "retrieve": ["BRANCH_MANAGER", "COMPANY_ADMIN"], "create": ["BRANCH_MANAGER"]}
    def create(self, request):
        d = request.data
        try:
            amount = Decimal(str(d.get("amount")))
            rid = int(d.get("reconciliation"))
            dt = timezone.datetime.fromisoformat(str(d.get("deposit_date")).strip()).date()
        except Exception: raise svc.BizError("Reconciliation, amount and deposit date are required and must be valid.")
        dep = svc.create_deposit(request.user, rid, d.get("bank_name", ""), amount, dt, d.get("transaction_reference"))
        return Response(DepositSerializer(dep).data, status=201)

class SettlementViewSet(Base, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    queryset = Settlement.objects.select_related("bank_deposit").order_by("-id"); serializer_class = SettlementSerializer
    branch_f = "bank_deposit__branch"; date_f = "settlement_date"
    co = ["COMPANY_ADMIN"]
    roles = {"list": ["BRANCH_MANAGER", "COMPANY_ADMIN"], "retrieve": ["BRANCH_MANAGER", "COMPANY_ADMIN"], "settle": co, "fail": co}
    @action(detail=True, methods=["post"])
    def settle(self, request, pk=None):
        return Response(SettlementSerializer(svc.settle(self.get_object().pk, request.user, request.data.get("remarks", ""), True)).data)
    @action(detail=True, methods=["post"])
    def fail(self, request, pk=None):
        return Response(SettlementSerializer(svc.settle(self.get_object().pk, request.user, request.data.get("remarks", ""), False)).data)

DASH_ROLES = {"admin": ["ADMIN"], "agent": ["COLLECTION_AGENT"], "branch": ["BRANCH_MANAGER"], "company": ["COMPANY_ADMIN"]}
@api_view(["GET"])
def dashboard(request, kind):
    u, p = request.user, request.query_params
    if kind not in DASH_ROLES or (u.role != "ADMIN" and u.role not in DASH_ROLES[kind]):
        raise PermissionDenied("You do not have permission to perform this action.")
    S = lambda qs, f: str(Decimal(qs.aggregate(t=Sum(f))["t"] or 0).quantize(Decimal("0.01")))
    col = filtered(scope(Collection.objects.select_related("customer", "agent", "loan").all(), u, "branch", "agent"), p, "branch", "agent", "payment_date")
    sch = scope(RepaymentSchedule.objects.exclude(status="PAID"), u, "loan__customer__branch")
    loans = scope(Loan.objects.filter(status="ACTIVE"), u, "customer__branch")
    rec = scope(Reconciliation.objects.select_related("cash_submission__agent").all(), u, "cash_submission__branch", "cash_submission__agent")
    dep = scope(BankDeposit.objects.filter(status__in=["DEPOSITED", "SETTLED"]), u, "branch")
    st = scope(Settlement.objects.filter(status="SETTLED"), u, "bank_deposit__branch")
    if p.get("branch") and u.role in ("ADMIN", "COMPANY_ADMIN"):
        b = p["branch"]; sch = sch.filter(loan__customer__branch=b); loans = loans.filter(customer__branch=b)
        rec = rec.filter(cash_submission__branch=b); dep = dep.filter(branch=b); st = st.filter(bank_deposit__branch=b)
    return Response({
        "expected_collections": S(sch, "remaining_amount"), "total_collected": S(col, "amount"),
        "cash_with_agents": S(col.filter(status__in=["COLLECTED", "SUBMITTED"]), "amount"),
        "cash_at_branches": S(col.filter(status="BRANCH_RECEIVED"), "amount"),
        "bank_deposited": S(dep, "amount"), "settled_amount": S(st, "settlement_amount"),
        "outstanding_amount": S(loans, "outstanding_amount"),
        "discrepancies": S(rec.exclude(status__in=["PENDING", "REJECTED"]).exclude(difference=0), "difference"),
        "recent_collections": CollectionSerializer(col[:5], many=True).data,
        "recent_reconciliations": ReconciliationSerializer(rec.order_by("-id")[:5], many=True).data})
