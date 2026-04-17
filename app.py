"""Streamlit dashboard for the paper-trading bot snapshots."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import streamlit as st


APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR
DEFAULT_DASHBOARD_API_URL = os.getenv("BOT_DASHBOARD_API_URL", "http://127.0.0.1:8765/api/status")
DEFAULT_PUBLIC_STATUS_JSON_URL = os.getenv("BOT_STATUS_JSON_URL", "").strip()
MANUAL_PORTFOLIO_PATH = APP_DIR / "paper_portfolio_manual.json"


def _discover_default_reports_dir() -> Path:
    candidates = [
        ROOT / "reports",
        Path.cwd() / "reports",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return ROOT / "reports"


DEFAULT_REPORTS_DIR = _discover_default_reports_dir()
BUNDLED_STATUS_PATH = APP_DIR / "cloud" / "status.json"


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def _load_uploaded_json(uploaded_file: Any) -> dict[str, Any]:
    payload = json.loads(uploaded_file.getvalue().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Uploaded JSON must be an object.")
    return payload


def _load_remote_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Remote response must be a JSON object.")
    return payload


def _fmt_money(value: Any) -> str:
    if value is None:
        return "-"
    return f"${float(value):,.2f}"


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}"


def _fmt_pct(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}%"


def _parse_timestamp(value: Any) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(str(value)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(value)


def _resolve_local_snapshot() -> tuple[dict[str, Any], str]:
    reports_dir = Path(os.getenv("BOT_REPORTS_DIR", str(DEFAULT_REPORTS_DIR)))
    status_path = reports_dir / "status.json"
    return _load_json_file(status_path), str(status_path)


def _resolve_dashboard_api_payload(api_url: str | None = None) -> tuple[dict[str, Any], str]:
    api_url = (api_url or os.getenv("BOT_DASHBOARD_API_URL", DEFAULT_DASHBOARD_API_URL)).strip()
    if not api_url:
        raise ValueError("BOT_DASHBOARD_API_URL is not set.")
    return _load_remote_json(api_url), api_url


def _resolve_public_status_payload(status_url: str | None = None) -> tuple[dict[str, Any], str]:
    status_url = (status_url or os.getenv("BOT_STATUS_JSON_URL", DEFAULT_PUBLIC_STATUS_JSON_URL)).strip()
    if not status_url:
        raise ValueError("BOT_STATUS_JSON_URL is not set.")
    return _load_remote_json(status_url), status_url


def _resolve_bundled_snapshot() -> tuple[dict[str, Any], str]:
    candidates = [BUNDLED_STATUS_PATH, APP_DIR / "status.json"]
    for candidate in candidates:
        if candidate.exists():
            return _load_json_file(candidate), str(candidate)
    raise FileNotFoundError("No bundled snapshot found.")


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "snapshot" in payload and isinstance(payload.get("snapshot"), dict):
        return payload
    return {
        "bot": {},
        "snapshot": payload,
        "logs": {},
    }


def _build_equity_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in snapshot.get("portfolio_history", []):
        timestamp = point.get("timestamp")
        equity = point.get("equity")
        if timestamp is None or equity is None:
            continue
        rows.append({"timestamp": _parse_timestamp(timestamp), "equity": float(equity)})
    return rows


def _extract_price_map(snapshot: dict[str, Any]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for item in snapshot.get("evaluations", []):
        symbol = item.get("symbol")
        last_close = item.get("last_close")
        if symbol and last_close is not None:
            prices[str(symbol)] = float(last_close)
    for item in snapshot.get("positions", []):
        symbol = item.get("symbol")
        last_price = item.get("last_price")
        if symbol and last_price is not None and symbol not in prices:
            prices[str(symbol)] = float(last_price)
    return prices


def _load_manual_portfolio(starting_cash: float) -> dict[str, Any]:
    if not MANUAL_PORTFOLIO_PATH.exists():
        return {
            "starting_cash": float(starting_cash),
            "cash": float(starting_cash),
            "positions": {},
            "orders": [],
            "portfolio_history": [],
        }
    payload = _load_json_file(MANUAL_PORTFOLIO_PATH)
    payload.setdefault("starting_cash", float(starting_cash))
    payload.setdefault("cash", float(starting_cash))
    payload.setdefault("positions", {})
    payload.setdefault("orders", [])
    payload.setdefault("portfolio_history", [])
    return payload


def _save_manual_portfolio(portfolio: dict[str, Any]) -> None:
    MANUAL_PORTFOLIO_PATH.write_text(json.dumps(portfolio, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_history_point(portfolio: dict[str, Any], prices: dict[str, float]) -> None:
    exposure = 0.0
    for symbol, position in portfolio.get("positions", {}).items():
        qty = float(position.get("qty", 0.0))
        last_price = float(prices.get(symbol, position.get("avg_entry_price", 0.0)))
        exposure += qty * last_price
    equity = float(portfolio.get("cash", 0.0)) + exposure
    portfolio.setdefault("portfolio_history", []).append(
        {
            "timestamp": datetime.now().astimezone().isoformat(),
            "equity": round(equity, 2),
            "cash": round(float(portfolio.get("cash", 0.0)), 2),
            "exposure": round(exposure, 2),
        }
    )
    portfolio["portfolio_history"] = portfolio["portfolio_history"][-300:]


def _build_manual_snapshot(snapshot: dict[str, Any], portfolio: dict[str, Any], prices: dict[str, float]) -> dict[str, Any]:
    manual_snapshot = dict(snapshot)
    positions_rows: list[dict[str, Any]] = []
    exposure = 0.0
    for symbol, position in portfolio.get("positions", {}).items():
        qty = float(position.get("qty", 0.0))
        avg_entry_price = float(position.get("avg_entry_price", 0.0))
        last_price = float(prices.get(symbol, avg_entry_price))
        market_value = round(qty * last_price, 2)
        exposure += market_value
        positions_rows.append(
            {
                "symbol": symbol,
                "qty": qty,
                "avg_entry_price": avg_entry_price,
                "last_price": last_price,
                "market_value": market_value,
                "unrealized_pnl": round((last_price - avg_entry_price) * qty, 2),
                "opened_at": position.get("opened_at"),
            }
        )
    equity = round(float(portfolio.get("cash", 0.0)) + exposure, 2)
    daily_pnl = round(equity - float(portfolio.get("starting_cash", equity)), 2)
    starting_cash = float(portfolio.get("starting_cash", equity)) or 1.0
    manual_snapshot["trading_mode"] = "paper_manual"
    manual_snapshot["positions"] = positions_rows
    manual_snapshot["orders"] = portfolio.get("orders", [])[-50:]
    manual_snapshot["portfolio_history"] = portfolio.get("portfolio_history", [])
    manual_snapshot["account"] = {
        "equity": equity,
        "cash": round(float(portfolio.get("cash", 0.0)), 2),
        "current_exposure": round(exposure, 2),
        "trading_blocked": False,
        "daily_pnl": daily_pnl,
        "daily_pnl_pct": round((daily_pnl / starting_cash) * 100.0, 2),
    }
    notes = list(snapshot.get("notes", []))
    notes.insert(0, "Manual paper trading is enabled in this Streamlit app.")
    manual_snapshot["notes"] = notes
    manual_snapshot["generated_at"] = datetime.now().astimezone().isoformat()
    return manual_snapshot


def _buy_position(portfolio: dict[str, Any], *, symbol: str, qty: float, price: float) -> str:
    notional = round(qty * price, 2)
    cash = float(portfolio.get("cash", 0.0))
    if qty <= 0:
        return "Buy quantity must be greater than zero."
    if notional > cash:
        return "Not enough cash for that buy order."
    timestamp = datetime.now().astimezone().isoformat()
    positions = portfolio.setdefault("positions", {})
    existing = positions.get(symbol)
    if existing:
        existing_qty = float(existing.get("qty", 0.0))
        existing_avg = float(existing.get("avg_entry_price", 0.0))
        new_qty = existing_qty + qty
        new_avg = ((existing_qty * existing_avg) + (qty * price)) / new_qty
        existing["qty"] = new_qty
        existing["avg_entry_price"] = round(new_avg, 4)
    else:
        positions[symbol] = {
            "qty": qty,
            "avg_entry_price": round(price, 4),
            "opened_at": timestamp,
        }
    portfolio["cash"] = round(cash - notional, 2)
    portfolio.setdefault("orders", []).append(
        {
            "submitted_at": timestamp,
            "symbol": symbol,
            "side": "buy",
            "status": "filled",
            "filled_qty": qty,
            "filled_avg_price": round(price, 4),
            "notional": notional,
            "realized_pnl": None,
        }
    )
    portfolio["orders"] = portfolio["orders"][-100:]
    return f"Bought {qty:.4f} {symbol} at ${price:.2f}."


def _sell_position(portfolio: dict[str, Any], *, symbol: str, qty: float, price: float) -> str:
    positions = portfolio.setdefault("positions", {})
    existing = positions.get(symbol)
    if existing is None:
        return f"No open position exists for {symbol}."
    held_qty = float(existing.get("qty", 0.0))
    if qty <= 0:
        return "Sell quantity must be greater than zero."
    if qty > held_qty:
        return f"Cannot sell {qty:.4f}; only {held_qty:.4f} is available."
    avg_entry_price = float(existing.get("avg_entry_price", 0.0))
    notional = round(qty * price, 2)
    realized_pnl = round((price - avg_entry_price) * qty, 2)
    portfolio["cash"] = round(float(portfolio.get("cash", 0.0)) + notional, 2)
    remaining_qty = held_qty - qty
    if remaining_qty <= 1e-9:
        positions.pop(symbol, None)
    else:
        existing["qty"] = remaining_qty
    timestamp = datetime.now().astimezone().isoformat()
    portfolio.setdefault("orders", []).append(
        {
            "submitted_at": timestamp,
            "symbol": symbol,
            "side": "sell",
            "status": "filled",
            "filled_qty": qty,
            "filled_avg_price": round(price, 4),
            "notional": notional,
            "realized_pnl": realized_pnl,
        }
    )
    portfolio["orders"] = portfolio["orders"][-100:]
    return f"Sold {qty:.4f} {symbol} at ${price:.2f}."


def _resolve_default_payload() -> tuple[dict[str, Any], str]:
    """Load one dashboard result using a best-effort fallback chain."""

    if DEFAULT_PUBLIC_STATUS_JSON_URL:
        try:
            payload, source_label = _resolve_public_status_payload()
            return _normalize_payload(payload), f"Public status JSON: {source_label}"
        except Exception:
            pass

    try:
        payload, source_label = _resolve_dashboard_api_payload()
        return _normalize_payload(payload), f"Dashboard API: {source_label}"
    except Exception:
        pass

    try:
        snapshot, source_label = _resolve_local_snapshot()
        return _normalize_payload(snapshot), f"Local status.json: {source_label}"
    except Exception:
        pass

    snapshot, source_label = _resolve_bundled_snapshot()
    return _normalize_payload(snapshot), f"Bundled snapshot: {source_label}"


def _resolve_local_snapshot_from_dir(reports_dir: str) -> tuple[dict[str, Any], str]:
    status_path = Path(reports_dir).expanduser() / "status.json"
    return _load_json_file(status_path), str(status_path)


def _resolve_payload_for_mode(
    mode: str,
    *,
    uploaded_file: Any | None = None,
    status_url: str | None = None,
    api_url: str | None = None,
    reports_dir: str | None = None,
) -> tuple[dict[str, Any], str]:
    if mode == "Auto":
        return _resolve_default_payload()
    if mode == "Uploaded JSON":
        if uploaded_file is None:
            raise ValueError("Upload a status.json file in the sidebar first.")
        return _normalize_payload(_load_uploaded_json(uploaded_file)), "Uploaded status.json"
    if mode == "Public JSON URL":
        payload, source_label = _resolve_public_status_payload(status_url)
        return _normalize_payload(payload), f"Public status JSON: {source_label}"
    if mode == "Dashboard API":
        payload, source_label = _resolve_dashboard_api_payload(api_url)
        return _normalize_payload(payload), f"Dashboard API: {source_label}"
    if mode == "Local reports/status.json":
        target_reports_dir = reports_dir or os.getenv("BOT_REPORTS_DIR", str(DEFAULT_REPORTS_DIR))
        snapshot, source_label = _resolve_local_snapshot_from_dir(target_reports_dir)
        return _normalize_payload(snapshot), f"Local status.json: {source_label}"
    if mode == "Bundled cloud snapshot":
        snapshot, source_label = _resolve_bundled_snapshot()
        return _normalize_payload(snapshot), f"Bundled snapshot: {source_label}"
    raise ValueError(f"Unsupported source mode: {mode}")


def main() -> None:
    st.set_page_config(
        page_title="Paper Trading Dashboard",
        page_icon="📈",
        layout="wide",
    )
    st.title("Paper Trading Dashboard")
    st.caption("Streamlit view of the paper-trading dashboard.")

    st.sidebar.header("Data Source")
    source_mode = st.sidebar.selectbox(
        "Load from",
        [
            "Auto",
            "Uploaded JSON",
            "Public JSON URL",
            "Dashboard API",
            "Local reports/status.json",
            "Bundled cloud snapshot",
        ],
        index=0,
    )
    uploaded_file = None
    status_url = None
    api_url = None
    reports_dir = None

    if source_mode == "Uploaded JSON":
        uploaded_file = st.sidebar.file_uploader("Upload status.json", type=["json"])
    elif source_mode == "Public JSON URL":
        status_url = st.sidebar.text_input("BOT_STATUS_JSON_URL", value=DEFAULT_PUBLIC_STATUS_JSON_URL)
    elif source_mode == "Dashboard API":
        api_url = st.sidebar.text_input("BOT_DASHBOARD_API_URL", value=DEFAULT_DASHBOARD_API_URL)
    elif source_mode == "Local reports/status.json":
        reports_dir = st.sidebar.text_input(
            "Reports directory",
            value=os.getenv("BOT_REPORTS_DIR", str(DEFAULT_REPORTS_DIR)),
        )

    try:
        payload, source_label = _resolve_payload_for_mode(
            source_mode,
            uploaded_file=uploaded_file,
            status_url=status_url,
            api_url=api_url,
            reports_dir=reports_dir,
        )
    except Exception as exc:
        st.error(f"Failed to load dashboard data: {exc}")
        st.stop()

    snapshot = payload.get("snapshot", {})
    bot = payload.get("bot", {})
    logs = payload.get("logs", {})
    prices = _extract_price_map(snapshot)
    starting_cash = float(snapshot.get("account", {}).get("equity", 10000.0) or 10000.0)
    portfolio = _load_manual_portfolio(starting_cash)

    st.sidebar.header("Paper Trading")
    tradeable_symbols = sorted(prices) or sorted({str(item.get("symbol")) for item in snapshot.get("evaluations", []) if item.get("symbol")})
    selected_symbol = st.sidebar.selectbox("Symbol", tradeable_symbols if tradeable_symbols else ["-"])
    selected_price = float(prices.get(selected_symbol, 0.0)) if selected_symbol != "-" else 0.0
    st.sidebar.caption(f"Last price: {_fmt_money(selected_price) if selected_price else '-'}")
    default_qty = 1.0
    if selected_symbol in portfolio.get("positions", {}) and selected_price > 0:
        default_qty = float(portfolio["positions"][selected_symbol].get("qty", 1.0))
    qty = st.sidebar.number_input("Quantity", min_value=0.0, value=default_qty, step=1.0)

    if st.sidebar.button("Buy", use_container_width=True, disabled=(selected_symbol == "-" or selected_price <= 0)):
        message = _buy_position(portfolio, symbol=selected_symbol, qty=float(qty), price=selected_price)
        if message.startswith("Bought"):
            st.sidebar.success(message)
            _append_history_point(portfolio, prices)
            _save_manual_portfolio(portfolio)
        else:
            st.sidebar.warning(message)
    if st.sidebar.button("Sell", use_container_width=True, disabled=(selected_symbol == "-" or selected_price <= 0)):
        message = _sell_position(portfolio, symbol=selected_symbol, qty=float(qty), price=selected_price)
        if message.startswith("Sold"):
            st.sidebar.success(message)
            _append_history_point(portfolio, prices)
            _save_manual_portfolio(portfolio)
        else:
            st.sidebar.warning(message)
    if st.sidebar.button("Reset Portfolio", use_container_width=True):
        portfolio = {
            "starting_cash": starting_cash,
            "cash": starting_cash,
            "positions": {},
            "orders": [],
            "portfolio_history": [],
        }
        _save_manual_portfolio(portfolio)
        st.sidebar.success("Manual paper portfolio was reset.")

    snapshot = _build_manual_snapshot(snapshot, portfolio, prices)
    account = snapshot.get("account", {})
    positions = snapshot.get("positions", [])
    orders = snapshot.get("orders", [])
    evaluations = snapshot.get("evaluations", [])
    notes = snapshot.get("notes", [])
    news_analysis = snapshot.get("news_analysis", {})
    generated_at = snapshot.get("generated_at")

    st.caption(f"Source: {source_label}")
    st.caption(f"Updated: {_parse_timestamp(generated_at)}")

    metric_cols = st.columns(5)
    metric_cols[0].metric("Equity", _fmt_money(account.get("equity")))
    metric_cols[1].metric("Cash", _fmt_money(account.get("cash")))
    metric_cols[2].metric("Exposure", _fmt_money(account.get("current_exposure")))
    metric_cols[3].metric("Daily P/L", _fmt_money(account.get("daily_pnl")), _fmt_pct(account.get("daily_pnl_pct")))
    metric_cols[4].metric("Leader", snapshot.get("leader_symbol", "-"), _fmt_num(snapshot.get("leader_score"), 4))

    status_cols = st.columns(4)
    status_cols[0].write(f"Mode: `{snapshot.get('trading_mode', '-')}`")
    status_cols[1].write(f"Strategy: `{snapshot.get('strategy_name', '-')}`")
    status_cols[2].write(f"Market Open: `{snapshot.get('market_open')}`")
    status_cols[3].write(f"Trading Blocked: `{account.get('trading_blocked')}`")

    bot_cols = st.columns(3)
    bot_cols[0].write(f"Bot Running: `{bot.get('running', '-')}`")
    bot_cols[1].write(f"Bot PID: `{bot.get('pid', '-')}`")
    bot_cols[2].write(f"Poll Interval: `{snapshot.get('poll_interval_seconds', '-')}` sec")

    equity_rows = _build_equity_rows(snapshot)
    st.subheader("Equity Curve")
    if equity_rows:
        st.line_chart(equity_rows, x="timestamp", y="equity", use_container_width=True)
    else:
        st.info("No portfolio history is available yet.")

    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("Open Positions")
        if positions:
            st.dataframe(
                [
                    {
                        "symbol": row.get("symbol"),
                        "qty": float(row.get("qty", 0.0)),
                        "avg_entry_price": float(row.get("avg_entry_price", 0.0)),
                        "last_price": float(row.get("last_price", 0.0)),
                        "market_value": float(row.get("market_value", 0.0)),
                        "unrealized_pnl": float(row.get("unrealized_pnl", 0.0)),
                        "opened_at": _parse_timestamp(row.get("opened_at")),
                    }
                    for row in positions
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No open positions.")

        st.subheader("Cycle Notes")
        if notes:
            for note in notes:
                st.write(f"- {note}")
        else:
            st.info("No notes were recorded.")

    with right_col:
        st.subheader("Recent Orders")
        if orders:
            st.dataframe(
                [
                    {
                        "submitted_at": _parse_timestamp(order.get("submitted_at")),
                        "symbol": order.get("symbol"),
                        "side": order.get("side"),
                        "status": order.get("status"),
                        "filled_qty": float(order.get("filled_qty", 0.0)),
                        "filled_avg_price": float(order.get("filled_avg_price", 0.0)),
                        "notional": float(order.get("notional", 0.0)),
                        "realized_pnl": order.get("realized_pnl"),
                    }
                    for order in orders
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No recent orders.")

        st.subheader("News Summary")
        if news_analysis:
            st.write(news_analysis.get("summary", "No summary available."))
            warnings = news_analysis.get("warnings", [])
            if warnings:
                for warning in warnings:
                    st.warning(str(warning))
        else:
            st.info("No news analysis available.")

    st.subheader("Signal Evaluations")
    if evaluations:
        st.dataframe(
            [
                {
                    "symbol": item.get("symbol"),
                    "action": item.get("action"),
                    "score": float(item.get("score", 0.0)),
                    "momentum_return": float(item.get("momentum_return", 0.0)),
                    "fast_ma": float(item.get("fast_ma", 0.0)),
                    "slow_ma": float(item.get("slow_ma", 0.0)),
                    "last_close": float(item.get("last_close", 0.0)),
                    "reason": item.get("reason"),
                }
                for item in evaluations
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No evaluations are available in this snapshot.")

    st.subheader("Bot Logs")
    stderr_lines = logs.get("stderr", []) if isinstance(logs, dict) else []
    stdout_lines = logs.get("stdout", []) if isinstance(logs, dict) else []
    if stderr_lines or stdout_lines:
        tab_err, tab_out = st.tabs(["stderr", "stdout"])
        with tab_err:
            st.code("\n".join(str(line) for line in stderr_lines) or "No stderr lines.", language="text")
        with tab_out:
            st.code("\n".join(str(line) for line in stdout_lines) or "No stdout lines.", language="text")
    else:
        st.info("No log lines are available from this data source.")

    with st.expander("Raw JSON Snapshot"):
        st.json(payload)


if __name__ == "__main__":
    main()
