import os
import json
import functools
import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from monaimetrics.web_portfolio import get_portfolio_data, get_symbol_data, get_allocation_for_profile, scan_for_opportunities
from monaimetrics.web_research import ask_research
from monaimetrics.web_arb import get_arb_dashboard_data
from monaimetrics.user_config import update_user_config

log = logging.getLogger(__name__)

_VALID_PROFILES = ("conservative", "moderate", "aggressive")


def _current_profile() -> str:
    """Read the active risk profile from the environment (loaded from user_config.yaml).
    Never falls back to session — the file is the single source of truth."""
    raw = os.environ.get("RISK_PROFILE", "moderate")
    val = raw.strip().lower()
    return val if val in _VALID_PROFILES else "moderate"


def login_required(view_func):
    @functools.wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not request.session.get("authenticated"):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapper


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.session.get("authenticated"):
        return redirect("dashboard")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")

        expected_user = os.environ.get("APP_USERNAME", "admin")
        expected_pass = os.environ.get("APP_PASSWORD", "")

        if not expected_pass:
            error = "APP_PASSWORD not configured in environment."
        elif username == expected_user and password == expected_pass:
            request.session["authenticated"] = True
            return redirect("dashboard")
        else:
            error = "Invalid credentials."

    return render(request, "dashboard/login.html", {"error": error})


def logout_view(request: HttpRequest) -> HttpResponse:
    request.session.flush()
    return redirect("login")


@login_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    profile = _current_profile()
    data = get_portfolio_data(profile)
    response = render(request, "dashboard/dashboard.html", {"data": data})
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def settings_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        profile = request.POST.get("risk_profile", "").strip().lower()
        if profile in _VALID_PROFILES:
            try:
                update_user_config("RISK_PROFILE", profile)
            except Exception as e:
                log.warning("Could not persist RISK_PROFILE to user_config.yaml: %s", e)

    profile = _current_profile()
    allocation_table = get_allocation_for_profile(profile)

    response = render(request, "dashboard/settings.html", {
        "profile": profile,
        "profiles": list(_VALID_PROFILES),
        "allocation_table": allocation_table,
    })
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def lookup_view(request: HttpRequest) -> HttpResponse:
    symbol = request.GET.get("symbol", "").strip().upper()
    data = None

    if symbol:
        data = get_symbol_data(symbol, _current_profile())

    response = render(request, "dashboard/lookup.html", {"symbol": symbol, "data": data})
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def research_view(request: HttpRequest) -> HttpResponse:
    question = ""
    result = None

    if request.method == "POST":
        question = request.POST.get("question", "").strip()
        if question:
            result = ask_research(question)

    response = render(request, "dashboard/research.html", {
        "question": question,
        "result": result,
    })
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def arb_view(request: HttpRequest) -> HttpResponse:
    data = get_arb_dashboard_data()
    response = render(request, "dashboard/arb.html", {"data": data})
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def scan_view(request: HttpRequest) -> HttpResponse:
    symbols_raw = request.GET.get("symbols", "").strip().upper()
    symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()] if symbols_raw else None
    data = scan_for_opportunities(_current_profile(), symbols)
    response = render(request, "dashboard/scan.html", {
        "data": data,
        "symbols_input": symbols_raw,
    })
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def allocation_preview_api(request: HttpRequest) -> JsonResponse:
    profile = request.GET.get("profile", "moderate")
    table = get_allocation_for_profile(profile)
    return JsonResponse(table)
