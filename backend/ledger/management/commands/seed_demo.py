from datetime import date, timedelta
from decimal import Decimal as D
from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import Branch, User
from ledger import services as s
from ledger.models import *

PW = "Demo@12345"
class Command(BaseCommand):
    help = "Create demo data (password for all users: Demo@12345)"
    @transaction.atomic
    def handle(self, *a, **o):
        if User.objects.filter(username="admin").exists():
            return self.stdout.write("Demo data already exists.")
        b1 = Branch.objects.create(branch_code="BR001", name="Delhi Central", city="Delhi", state="Delhi", address="Connaught Place")
        b2 = Branch.objects.create(branch_code="BR002", name="Mumbai West", city="Mumbai", state="Maharashtra", address="Andheri West")
        mk = lambda u, role, br=None, f="", l="": User.objects.create_user(u, f"{u}@cmrs.test", PW, role=role, branch=br, first_name=f, last_name=l)
        admin = mk("admin", "ADMIN", None, "System", "Admin"); mk("company", "COMPANY_ADMIN", None, "Company", "Admin")
        m1 = mk("manager1", "BRANCH_MANAGER", b1, "Rohit", "Sharma"); m2 = mk("manager2", "BRANCH_MANAGER", b2, "Anita", "Desai")
        ag = [mk("agent1", "COLLECTION_AGENT", b1, "Amit", "Verma"), mk("agent2", "COLLECTION_AGENT", b1, "Neha", "Singh"),
              mk("agent3", "COLLECTION_AGENT", b2, "Suresh", "Patil"), mk("agent4", "COLLECTION_AGENT", b2, "Pooja", "Joshi")]
        names = ["Ramesh Kumar", "Sunita Devi", "Mohan Lal", "Geeta Rani", "Vijay Yadav",
                 "Kavita Shah", "Deepak Mehta", "Lakshmi Iyer", "Imran Khan", "Priya Nair"]
        today = date.today(); loans = []
        for i, n in enumerate(names):
            c = Customer.objects.create(customer_code=f"CUS{i+1:05d}", full_name=n, phone=f"98100000{i:02d}",
                email=f"cust{i+1}@example.com", address="Demo address", branch=b1 if i < 5 else b2)
            loans.append(s.create_loan(admin, c, D(20000 + i * 5000), D(2000 + i * 500), today - timedelta(days=30), today + timedelta(days=120), 4, f"LN{i+1:05d}"))
        # agent1: collect, submit, verify with discrepancy, approve, deposit, settle (full lifecycle)
        s.record_collection(ag[0], loans[0].id, D("6000")); s.record_collection(ag[0], loans[1].id, D("8000"))
        sub = s.create_submission(ag[0]); s.verify_submission(sub.id, m1, D("13500"), "Short by 500"); s.approve_submission(sub.id, m1, "Agent to repay shortfall")
        dep = s.create_deposit(m1, sub.reconciliation.id, "HDFC Bank", D("13500"), today, "HDFC-TXN-1001"); s.settle(dep.settlement.id, User.objects.get(username="company"))
        # agent2: submission verified (awaiting approval)
        s.record_collection(ag[1], loans[2].id, D("5000")); sub = s.create_submission(ag[1]); s.verify_submission(sub.id, m1, D("5000"))
        # agent3: approved, deposit mismatch
        s.record_collection(ag[2], loans[5].id, D("10000")); sub = s.create_submission(ag[2]); s.verify_submission(sub.id, m2, D("10000")); s.approve_submission(sub.id, m2)
        s.create_deposit(m2, sub.reconciliation.id, "ICICI Bank", D("9800"), today, "ICICI-TXN-2001")
        # agent4: collected only; agent2: partial + over-collection
        s.record_collection(ag[3], loans[6].id, D("4000")); s.record_collection(ag[1], loans[3].id, D("1000"))
        self.stdout.write(self.style.SUCCESS("Demo data created."))
