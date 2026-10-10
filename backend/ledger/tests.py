from datetime import date, timedelta
from decimal import Decimal as D
from rest_framework.test import APITestCase
from accounts.models import Branch, User
from ledger.models import *

class CMRS(APITestCase):
    def setUp(self):
        self.b = Branch.objects.create(branch_code="B1", name="B1"); self.b2 = Branch.objects.create(branch_code="B2", name="B2")
        mk = lambda u, r, br=self.b: User.objects.create_user(u, password="pass12345", role=r, branch=br)
        self.admin, self.mgr, self.agent, self.co = mk("a", "ADMIN", None), mk("m", "BRANCH_MANAGER"), mk("g", "COLLECTION_AGENT"), mk("c", "COMPANY_ADMIN", None)
        self.other_mgr = mk("m2", "BRANCH_MANAGER", self.b2)
        self.as_(self.mgr)
        self.cust = self.client.post("/api/customers/", {"full_name": "Test", "phone": "9"}).data
        self.loan = self.client.post("/api/loans/", {"customer": self.cust["id"], "principal_amount": "9000.00", "interest_amount": "1000.00",
            "start_date": str(date.today()), "end_date": str(date.today() + timedelta(days=30)), "installments": 1}).data
    def as_(self, u): self.client.force_authenticate(u)
    def pay(self, amt, **kw):
        self.as_(self.agent); return self.client.post("/api/collections/", {"loan": self.loan["id"], "amount": amt, **kw}, format="json")
    def full_cycle(self, received="6000", dep_amt=None, ref="REF1"):
        self.pay("6000"); sub = self.client.post("/api/cash-submissions/").data
        self.as_(self.mgr); self.client.post(f"/api/cash-submissions/{sub['id']}/verify/", {"received_amount": received, "remarks": "short"})
        self.client.post(f"/api/cash-submissions/{sub['id']}/approve/", {"remarks": "ok"})
        rid = Reconciliation.objects.get(cash_submission_id=sub["id"]).id
        return sub, self.client.post("/api/deposits/", {"reconciliation": rid, "bank_name": "HDFC", "amount": dep_amt or received,
            "deposit_date": str(date.today()), "transaction_reference": ref})

    def test_login_and_me(self):
        self.client.force_authenticate(None)
        assert self.client.post("/api/auth/login/", {"username": "m", "password": "bad"}).status_code == 401
        r = self.client.post("/api/auth/login/", {"username": "m", "password": "pass12345"}); assert r.status_code == 200 and r.data["user"]["role"] == "BRANCH_MANAGER"
    def test_role_permissions(self):
        self.as_(self.agent); assert self.client.post("/api/customers/", {"full_name": "x", "phone": "1"}).status_code == 403
        assert self.client.get("/api/dashboard/admin/").status_code == 403
        self.as_(self.co); assert self.client.post("/api/cash-submissions/").status_code == 403
        self.as_(self.agent); assert self.client.get("/api/deposits/").status_code == 403
    def test_customer_and_loan_schedule(self):
        assert self.cust["branch"] == self.b.id and self.loan["outstanding_amount"] == "10000.00"
        s = self.client.get(f"/api/loans/{self.loan['id']}/schedule/").data; assert sum(D(x["due_amount"]) for x in s) == D("10000")
        self.as_(self.other_mgr); assert self.client.get(f"/api/customers/{self.cust['id']}/").status_code == 404
    def test_partial_payment(self):
        r = self.pay("6000"); assert r.status_code == 201
        s = RepaymentSchedule.objects.get(loan_id=self.loan["id"]); assert (s.status, s.remaining_amount) == ("PARTIAL", D("4000"))
        assert Loan.objects.get(pk=self.loan["id"]).outstanding_amount == D("4000")
    def test_zero_and_over_and_duplicate(self):
        assert self.pay("0").data["detail"] == "Payment amount must be greater than zero."
        assert self.pay("11000").data["detail"] == "Payment exceeds outstanding amount."
        r = self.pay("11000", allow_over=True); assert r.data["flag"] == "OVER_COLLECTION" and D(r.data["excess_amount"]) == D("1000")
        assert Loan.objects.get(pk=self.loan["id"]).outstanding_amount == 0
    def test_duplicate_collection(self):
        assert self.pay("100").status_code == 201; assert "Duplicate" in self.pay("100").data["detail"]
        assert self.pay("100", confirm_duplicate=True).status_code == 201
    def test_discrepancy_and_lock(self):
        sub, r = self.full_cycle(received="5500", ref="D1"); assert r.status_code == 201 and r.data["status"] == "DEPOSITED"
        rec = Reconciliation.objects.get(cash_submission_id=sub["id"]); assert rec.difference == D("500")
        self.as_(self.mgr); r = self.client.post(f"/api/cash-submissions/{sub['id']}/approve/"); assert r.data["detail"] == "Cash submission has already been reconciled."
    def test_discrepancy_needs_remarks(self):
        self.pay("6000"); sub = self.client.post("/api/cash-submissions/").data; self.as_(self.mgr)
        self.client.post(f"/api/cash-submissions/{sub['id']}/verify/", {"received_amount": "5000"})
        assert self.client.post(f"/api/cash-submissions/{sub['id']}/approve/").status_code == 400
    def test_reject_releases_collections(self):
        self.pay("6000"); sub = self.client.post("/api/cash-submissions/").data; self.as_(self.mgr)
        assert self.client.post(f"/api/cash-submissions/{sub['id']}/reject/", {"remarks": "count wrong"}).data["status"] == "REJECTED"
        assert Collection.objects.get().status == "COLLECTED"
        self.as_(self.agent); assert self.client.post("/api/cash-submissions/").status_code == 201
    def test_duplicate_reference_and_mismatch(self):
        _, r = self.full_cycle(ref="SAME"); assert r.status_code == 201
        self.as_(self.agent); self.client.post("/api/collections/", {"loan": self.loan["id"], "amount": "1000"}); sub = self.client.post("/api/cash-submissions/").data
        self.as_(self.mgr); self.client.post(f"/api/cash-submissions/{sub['id']}/verify/", {"received_amount": "1000"}); self.client.post(f"/api/cash-submissions/{sub['id']}/approve/")
        rid = Reconciliation.objects.get(cash_submission_id=sub["id"]).id; body = {"reconciliation": rid, "bank_name": "X", "deposit_date": str(date.today()), "amount": "900"}
        assert self.client.post("/api/deposits/", {**body, "transaction_reference": "SAME"}).data["detail"] == "Duplicate transaction reference."
        r = self.client.post("/api/deposits/", {**body, "transaction_reference": "NEW"}); assert r.data["status"] == "MISMATCH"
        self.as_(self.co); st = Settlement.objects.get(bank_deposit_id=r.data["id"]); assert self.client.post(f"/api/settlements/{st.id}/settle/").status_code == 400
    def test_settlement_lifecycle_and_dashboard(self):
        _, r = self.full_cycle(ref="OK1"); assert Collection.objects.get().status == "DEPOSITED"
        st = Settlement.objects.get(); self.as_(self.mgr); assert self.client.post(f"/api/settlements/{st.id}/settle/").status_code == 403
        self.as_(self.co); assert self.client.post(f"/api/settlements/{st.id}/settle/").data["status"] == "SETTLED"
        assert Collection.objects.get().status == "SETTLED"
        d = self.client.get("/api/dashboard/company/").data; assert d["settled_amount"] == "6000.00" and d["outstanding_amount"] == "4000.00" and d["expected_collections"] == "4000.00"
        assert self.client.post(f"/api/settlements/{st.id}/settle/").status_code == 400
    def test_unauthorized_modification(self):
        self.pay("100"); cid = Collection.objects.get().id
        for m in ("put", "patch", "delete"): assert getattr(self.client, m)(f"/api/collections/{cid}/").status_code == 405
        assert self.client.put(f"/api/loans/{self.loan['id']}/", {}).status_code == 403
        self.as_(self.mgr); r = self.client.patch(f"/api/loans/{self.loan['id']}/", {"principal_amount": "1"}, format="json")
        assert Loan.objects.get().principal_amount == D("9000.00")
    def test_audit_log(self): assert AuditLog.objects.filter(action="LOAN_CREATED").exists()
