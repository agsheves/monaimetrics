from django.urls import path
from web.dashboard import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("settings/", views.settings_view, name="settings"),
    path("lookup/", views.lookup_view, name="lookup"),
    path("research/", views.research_view, name="research"),
    path("scan/", views.scan_view, name="scan"),
    path("review/", views.review_action_view, name="review_action"),
    path("backtest/", views.backtest_view, name="backtest"),
    path("notifications/", views.notifications_view, name="notifications"),
    path("journal/", views.journal_view, name="journal"),
    path("api/unread-count/", views.api_unread_count, name="api_unread_count"),
    path("api/allocation-preview/", views.allocation_preview_api, name="allocation_preview"),
    path("plan/", views.plan_view, name="plan"),
]
