from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import LoginView, me
from ledger import views as v

r = DefaultRouter()
r.register("customers", v.CustomerViewSet, "customers")
r.register("loans", v.LoanViewSet, "loans")
r.register("collections", v.CollectionViewSet, "collections")
r.register("cash-submissions", v.SubmissionViewSet, "cash-submissions")
r.register("reconciliation", v.ReconciliationViewSet, "reconciliation")
r.register("deposits", v.DepositViewSet, "deposits")
r.register("settlements", v.SettlementViewSet, "settlements")
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/refresh/", TokenRefreshView.as_view()),
    path("api/auth/me/", me),
    path("api/agent/collections/today/", v.agent_today),
    path("api/dashboard/<str:kind>/", v.dashboard),
    path("api/", include(r.urls)),
]
