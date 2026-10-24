"""Render the loan agreement: Jinja2 (autoescaped) -> WeasyPrint PDF."""
from datetime import date

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, default_url_fetcher

from . import config

_env = Environment(loader=FileSystemLoader(str(config.TEMPLATES)),
                   autoescape=select_autoescape(["html"]))


def _safe_fetcher(url, *args, **kwargs):
    """Block http(s)/file fetches from templates (SSRF / local file read)."""
    if url.startswith("data:"):
        return default_url_fetcher(url)
    raise ValueError(f"blocked url: {url[:40]}")


def amortization(principal, months, annual_rate):
    r = annual_rate / 12
    payment = principal / months if r == 0 else principal * r / (1 - (1 + r) ** -months)
    balance, rows = principal, []
    for n in range(1, months + 1):
        interest = balance * r
        princ = payment - interest
        balance = max(balance - princ, 0)
        rows.append({"n": n, "payment": f"{payment:,.2f}", "interest": f"{interest:,.2f}",
                     "principal": f"{princ:,.2f}", "balance": f"{balance:,.2f}"})
    return payment, rows


def render_loan_pdf(loan, borrower):
    payment, schedule = amortization(loan["amount"], loan["months"], config.ANNUAL_RATE)
    html = _env.get_template("loan_agreement.html").render(
        loan_id=loan["loan_id"], date=date.today().isoformat(),
        borrower_name=borrower["full_name"], id_masked="*" * 4 + borrower["id_number"][-4:],
        amount=f"{loan['amount']:,.2f}", currency="TND", months=loan["months"],
        rate=f"{config.ANNUAL_RATE * 100:.1f}", payment=f"{payment:,.2f}",
        purpose=loan["purpose"] or "-", schedule=schedule,
    )
    return HTML(string=html, url_fetcher=_safe_fetcher).write_pdf()
