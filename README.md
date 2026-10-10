# CMRS – Cash Management & Reconciliation System

Tracks loan repayment cash from customer to final settlement:
`EXPECTED → COLLECTED → SUBMITTED → BRANCH_RECEIVED → DEPOSITED → SETTLED`

## Problem
Field agents collect cash for loan repayments. Companies need to know where every rupee is (agent, branch, bank, settled), catch shortages, and prevent tampering after approval.

## Stack
React + Vite + React Router + Axios · Django + DRF + SimpleJWT · PostgreSQL (SQLite fallback for local dev) · Decimal for all money.

## Architecture
```
backend/
  config/    settings, urls
  accounts/  User (role, branch), Branch, JWT login, /auth/me
  ledger/    models.py (all domain tables + AuditLog), services.py (ALL business logic, transaction.atomic),
             views.py (RBAC viewsets, branch/agent scoping, filters, dashboards), serializers.py, tests.py, seed_demo
frontend/src/ services/api.js (axios+refresh), context/AuthContext, components/ui.jsx, pages/Pages.jsx, App.jsx (role-based nav/routes)
```

## Setup
Backend:
```
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # export the variables (or set them in your host)
python manage.py migrate && python manage.py seed_demo && python manage.py runserver
python manage.py test
```
Frontend:
```
cd frontend && cp .env.example .env && npm install && npm run dev      # http://localhost:5173
```
Without `DATABASE_URL` the backend uses SQLite. For PostgreSQL: `DATABASE_URL=postgres://user:pass@host:5432/cmrs`.

## Environment variables
Backend: `SECRET_KEY` (required when DEBUG=False), `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `DATABASE_URL`.
Frontend: `VITE_API_URL` (e.g. `https://api.example.com/api`). Production: `gunicorn config.wsgi`, run `migrate`, serve `frontend/dist` as static site.

## Test credentials (password for all: `Demo@12345`)
| Role | Username |
|---|---|
| Admin | admin |
| Company Admin | company |
| Branch Managers | manager1 (Delhi), manager2 (Mumbai) |
| Collection Agents | agent1, agent2 (Delhi), agent3, agent4 (Mumbai) |

Demo data includes a fully settled lifecycle (with a ₹500 discrepancy), a verified submission awaiting approval, a bank deposit mismatch (agent3/manager2), and open collections.

## Role access
| Role | Can do |
|---|---|
| ADMIN | everything |
| COLLECTION_AGENT | view own-branch customers/loans, record collections, submit cash |
| BRANCH_MANAGER | manage branch customers/loans, verify/approve/reject cash, create bank deposits |
| COMPANY_ADMIN | read-only across branches; settle / fail settlements |

## Business rules (enforced in `ledger/services.py`)
1. Amounts > 0 (also DB CHECK constraints); all money is `DecimalField`.
2. Unique receipt numbers and unique bank transaction references.
3. Partial payments: allocated oldest-due-first; schedule status PENDING → PARTIAL → PAID.
4. Over-collection: rejected ("Payment exceeds outstanding amount.") unless the agent confirms; then stored with `flag=OVER_COLLECTION` and `excess_amount`, loan applied only up to outstanding.
5. Duplicate collection (same loan, agent, amount, date) is blocked unless explicitly confirmed.
6. Cash discrepancy: `difference = expected − received`; approving a discrepancy requires remarks.
7. Rejected submission releases its collections back to the agent (COLLECTED) for resubmission.
8. Deposit must reference an APPROVED reconciliation; amount ≠ received cash → `MISMATCH` and settlement is blocked.
9. Approved/rejected submissions, collections, deposits and settled records are immutable (no update/delete endpoints; "already reconciled" errors); loan amounts can't be edited after creation.
10. Every important action is written to `AuditLog`; every money flow runs in `transaction.atomic` with row locks.

## API
Auth: `POST /api/auth/login/`, `POST /api/auth/refresh/`, `GET /api/auth/me/`
Customers: CRUD `/api/customers/` (`?search=`) · Loans: `GET/POST /api/loans/`, `GET/PUT /api/loans/{id}/`, `/schedule/`, `/repayments/`
Collections: `GET/POST /api/collections/`, `GET /api/collections/{id}/`, `GET /api/agent/collections/today/`
Cash: `/api/cash-submissions/` (+ `POST {id}/verify|approve|reject/`) · Reconciliation: `GET /api/reconciliation/`, `POST {id}/verify/`
Deposits: `GET/POST /api/deposits/` · Settlements: `GET /api/settlements/`, `POST {id}/settle|fail/`
Dashboards: `GET /api/dashboard/{admin|agent|branch|company}/`
Filters on list endpoints: `?date=&branch=&agent=&status=`. Errors return `{"detail": "..."}`.

## ER diagram
```mermaid
erDiagram
  Branch ||--o{ User : has
  Branch ||--o{ Customer : has
  Customer ||--o{ Loan : has
  Loan ||--o{ RepaymentSchedule : has
  Loan ||--o{ Collection : receives
  User ||--o{ Collection : collects
  User ||--o{ CashSubmission : submits
  CashSubmission ||--o{ Collection : groups
  CashSubmission ||--|| Reconciliation : has
  Reconciliation ||--o| BankDeposit : deposited_as
  BankDeposit ||--|| Settlement : settled_by
  User ||--o{ AuditLog : performs
```

## Future improvements
Resolution workflow for deposit mismatches, bank statement import/auto-match, user/branch admin screens, pagination UI, CSV export, SMS receipts, screenshots, richer frontend tests.
