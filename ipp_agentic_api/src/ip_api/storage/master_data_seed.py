"""Default legal/sales master-data rows (same values as document MCP seed)."""

from __future__ import annotations

LEGAL_PLACEHOLDER = "Legal_Department_Master_Data"
SALES_PLACEHOLDER = "Sales_Excellence_Master_Data"

DEFAULT_MASTER_DATA_ROWS: tuple[dict[str, str], ...] = (
    {
        "id": "md-legal-department",
        "placeholder_key": LEGAL_PLACEHOLDER,
        "category": "legal",
        "content": (
            "Legal Department\n"
            "200 Connell Drive, Suite 1000\n"
            "Berkeley Heights, NJ 07922\n"
            "E-mail: pmo@ABCTec.com"
        ),
    },
    {
        "id": "md-sales-excellence",
        "placeholder_key": SALES_PLACEHOLDER,
        "category": "sales",
        "content": (
            "Sales Excellence\n"
            "200 Connell Drive, Suite 1000\n"
            "Berkeley Heights, NJ 07922\n"
            "E-mail: pmo@ABCTec.com"
        ),
    },
)
