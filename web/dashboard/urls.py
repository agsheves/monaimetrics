from django.urls import path
from web.dashboard import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("settings/", views.settings_view, name="settings"),
    path("lookup/", views.lookup_view, name="lookup"),
    path("research/", views.research_view, name="research"),
    path("arb/", views.arb_view, name="arb"),
    path("api/allocation-preview/", views.allocation_preview_api, name="allocation_preview"),
]
