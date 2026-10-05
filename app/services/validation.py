"""Deterministic cross-document validation for Purchase Order, Invoice and Payment Request.

This module never uses an LLM. Findings are risk flags for human review, not a fraud verdict.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
import re


@dataclass
class Finding:
    rule_id: str
    severity: str  # HIGH, MEDIUM, LOW, INFO
    status: str    # FAIL, REVIEW, PASS
    message: str
    documents: list[str]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _value(doc: dict[str, Any] | None, key: str, default=None):
    if not doc:
        return default
    value = doc.get(key, default)
    # Support both plain values and {"value": ..., "evidence": [...]} wrappers.
    if isinstance(value, dict) and "value" in value:
        return value.get("value", default)
    return value


def _number(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))
        cleaned = re.sub(r"[^0-9,.-]", "", str(value)).strip()
        if not cleaned:
            return None
        # Vietnamese samples use dot/comma as thousands separators. Decimal point is
        # retained only when there is one separator followed by 1-2 digits.
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(",", "") if cleaned.rfind(".") > cleaned.rfind(",") else cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            tail = cleaned.rsplit(",", 1)[-1]
            cleaned = cleaned.replace(",", ".") if len(tail) <= 2 else cleaned.replace(",", "")
        elif "." in cleaned:
            tail = cleaned.rsplit(".", 1)[-1]
            if len(tail) > 2:
                cleaned = cleaned.replace(".", "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _doc_type(doc: dict[str, Any] | None) -> str:
    return str(_value(doc, "document_type", "unknown") or "unknown").lower()


def _items(doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    value = _value(doc, "items", []) or []
    return value if isinstance(value, list) else []


def _bank(doc: dict[str, Any] | None) -> dict[str, Any]:
    value = _value(doc, "bank_details", {}) or {}
    return value if isinstance(value, dict) else {}


def validate_documents(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate extracted JSON dictionaries; missing documents are allowed."""
    by_type: dict[str, dict[str, Any]] = {}
    for doc in documents:
        dtype = _doc_type(doc)
        if dtype in {"purchase_order", "invoice", "payment_request"}:
            by_type[dtype] = doc

    po = by_type.get("purchase_order")
    inv = by_type.get("invoice")
    pr = by_type.get("payment_request")
    findings: list[Finding] = []

    def add(rule_id, severity, status, message, docs, evidence):
        findings.append(Finding(rule_id, severity, status, message, docs, evidence))

    # Missing document/critical fields should be review items, not silently treated as zero.
    for dtype, doc in (("purchase_order", po), ("invoice", inv), ("payment_request", pr)):
        if doc is None:
            add("DOC-001", "MEDIUM", "REVIEW", f"Thiếu chứng từ {dtype} trong bộ hồ sơ.", [dtype], {})
            continue
        critical = {
            "purchase_order": ["document_number", "buyer", "seller", "currency", "total_amount", "items"],
            "invoice": ["document_number", "po_number", "buyer", "seller", "currency", "total_amount", "items"],
            "payment_request": ["document_number", "po_number", "invoice_number", "requested_payment_amount", "bank_details"],
        }[dtype]
        missing = []
        for field in critical:
            value = _value(doc, field)
            if value is None or value == "" or (field == "items" and not value):
                missing.append(field)
        add("FIELD-001", "LOW" if not missing else "MEDIUM", "PASS" if not missing else "REVIEW",
            f"Các trường bắt buộc của {dtype}: " + ("đã có đủ." if not missing else "thiếu " + ", ".join(missing) + "."),
            [dtype], {"missing_fields": missing})

    # References should line up across the documents.
    po_no = _value(po, "document_number") if po else None
    inv_po = _value(inv, "po_number") if inv else None
    pr_po = _value(pr, "po_number") if pr else None
    inv_no = _value(inv, "document_number") if inv else None
    pr_inv = _value(pr, "invoice_number") if pr else None

    for rule, label, a, b, docs in [
        ("REF-PO-001", "PO number giữa PO và Invoice", po_no, inv_po, ["purchase_order", "invoice"]),
        ("REF-PO-002", "PO number giữa PO và Payment Request", po_no, pr_po, ["purchase_order", "payment_request"]),
        ("REF-INV-001", "Invoice number giữa Invoice và Payment Request", inv_no, pr_inv, ["invoice", "payment_request"]),
    ]:
        if a and b:
            ok = _norm_text(a) == _norm_text(b)
            add(rule, "HIGH" if not ok else "LOW", "PASS" if ok else "FAIL",
                f"{label} {'khớp' if ok else 'không khớp'}.", docs, {"left": a, "right": b})
        else:
            add(rule, "MEDIUM", "REVIEW", f"Không đủ dữ liệu để đối chiếu {label}.", docs, {"left": a, "right": b})

    # Buyer/seller consistency (compare names only; do not infer legal equivalence).
    for party in ("buyer", "seller"):
        values = [(dtype, _value(doc, party, {}) or {}) for dtype, doc in (("purchase_order", po), ("invoice", inv), ("payment_request", pr)) if doc]
        names = [(dtype, v.get("name") if isinstance(v, dict) else None) for dtype, v in values]
        names = [(dtype, name) for dtype, name in names if name]
        if len(names) >= 2:
            distinct = { _norm_text(name) for _, name in names }
            ok = len(distinct) == 1
            add(f"PARTY-{party.upper()}-001", "MEDIUM" if not ok else "LOW", "PASS" if ok else "REVIEW",
                f"Tên {party} {'nhất quán' if ok else 'khác nhau giữa các chứng từ; cần xác minh'}.",
                [dtype for dtype, _ in names], {dtype: name for dtype, name in names})

    # Compare item quantities and line totals by SKU.
    if po and inv:
        po_items = {str(x.get("sku") or "").strip().upper(): x for x in _items(po) if x.get("sku")}
        inv_items = {str(x.get("sku") or "").strip().upper(): x for x in _items(inv) if x.get("sku")}
        for sku in sorted(set(po_items) | set(inv_items)):
            p_item, i_item = po_items.get(sku), inv_items.get(sku)
            if p_item is None or i_item is None:
                add("ITEM-001", "HIGH", "FAIL", f"Mã hàng {sku} chỉ xuất hiện ở một trong PO/Invoice.",
                    ["purchase_order", "invoice"], {"sku": sku, "in_po": p_item is not None, "in_invoice": i_item is not None})
                continue
            pq, iq = _number(p_item.get("quantity")), _number(i_item.get("quantity"))
            if pq is not None and iq is not None:
                ok = pq == iq
                add("ITEM-QTY-001", "HIGH" if not ok else "LOW", "PASS" if ok else "FAIL",
                    f"Số lượng mã {sku} {'khớp' if ok else 'không khớp'} giữa PO và Invoice.",
                    ["purchase_order", "invoice"], {"sku": sku, "po_quantity": str(pq), "invoice_quantity": str(iq)})
            else:
                add("ITEM-QTY-001", "MEDIUM", "REVIEW", f"Thiếu số lượng để đối chiếu mã {sku}.",
                    ["purchase_order", "invoice"], {"sku": sku, "po_quantity": str(pq), "invoice_quantity": str(iq)})

    # Line arithmetic: quantity * unit price should approximately equal line total.
    for dtype, doc in (("purchase_order", po), ("invoice", inv)):
        if not doc:
            continue
        for idx, item in enumerate(_items(doc), start=1):
            qty, unit_price, line_total = (_number(item.get(k)) for k in ("quantity", "unit_price", "line_total"))
            if qty is None or unit_price is None or line_total is None:
                continue
            expected = qty * unit_price
            if abs(expected - line_total) > Decimal("1"):
                add("MATH-LINE-001", "MEDIUM", "REVIEW",
                    f"Thành tiền dòng {idx} ({item.get('sku') or 'không mã'}) không bằng số lượng × đơn giá trong {dtype}.",
                    [dtype], {"sku": item.get("sku"), "quantity": str(qty), "unit_price": str(unit_price),
                              "expected_line_total": str(expected), "extracted_line_total": str(line_total)})

    # Totals across documents.
    po_total = _number(_value(po, "total_amount")) if po else None
    inv_total = _number(_value(inv, "total_amount")) if inv else None
    pr_invoice_amount = _number(_value(pr, "total_amount")) if pr else None
    requested = _number(_value(pr, "requested_payment_amount")) if pr else None
    paid = _number(_value(pr, "amount_already_paid")) if pr else None

    if po_total is not None and inv_total is not None:
        ok = po_total == inv_total
        add("AMOUNT-PO-INV-001", "HIGH" if not ok else "LOW", "PASS" if ok else "FAIL",
            f"Tổng tiền PO và Invoice {'khớp' if ok else 'không khớp'}.", ["purchase_order", "invoice"],
            {"po_total": str(po_total), "invoice_total": str(inv_total), "difference": str(inv_total - po_total)})

    if inv_total is not None and pr_invoice_amount is not None:
        ok = inv_total == pr_invoice_amount
        add("AMOUNT-INV-PR-001", "HIGH" if not ok else "LOW", "PASS" if ok else "FAIL",
            f"Giá trị hóa đơn trên Payment Request {'khớp' if ok else 'không khớp'} với Invoice total.",
            ["invoice", "payment_request"], {"invoice_total": str(inv_total), "pr_invoice_amount": str(pr_invoice_amount)})

    if requested is not None and pr_invoice_amount is not None and paid is not None:
        expected_payable = pr_invoice_amount - paid
        ok = requested == expected_payable
        add("AMOUNT-PR-001", "HIGH" if not ok else "LOW", "PASS" if ok else "FAIL",
            f"Số tiền đề nghị {'khớp' if ok else 'không khớp'} với giá trị hóa đơn trừ số đã thanh toán.",
            ["payment_request"], {"invoice_amount_on_pr": str(pr_invoice_amount), "already_paid": str(paid),
                                  "expected_requested_amount": str(expected_payable), "requested_amount": str(requested)})

    # Beneficiary account should match supplier bank details from PO/Invoice.
    source_banks = [(dtype, _bank(doc)) for dtype, doc in (("purchase_order", po), ("invoice", inv)) if doc]
    pr_bank = _bank(pr) if pr else {}
    source_accounts = [(dtype, str(b.get("account_number"))) for dtype, b in source_banks if b.get("account_number")]
    pr_account = pr_bank.get("account_number")
    if source_accounts and pr_account:
        all_match = all(_norm_text(account) == _norm_text(pr_account) for _, account in source_accounts)
        add("BANK-001", "HIGH" if not all_match else "LOW", "PASS" if all_match else "FAIL",
            "Số tài khoản thụ hưởng trên Payment Request " + ("khớp" if all_match else "khác với PO/Invoice; cần xác minh độc lập trước khi thanh toán"),
            [dtype for dtype, _ in source_accounts] + ["payment_request"],
            {"source_accounts": dict(source_accounts), "payment_request_account": str(pr_account)})
    else:
        add("BANK-001", "HIGH", "REVIEW", "Thiếu số tài khoản ở một hoặc nhiều chứng từ nên chưa thể đối chiếu.",
            ["purchase_order", "invoice", "payment_request"], {"source_accounts": dict(source_accounts), "payment_request_account": pr_account})

    # Account name should agree with the supplier name when available.
    supplier = _value(inv, "seller", {}) if inv else (_value(po, "seller", {}) if po else {})
    supplier_name = supplier.get("name") if isinstance(supplier, dict) else None
    pr_account_name = pr_bank.get("account_name")
    if supplier_name and pr_account_name:
        ok = _norm_text(supplier_name) == _norm_text(pr_account_name)
        add("BANK-NAME-001", "HIGH" if not ok else "LOW", "PASS" if ok else "FAIL",
            "Tên chủ tài khoản trên Payment Request " + ("khớp với nhà cung cấp" if ok else "khác tên nhà cung cấp; cần xác minh"),
            ["invoice" if inv else "purchase_order", "payment_request"],
            {"supplier_name": supplier_name, "payment_request_account_name": pr_account_name})

    # Approval state is a workflow flag, not a financial discrepancy.
    pending = []
    for step in (_value(pr, "approvals", []) or []) if pr else []:
        status = _norm_text(step.get("status")) if isinstance(step, dict) else ""
        if status and any(word in status for word in ("pending", "chờ", "awaiting")):
            pending.append({"role": step.get("role"), "person": step.get("person"), "status": step.get("status")})
    if pending:
        add("APPROVAL-001", "MEDIUM", "REVIEW", "Có bước phê duyệt chưa hoàn tất; chưa nên xem hồ sơ là sẵn sàng thanh toán.",
            ["payment_request"], {"pending_steps": pending})

    counts = {s: sum(1 for f in findings if f.status == s) for s in ("FAIL", "REVIEW", "PASS")}
    risk = "HIGH" if any(f.severity == "HIGH" and f.status in {"FAIL", "REVIEW"} for f in findings) else (
        "MEDIUM" if any(f.status in {"FAIL", "REVIEW"} for f in findings) else "LOW")
    return {"risk_level": risk, "summary": counts, "findings": [f.to_dict() for f in findings],
            "disclaimer": "Đây là cờ cảnh báo dựa trên quy tắc, không phải kết luận gian lận. Cần người có thẩm quyền rà soát trước khi thanh toán."}
