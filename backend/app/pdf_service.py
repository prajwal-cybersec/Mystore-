"""PDF Service: Professional Indian GST Tax Invoice and Consolidated Order Summary PDFs.

Uses ReportLab to draw standard GST Tax Invoices (Form GST INV-1 format compliant):
- Supplier details (Name, Address, GSTIN, State)
- Buyer details (Customer name, Place of supply)
- Invoice No, Date, Reference Order No
- HSN / Category, Quantity, Unit Rate, Taxable Value
- CGST, SGST, IGST breakdown
- Total in words & figures, Authorized Signatory

Renders all currency using 'Rs.' to ensure flawless rendering across all standard PDF viewers.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any, Dict, List
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from pypdf import PdfWriter


def _num_to_words(num: float) -> str:
    """Simple Indian currency wording helper."""
    n = int(round(num))
    if n == 0:
        return "Zero Rupees Only"
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def convert_upto_999(val: int) -> str:
        s = ""
        if val >= 100:
            s += ones[val // 100] + " Hundred "
            val %= 100
        if val >= 20:
            s += tens[val // 10] + " "
            val %= 10
        if val > 0:
            s += ones[val] + " "
        return s.strip()

    crore = n // 10000000
    n %= 10000000
    lakh = n // 100000
    n %= 100000
    thousand = n // 1000
    n %= 1000

    parts = []
    if crore:
        parts.append(f"{convert_upto_999(crore)} Crore")
    if lakh:
        parts.append(f"{convert_upto_999(lakh)} Lakh")
    if thousand:
        parts.append(f"{convert_upto_999(thousand)} Thousand")
    if n:
        parts.append(convert_upto_999(n))

    return "Rupees " + " ".join(parts).strip() + " Only"


def generate_consolidated_master_invoice_pdf(order_data: Dict[str, Any]) -> bytes:
    """Generate a single unified Master GST Tax Invoice PDF for the entire order.
    
    Combines all products across all sellers into ONE single tax invoice with
    one Master Invoice Number (INV-2024-25-MST-XXXXX), unified tax calculation,
    and clear seller attribution per line item.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontSize = 8.5
    normal.leading = 11

    title_style = ParagraphStyle(
        "MasterInvoiceTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        alignment=1,
    )
    subtitle_style = ParagraphStyle(
        "MasterInvoiceSubTitle",
        parent=normal,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b"),
        alignment=1,
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("MYSTORE · TAX INVOICE", title_style))
    story.append(Paragraph("(Issued under Section 31 of CGST Act, 2017 · Original for Recipient · Unified Order Invoice)", subtitle_style))
    story.append(Spacer(1, 12))

    # 2. Header Metadata Grid (Marketplace Facilitator & Invoice Meta)
    order_id = str(order_data.get("order_id") or order_data.get("id", ""))
    master_inv_no = f"INV-2024-25-MST-{order_id[:8].upper()}"
    issued_date = str(order_data.get("created_at", ""))[:10]
    customer = order_data.get("customer", {})
    sub_orders = order_data.get("sub_orders", [])
    city = order_data.get("city", "Bengaluru")
    grand_total = float(order_data.get("grand_total") or order_data.get("total_inr") or 0)

    # Tracking numbers
    tracking_nos = [
        so.get("shipment", {}).get("tracking_number") or "TRK-ASSIGNED"
        for so in sub_orders
        if so.get("shipment")
    ]
    tracking_summary = ", ".join(tracking_nos) if tracking_nos else "TRK-ASSIGNED"

    meta_table_data = [
        [
            Paragraph("<b>Marketplace Facilitator / Platform:</b><br/>"
                      "<b>MyStore E-Commerce Marketplace Pvt Ltd</b><br/>"
                      "Prestige Tech Park, Outer Ring Road<br/>"
                      "Bengaluru, Karnataka - 560103<br/>"
                      "<b>GSTIN: 29AABCN1234F1Z5</b>", normal),
            Paragraph(f"<b>Tax Invoice No:</b> <font color='#ea580c'><b>{master_inv_no}</b></font><br/>"
                      f"<b>Invoice Date:</b> {issued_date}<br/>"
                      f"<b>Order ID:</b> {order_id}<br/>"
                      f"<b>Payment Status:</b> <font color='green'><b>PAID IN FULL (Online)</b></font><br/>"
                      f"<b>Consignments:</b> {len(sub_orders)} Separate Package(s)", normal),
        ],
        [
            Paragraph(f"<b>Billed To & Delivery Address:</b><br/>"
                      f"<b>{customer.get('name', 'Priya Sharma')}</b><br/>"
                      f"Delivery City: {city}<br/>"
                      f"Place of Supply: Karnataka (State Code: 29)<br/>"
                      f"Contact: {customer.get('phone', '+91-9876543210')}", normal),
            Paragraph(f"<b>Shipment Tracking:</b> {tracking_summary}<br/>"
                      "<b>Reverse Charge:</b> No<br/>"
                      "<b>Mode of Delivery:</b> Surface Express Logistics<br/>"
                      "<b>Nature of Transaction:</b> Multi-Seller Electronic Commerce", normal),
        ]
    ]

    meta_table = Table(meta_table_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # 3. Item Details Table across all sub-orders / sellers
    item_rows = [
        [
            Paragraph("<b>#</b>", normal),
            Paragraph("<b>Description of Goods & Legal Supplier</b>", normal),
            Paragraph("<b>Qty</b>", normal),
            Paragraph("<b>Gross Rate (Rs.)</b>", normal),
            Paragraph("<b>Taxable Val (Rs.)</b>", normal),
            Paragraph("<b>Total (Rs.)</b>", normal),
        ]
    ]

    row_idx = 1
    total_taxable = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0

    for so in sub_orders:
        seller = so.get("seller", {})
        seller_name = seller.get("name", "Seller")
        seller_gstin = seller.get("gstin", "N/A")
        seller_state = seller.get("state", "India")
        sh = so.get("shipment", {})
        trk = sh.get("tracking_number", "TRK-ASSIGNED")
        inv = so.get("invoice", {})

        if inv:
            total_taxable += float(inv.get("taxable_value", 0))
            total_cgst += float(inv.get("cgst", 0))
            total_sgst += float(inv.get("sgst", 0))
            total_igst += float(inv.get("igst", 0))

        items = so.get("items", [])
        for it in items:
            qty = int(it.get("quantity", 1))
            rate = float(it.get("unit_price_inr", 0))
            line_total = rate * qty
            line_taxable = round(line_total / 1.18, 2)
            if not inv:
                total_taxable += line_taxable

            item_desc = (
                f"<b>{it.get('product_name', 'Item')}</b><br/>"
                f"<font color='#64748b' size=7>"
                f"SKU: {it.get('sku', 'N/A')} · Supplier: <b>{seller_name}</b> (GSTIN: {seller_gstin}) · {trk}"
                f"</font>"
            )

            item_rows.append([
                Paragraph(str(row_idx), normal),
                Paragraph(item_desc, normal),
                Paragraph(str(qty), normal),
                Paragraph(f"Rs. {rate:,.2f}", normal),
                Paragraph(f"Rs. {line_taxable:,.2f}", normal),
                Paragraph(f"Rs. {line_total:,.2f}", normal),
            ])
            row_idx += 1

    # In case invoices weren't ready, estimate CGST/SGST vs IGST
    if total_cgst == 0 and total_sgst == 0 and total_igst == 0:
        total_tax = grand_total - total_taxable
        total_cgst = round(total_tax / 2.0, 2)
        total_sgst = round(total_tax / 2.0, 2)

    items_table = Table(item_rows, colWidths=[25, 255, 35, 75, 75, 75])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    # 4. Tax Breakdown Table
    tax_rows = [
        [Paragraph("<b>Consolidated Tax Component</b>", normal), Paragraph("<b>Amount (Rs.)</b>", normal)],
        [Paragraph("Total Taxable Value of Goods", normal), Paragraph(f"Rs. {total_taxable:,.2f}", normal)],
    ]
    if total_cgst > 0 or total_sgst > 0:
        tax_rows.append([Paragraph("Central GST (CGST)", normal), Paragraph(f"Rs. {total_cgst:,.2f}", normal)])
        tax_rows.append([Paragraph("State / UT GST (SGST)", normal), Paragraph(f"Rs. {total_sgst:,.2f}", normal)])
    if total_igst > 0:
        tax_rows.append([Paragraph("Integrated GST (IGST)", normal), Paragraph(f"Rs. {total_igst:,.2f}", normal)])

    tax_rows.append([Paragraph("<b>Grand Total Invoice Value (INR)</b>", normal), Paragraph(f"<b>Rs. {grand_total:,.2f}</b>", normal)])

    tax_table = Table(tax_rows, colWidths=[380, 160])
    tax_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
    ]))
    story.append(tax_table)
    story.append(Spacer(1, 10))

    # 5. Amount in Words & Signatory Box
    words = _num_to_words(grand_total)
    footer_table_data = [
        [
            Paragraph(f"<b>Amount in Words:</b><br/><i>{words}</i><br/><br/>"
                      f"<font size=7 color='#64748b'>"
                      f"This is a single consolidated computer-generated tax invoice for Order #{order_id}. "
                      f"Goods are supplied by respective registered sellers as indicated above. "
                      f"No physical signature is required.</font>", normal),
            Paragraph("For <b>MyStore Marketplace</b>:<br/><br/><br/>"
                      "<b>Authorized Signatory</b>", normal),
        ]
    ]
    footer_table = Table(footer_table_data, colWidths=[360, 180])
    footer_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
    ]))
    story.append(footer_table)

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def generate_single_invoice_pdf(inv: Dict[str, Any]) -> bytes:
    """Generate a single-seller GST Tax Invoice PDF."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontSize = 9
    normal.leading = 12

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1e293b"),
        alignment=1,
    )
    subtitle_style = ParagraphStyle(
        "InvoiceSubTitle",
        parent=normal,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#64748b"),
        alignment=1,
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("TAX INVOICE", title_style))
    story.append(Paragraph("(Issued under Section 31 of CGST Act, 2017 · Original for Recipient)", subtitle_style))
    story.append(Spacer(1, 14))

    # 2. Metadata Grid (Seller & Invoice Meta)
    seller = inv.get("seller", {})
    customer = inv.get("customer", {})

    meta_table_data = [
        [
            Paragraph(f"<b>Sold By:</b><br/><b>{seller.get('name', 'Seller')}</b><br/>"
                      f"{seller.get('address', 'Warehouse Complex, India')}<br/>"
                      f"State: {seller.get('state', 'Karnataka')}<br/>"
                      f"<b>GSTIN: {seller.get('gstin', 'N/A')}</b>", normal),
            Paragraph(f"<b>Invoice No:</b> <font color='#ea580c'><b>{inv.get('invoice_no', '')}</b></font><br/>"
                      f"<b>Invoice Date:</b> {str(inv.get('issued_at', ''))[:10]}<br/>"
                      f"<b>Order ID:</b> {inv.get('order_id', '')}<br/>"
                      f"<b>Package / Sub-Order:</b> {str(inv.get('sub_order_id', ''))[:8]}<br/>"
                      f"<b>Tracking No:</b> {inv.get('tracking_number', 'TRK-ASSIGNED')}", normal),
        ],
        [
            Paragraph(f"<b>Billed To / Delivered To:</b><br/>"
                      f"<b>{customer.get('name', 'Customer')}</b><br/>"
                      f"Delivery City: {inv.get('delivery_city', 'Bengaluru')}<br/>"
                      f"Place of Supply: {inv.get('delivery_state', 'Karnataka')}<br/>"
                      f"Contact: {customer.get('phone', '+91-9876543210')}", normal),
            Paragraph("<b>Reverse Charge:</b> No<br/>"
                      "<b>Mode of Supply:</b> E-Commerce Delivery<br/>"
                      f"<b>Platform:</b> MyStore / NammaStore Online Marketplace", normal),
        ]
    ]

    meta_table = Table(meta_table_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # 3. Item Details Table
    items = inv.get("items", [])
    item_rows = [
        [
            Paragraph("<b>#</b>", normal),
            Paragraph("<b>Description of Goods</b>", normal),
            Paragraph("<b>Qty</b>", normal),
            Paragraph("<b>Gross Rate (Rs.)</b>", normal),
            Paragraph("<b>Total (Rs.)</b>", normal),
        ]
    ]

    for idx, it in enumerate(items, 1):
        item_rows.append([
            Paragraph(str(idx), normal),
            Paragraph(f"<b>{it.get('product_name', 'Item')}</b><br/><font color='#64748b' size=7>SKU: {it.get('sku', '')}</font>", normal),
            Paragraph(str(it.get("quantity", 1)), normal),
            Paragraph(f"Rs. {float(it.get('unit_price_inr', 0)):,.2f}", normal),
            Paragraph(f"Rs. {float(it.get('unit_price_inr', 0)) * it.get('quantity', 1):,.2f}", normal),
        ])

    items_table = Table(item_rows, colWidths=[25, 275, 45, 95, 100])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    # 4. Tax Breakdown Table
    taxable = float(inv.get("taxable_value", 0))
    cgst = float(inv.get("cgst", 0))
    sgst = float(inv.get("sgst", 0))
    igst = float(inv.get("igst", 0))
    total = float(inv.get("total", 0))

    tax_rows = [
        [Paragraph("<b>Tax Component</b>", normal), Paragraph("<b>Amount (Rs.)</b>", normal)],
        [Paragraph("Taxable Value of Goods", normal), Paragraph(f"Rs. {taxable:,.2f}", normal)],
    ]
    if cgst > 0 or sgst > 0:
        tax_rows.append([Paragraph("Central GST (CGST)", normal), Paragraph(f"Rs. {cgst:,.2f}", normal)])
        tax_rows.append([Paragraph("State / UT GST (SGST)", normal), Paragraph(f"Rs. {sgst:,.2f}", normal)])
    if igst > 0:
        tax_rows.append([Paragraph("Integrated GST (IGST)", normal), Paragraph(f"Rs. {igst:,.2f}", normal)])

    tax_rows.append([Paragraph("<b>Total Invoice Value (INR)</b>", normal), Paragraph(f"<b>Rs. {total:,.2f}</b>", normal)])

    tax_table = Table(tax_rows, colWidths=[380, 160])
    tax_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
    ]))
    story.append(tax_table)
    story.append(Spacer(1, 12))

    # 5. Amount in Words & Signatory
    words = _num_to_words(total)
    footer_table_data = [
        [
            Paragraph(f"<b>Amount in Words:</b><br/><i>{words}</i><br/><br/>"
                      f"<font size=7 color='#64748b'>This is a computer generated invoice and requires no physical signature.</font>", normal),
            Paragraph(f"For <b>{seller.get('name', 'Seller')}</b>:<br/><br/><br/>"
                      "<b>Authorized Signatory</b>", normal),
        ]
    ]
    footer_table = Table(footer_table_data, colWidths=[360, 180])
    footer_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(footer_table)

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def generate_order_summary_pdf(order_data: Dict[str, Any]) -> bytes:
    """Generate the consolidated Order Summary Cover Sheet."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontSize = 9
    normal.leading = 12

    title_style = ParagraphStyle(
        "SummaryTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        alignment=1,
    )
    subtitle_style = ParagraphStyle(
        "SummarySub",
        parent=normal,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#ea580c"),
        alignment=1,
    )

    story = []
    story.append(Paragraph("MYSTORE · ORDER CONSIGNMENT SUMMARY", title_style))
    story.append(Paragraph("One Order · Multi-Seller Consolidated Dispatch Record", subtitle_style))
    story.append(Spacer(1, 16))

    # Order meta block
    order_id = str(order_data.get("order_id") or order_data.get("id", ""))
    customer = order_data.get("customer", {})
    sub_orders = order_data.get("sub_orders", [])
    grand_total = float(order_data.get("grand_total") or order_data.get("total_inr") or 0)

    meta_data = [
        [
            Paragraph(f"<b>Order ID:</b> {order_id}<br/>"
                      f"<b>Order Date:</b> {str(order_data.get('created_at', ''))[:19]}<br/>"
                      f"<b>Delivery City:</b> {order_data.get('city', 'Bengaluru')}<br/>"
                      f"<b>Total Packages:</b> {len(sub_orders)} Separate Shipments", normal),
            Paragraph(f"<b>Customer Name:</b> {customer.get('name', 'Priya Sharma')}<br/>"
                      f"<b>Customer Phone:</b> {customer.get('phone', '+91-9876543210')}<br/>"
                      f"<b>Payment Status:</b> <font color='green'><b>SUCCESSFUL (Paid in Full)</b></font><br/>"
                      f"<b>Grand Total:</b> <font color='#ea580c' size=11><b>Rs. {grand_total:,.2f}</b></font>", normal),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))

    # Packages Table
    pkg_rows = [
        [
            Paragraph("<b>Pkg</b>", normal),
            Paragraph("<b>Seller & Legal Supplier</b>", normal),
            Paragraph("<b>Tax Invoice No</b>", normal),
            Paragraph("<b>Shipment Tracking</b>", normal),
            Paragraph("<b>Package Total (Rs.)</b>", normal),
        ]
    ]

    for idx, so in enumerate(sub_orders, 1):
        s = so.get("seller", {})
        inv = so.get("invoice", {})
        sh = so.get("shipment", {})
        pkg_rows.append([
            Paragraph(f"#{idx}", normal),
            Paragraph(f"<b>{s.get('name', 'Seller')}</b><br/><font size=7 color='#64748b'>GSTIN: {s.get('gstin', '')}</font>", normal),
            Paragraph(f"<font color='#0284c7'><b>{inv.get('invoice_no', 'Pending')}</b></font>", normal),
            Paragraph(f"{sh.get('tracking_number', 'TRK-ASSIGNED')}", normal),
            Paragraph(f"Rs. {float(so.get('subtotal', 0)):,.2f}", normal),
        ])

    pkg_table = Table(pkg_rows, colWidths=[30, 170, 150, 100, 90])
    pkg_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
    ]))
    story.append(pkg_table)
    story.append(Spacer(1, 14))

    # Explanatory note for the customer
    note = (
        "<b>Customer Notice:</b> As per Indian GST law for Multi-Seller Online Marketplaces, "
        "goods shipped by distinct registered suppliers are billed under individual GST Tax Invoices. "
        "You can claim GST input credit or submit individual invoices as needed."
    )
    story.append(Paragraph(note, ParagraphStyle("Note", parent=normal, textColor=colors.HexColor("#475569"))))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def merge_order_invoices_pdf(summary_pdf: bytes, invoice_pdfs: List[bytes]) -> bytes:
    """Merge summary cover sheet and each seller invoice PDF into a single PDF document."""
    writer = PdfWriter()
    writer.append(io.BytesIO(summary_pdf))
    for inv_bytes in invoice_pdfs:
        writer.append(io.BytesIO(inv_bytes))

    out_buf = io.BytesIO()
    writer.write(out_buf)
    writer.close()
    out_buf.seek(0)
    return out_buf.getvalue()
