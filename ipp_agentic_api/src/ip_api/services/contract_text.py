"""Format a stored contract payload as plain text (download fallback)."""

from __future__ import annotations

from typing import Any


def render_contract_text(payload: dict[str, Any]) -> str:
    products = payload.get("products") or []
    lines = [
        "SUPPLY CONTRACT (DUMMY)",
        "=" * 48,
        f"Contract Reference Number : {payload.get('contractReferenceNumber')}",
        f"Date                      : {payload.get('DATE')}",
        "",
        "LEGAL ENTITY",
        "-" * 48,
        f"Legal Name   : {payload.get('legalName')}",
        f"Code         : {payload.get('legalEntityCode')}",
        f"Address      : {payload.get('address')}",
        f"City         : {payload.get('city')}",
        f"Country      : {payload.get('country')}",
        f"Postal Code  : {payload.get('postalCode')}",
        f"Email        : {payload.get('email')}",
        f"Phone        : {payload.get('phone')}",
        f"Registration : {payload.get('registrationNumber')}",
        "",
        "PRICELIST / PRODUCTS",
        "-" * 48,
        f"Currency       : {payload.get('currency')}",
        f"Effective Date : {payload.get('effectiveDate')}",
        "",
        f"{'Code':<12} {'Description':<40} {'UOM':<6} {'Price':>8} {'Market':>8}",
    ]
    for product in products:
        lines.append(
            f"{str(product.get('productCode') or ''):<12} "
            f"{str(product.get('productDescription') or '')[:40]:<40} "
            f"{str(product.get('uom') or ''):<6} "
            f"{str(product.get('unitPrice') or ''):>8} "
            f"{str(product.get('marketPrice') or ''):>8}"
        )
    lines.extend(
        [
            "",
            "This is a dummy contract generated after human confirmation "
            "from SQLite legal-entity and pricelist data.",
        ]
    )
    return "\n".join(lines)
