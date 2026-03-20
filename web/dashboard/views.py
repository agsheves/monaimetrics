import os
import json
import functools

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from monaimetrics.web_portfolio import get_portfolio_data, get_symbol_data, get_allocation_for_profile, scan_for_opportunities
from monaimetrics.web_research import ask_research
from monaimetrics.web_backtest import run_web_backtest, get_backtest_info
from monaimetrics import trade_journal as _trade_journal


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
    from monaimetrics import runtime_settings, review_queue, trade_journal, notifications

    rt = runtime_settings.load()
    profile = rt.risk_profile
    data = get_portfolio_data(profile)

    # Pending review signals
    pending = review_queue.get_pending()
    pending_data = [
        {
            "id": s.id,
            "symbol": s.symbol,
            "action": s.action,
            "tier": s.tier,
            "confidence": s.confidence,
            "position_size_usd": round(s.position_size_usd, 2),
            "stop_price": round(s.stop_price, 2) if s.stop_price else None,
            "target_price": round(s.target_price, 2) if s.target_price else None,
            "reasons": s.reasons,
            "created_at": s.created_at.strftime("%H:%M:%S"),
        }
        for s in pending
    ]

    # Recent activity for timeline
    activity = trade_journal.recent_activity(n=20)
    for event in activity:
        ts = event.get("ts", "")
        if ts:
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(ts)
                event["ts_display"] = dt.strftime("%H:%M:%S")
                event["date_display"] = dt.strftime("%b %d")
            except Exception:
                event["ts_display"] = ts[:19]
                event["date_display"] = ""

    data["pending_reviews"] = pending_data
    data["activity"] = list(reversed(activity))
    data["unread_count"] = notifications.unread_count()
    data["human_review"] = rt.human_review
    data["dry_run"] = rt.dry_run
    data["settings"] = {
        "risk_profile": rt.risk_profile,
        "min_position_usd": rt.min_position_usd,
        "max_position_usd": rt.max_position_usd,
    }

    response = render(request, "dashboard/dashboard.html", {"data": data})
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
@require_http_methods(["POST"])
def review_action_view(request: HttpRequest) -> HttpResponse:
    """Handle approve/reject actions on pending signals."""
    from monaimetrics import review_queue

    action = request.POST.get("action", "")
    signal_id = request.POST.get("signal_id", "")

    if action == "approve" and signal_id:
        review_queue.approve(signal_id)
    elif action == "reject" and signal_id:
        review_queue.reject(signal_id)
    elif action == "approve_all":
        review_queue.approve_all()
    elif action == "reject_all":
        review_queue.reject_all()

    return redirect("dashboard")


@login_required
def settings_view(request: HttpRequest) -> HttpResponse:
    from monaimetrics import runtime_settings

    if request.method == "POST":
        rt = runtime_settings.load()

        # Risk profile
        profile = request.POST.get("risk_profile", rt.risk_profile)
        if profile in ("conservative", "moderate", "aggressive"):
            rt.risk_profile = profile

        # Position sizing
        try:
            min_pos = float(request.POST.get("min_position_usd", rt.min_position_usd))
            if 10 <= min_pos <= 100000:
                rt.min_position_usd = min_pos
        except (ValueError, TypeError):
            pass

        try:
            max_pos = float(request.POST.get("max_position_usd", rt.max_position_usd))
            if 10 <= max_pos <= 100000:
                rt.max_position_usd = max_pos
        except (ValueError, TypeError):
            pass

        # Ensure min <= max
        if rt.min_position_usd > rt.max_position_usd:
            rt.min_position_usd, rt.max_position_usd = rt.max_position_usd, rt.min_position_usd

        # Universe limit
        try:
            limit = int(request.POST.get("scan_universe_limit", rt.scan_universe_limit))
            if 10 <= limit <= 2000:
                rt.scan_universe_limit = limit
        except (ValueError, TypeError):
            pass

        # Toggles
        rt.dry_run = request.POST.get("dry_run") == "on"
        rt.human_review = request.POST.get("human_review") == "on"

        # Webhook
        rt.webhook_url = request.POST.get("webhook_url", "").strip()

        runtime_settings.save(rt)

    rt = runtime_settings.load()
    allocation_table = get_allocation_for_profile(rt.risk_profile)

    response = render(request, "dashboard/settings.html", {
        "settings": rt,
        "profiles": ["conservative", "moderate", "aggressive"],
        "allocation_table": allocation_table,
    })
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def lookup_view(request: HttpRequest) -> HttpResponse:
    from monaimetrics import runtime_settings
    rt = runtime_settings.load()

    symbol = request.GET.get("symbol", "").strip().upper()
    data = None

    if symbol:
        data = get_symbol_data(symbol, rt.risk_profile)

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
def scan_view(request: HttpRequest) -> HttpResponse:
    from monaimetrics import runtime_settings
    rt = runtime_settings.load()

    symbols_raw = request.GET.get("symbols", "").strip().upper()
    symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()] if symbols_raw else None
    data = scan_for_opportunities(rt.risk_profile, symbols)
    response = render(request, "dashboard/scan.html", {
        "data": data,
        "symbols_input": symbols_raw,
    })
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def backtest_view(request: HttpRequest) -> HttpResponse:
    from monaimetrics import runtime_settings
    rt = runtime_settings.load()

    result = None
    symbols_input = ""
    start_date = "2024-01-01"
    end_date = "2024-12-31"
    initial_capital = 100000
    max_positions = 10
    risk_profile = rt.risk_profile

    if request.method == "POST":
        symbols_input = request.POST.get("symbols", "").strip().upper()
        start_date = request.POST.get("start_date", start_date)
        end_date = request.POST.get("end_date", end_date)
        risk_profile = request.POST.get("risk_profile", risk_profile)

        try:
            initial_capital = float(request.POST.get("initial_capital", 100000))
        except (ValueError, TypeError):
            pass
        try:
            max_positions = int(request.POST.get("max_positions", 10))
        except (ValueError, TypeError):
            pass

        symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]
        if symbols:
            result = run_web_backtest(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                risk_profile=risk_profile,
                max_positions=max_positions,
            )

    info = get_backtest_info()

    context = {
        "result": result,
        "symbols_input": symbols_input,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": int(initial_capital),
        "max_positions": max_positions,
        "risk_profile": risk_profile,
        "info": info,
    }

    # Pass equity curve as JSON for the chart
    if result and result.get("equity_curve"):
        context["result"]["equity_curve_json"] = json.dumps(result["equity_curve"])

    response = render(request, "dashboard/backtest.html", context)
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def notifications_view(request: HttpRequest) -> HttpResponse:
    from monaimetrics import notifications

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "mark_all_read":
            notifications.mark_all_read()
        elif action == "mark_read":
            nid = request.POST.get("notification_id", "")
            if nid:
                notifications.mark_read([nid])
        return redirect("notifications")

    all_notifs = notifications.get_notifications(limit=100)
    read_ids = notifications._get_read_ids()

    for n in all_notifs:
        n["is_read"] = n.get("id", "") in read_ids
        ts = n.get("ts", "")
        if ts:
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(ts)
                n["ts_display"] = dt.strftime("%H:%M:%S")
                n["date_display"] = dt.strftime("%b %d")
            except Exception:
                n["ts_display"] = ts[:19]
                n["date_display"] = ""

    all_notifs.reverse()

    response = render(request, "dashboard/notifications.html", {
        "notifications": all_notifs,
        "unread_count": notifications.unread_count(),
    })
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def journal_view(request: HttpRequest) -> HttpResponse:
    from monaimetrics import trade_journal

    event_type = request.GET.get("type", "").strip().upper() or None
    symbol = request.GET.get("symbol", "").strip().upper() or None

    events = trade_journal.read_events(
        event_type=event_type,
        symbol=symbol,
        limit=200,
    )

    for event in events:
        ts = event.get("ts", "")
        if ts:
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(ts)
                event["ts_display"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                event["ts_display"] = ts[:19]

    events.reverse()

    response = render(request, "dashboard/journal.html", {
        "events": events,
        "filter_type": event_type or "",
        "filter_symbol": symbol or "",
    })
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def api_unread_count(request: HttpRequest) -> JsonResponse:
    from monaimetrics import notifications
    return JsonResponse({"unread": notifications.unread_count()})


@login_required
def allocation_preview_api(request: HttpRequest) -> JsonResponse:
    profile = request.GET.get("profile", "moderate")
    table = get_allocation_for_profile(profile)
    return JsonResponse(table)


_plan_running = False


@login_required
@require_http_methods(["POST"])
def plan_trigger_view(request: HttpRequest) -> JsonResponse:
    global _plan_running
    if _plan_running:
        return JsonResponse({"status": "already_running",
                             "message": "A plan is already being generated. Check back in a few minutes."})

    import threading

    def _run():
        global _plan_running
        try:
            from monaimetrics.scheduler import run_planning_job
            run_planning_job()
        finally:
            _plan_running = False

    _plan_running = True
    threading.Thread(target=_run, daemon=True).start()
    return JsonResponse({"status": "started",
                         "message": "Plan generation started — scanning the full universe. "
                                    "This takes several minutes. Refresh the page to see results."})


@login_required
def plan_view(request: HttpRequest) -> HttpResponse:
    plan = _trade_journal.load_latest_plan()

    # Format the generated_at timestamp for display
    generated_display = None
    session_label = None
    if plan:
        try:
            from datetime import datetime, timezone
            import pytz
            dt = datetime.fromisoformat(plan["generated_at"])
            et = pytz.timezone("America/New_York")
            dt_et = dt.astimezone(et)
            generated_display = dt_et.strftime("%A %b %-d, %Y at %-I:%M %p ET")
        except Exception:
            generated_display = plan.get("generated_at", "")
        session_label = plan.get("session", "").replace("-", " ").title()

    return render(request, "dashboard/plan.html", {
        "plan": plan,
        "generated_display": generated_display,
        "session_label": session_label,
    })
