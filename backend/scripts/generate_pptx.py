"""Generate the polished MyStore presentation PPTX with all architectural and innovation updates."""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def create_presentation():
    prs = Presentation()
    # 16:9 Widescreen dimensions
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Theme colors
    COLOR_BG = RGBColor(15, 23, 42)        # Dark navy (#0f172a)
    COLOR_CARD = RGBColor(30, 41, 59)      # Slate (#1e293b)
    COLOR_ORANGE = RGBColor(234, 88, 12)   # Brand orange (#ea580c)
    COLOR_GREEN = RGBColor(16, 185, 129)   # Emerald (#10b981)
    COLOR_BLUE = RGBColor(59, 130, 246)    # Blue (#3b82f6)
    COLOR_TEXT = RGBColor(248, 250, 252)   # Near white
    COLOR_MUTED = RGBColor(148, 163, 184)  # Muted slate

    def set_slide_bg(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = COLOR_BG
        bg.line.fill.background()
        return bg

    def add_header(slide, title, subtitle):
        tb = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(1.2))
        tf = tb.text_frame
        tf.word_wrap = True
        
        p1 = tf.paragraphs[0]
        p1.text = title
        p1.font.bold = True
        p1.font.size = Pt(28)
        p1.font.color.rgb = COLOR_TEXT
        
        p2 = tf.add_paragraph()
        p2.text = subtitle
        p2.font.size = Pt(14)
        p2.font.color.rgb = COLOR_ORANGE

    # ==========================================
    # SLIDE 1: Title Slide
    # ==========================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s1)

    # Main title box
    tb = s1.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(11.3), Inches(3.5))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "MyStore 🛍️🇮🇳"
    p.font.bold = True
    p.font.size = Pt(52)
    p.font.color.rgb = COLOR_ORANGE

    p = tf.add_paragraph()
    p.text = "The Indian Retail Superstore That Speaks Your Language & Never Oversells"
    p.font.bold = True
    p.font.size = Pt(24)
    p.font.color.rgb = COLOR_TEXT
    p.space_before = Pt(14)

    p = tf.add_paragraph()
    p.text = "Production Architecture Powered by Aiven Managed Cloud (PostgreSQL · Apache Kafka · OpenSearch)"
    p.font.size = Pt(16)
    p.font.color.rgb = COLOR_GREEN
    p.space_before = Pt(10)

    # Pill tags
    tags = ["Zero Oversell Guarantee", "Hinglish + Voice Search", "Transactional Outbox Pattern", "Real-Time X-Ray Pipeline"]
    for i, tag in enumerate(tags):
        card = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0 + i*2.8), Inches(5.6), Inches(2.6), Inches(0.6))
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_CARD
        card.line.color.rgb = COLOR_ORANGE
        ctf = card.text_frame
        cp = ctf.paragraphs[0]
        cp.text = tag
        cp.alignment = PP_ALIGN.CENTER
        cp.font.size = Pt(11)
        cp.font.color.rgb = COLOR_TEXT

    # ==========================================
    # SLIDE 2: The Problem
    # ==========================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s2)
    add_header(s2, "ONLINE SHOPPING ISN'T BUILT FOR REAL-WORLD INDIA", "The 3 Fatal Gaps in Traditional Retail E-Commerce")

    problems = [
        ("🗣️ Hinglish Gets Lost", "Shoppers type phonetically ('sasta atta', 'bata juta'). Keyword search fails completely, driving 70% cart abandonment among regional Indian shoppers."),
        ("⚡ 1 Last Unit, 2 Buyers", "With batch inventory syncs, two shoppers purchase the final piece at the same time. The order gets canceled later, costing chains up to 15% in refunds and lost loyalty."),
        ("⌛ Stale Search Listings", "Inventory drops to 0 in warehouse stock, but search caches lag for hours. Customers waste time chasing out-of-stock ghost products.")
    ]
    for i, (p_title, p_desc) in enumerate(problems):
        card = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i*4.0), Inches(2.0), Inches(3.7), Inches(4.5))
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_CARD
        card.line.color.rgb = COLOR_ORANGE if i==1 else COLOR_MUTED
        ctf = card.text_frame
        ctf.word_wrap = True
        
        cp1 = ctf.paragraphs[0]
        cp1.text = p_title
        cp1.font.bold = True
        cp1.font.size = Pt(20)
        cp1.font.color.rgb = COLOR_TEXT
        
        cp2 = ctf.add_paragraph()
        cp2.text = p_desc
        cp2.font.size = Pt(14)
        cp2.font.color.rgb = COLOR_MUTED
        cp2.space_before = Pt(16)

    # ==========================================
    # SLIDE 3: The Architecture (One Store, Three Aiven Services)
    # ==========================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s3)
    add_header(s3, "SYSTEM ARCHITECTURE: 3 MANAGED AIVEN SERVICES", "ACID Consistency + Event Streaming + Hybrid Vector Intelligence")

    services = [
        ("1. Aiven PostgreSQL", "The Source of Truth", [
            "Atomic row-level reservation: UPDATE ... WHERE qty >= :n",
            "Transactional Outbox pattern (Zero dual-write failures)",
            "310 seeded Indian products across 5 major metro hubs"
        ], COLOR_BLUE),
        ("2. Aiven Apache Kafka", "Distributed Event Spine", [
            "8 topics: orders.placed, inventory.changed, *.dlq",
            "Idempotent consumers with processed_events table",
            "Decoupled asynchronous notification & search-sync"
        ], COLOR_ORANGE),
        ("3. Aiven OpenSearch", "Sub-Second Hybrid Search", [
            "BM25 lexical + 384-d kNN dense vectors (bge-small-en-v1.5)",
            "Reciprocal Rank Fusion (RRF) for 100% Recall@5",
            "Real-time partial index updates via Kafka events"
        ], COLOR_GREEN)
    ]

    for i, (srv_title, srv_sub, srv_bullets, srv_color) in enumerate(services):
        card = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i*4.0), Inches(2.0), Inches(3.7), Inches(4.5))
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_CARD
        card.line.color.rgb = srv_color
        ctf = card.text_frame
        ctf.word_wrap = True
        
        cp1 = ctf.paragraphs[0]
        cp1.text = srv_title
        cp1.font.bold = True
        cp1.font.size = Pt(18)
        cp1.font.color.rgb = srv_color
        
        cp2 = ctf.add_paragraph()
        cp2.text = srv_sub
        cp2.font.size = Pt(12)
        cp2.font.color.rgb = COLOR_MUTED
        cp2.space_before = Pt(4)
        
        for b in srv_bullets:
            bp = ctf.add_paragraph()
            bp.text = f"• {b}"
            bp.font.size = Pt(13)
            bp.font.color.rgb = COLOR_TEXT
            bp.space_before = Pt(10)

    # ==========================================
    # SLIDE 4: End-to-End Event Flow
    # ==========================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s4)
    add_header(s4, "HOW AN ORDER PROPAGATES THROUGH MYSTORE", "Guaranteed At-Least-Once Delivery & Exact-Once Processing")

    steps = [
        ("1. Shopper Action", "Customer searches (text/voice), selects city, and clicks Checkout"),
        ("2. ACID Lock", "PostgreSQL executes row-lock deduction and inserts Order + Outbox record"),
        ("3. Outbox Relay", "Background worker polls unpublished rows (SKIP LOCKED) and pushes to Kafka"),
        ("4. Kafka Event Bus", "Broadcasts orders.placed & inventory.changed asynchronously"),
        ("5. Reactive Consumers", "Notification sends SMS/Email audit; Search-Sync re-indexes OpenSearch")
    ]
    for i, (st, sd) in enumerate(steps):
        card = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.0 + i*0.95), Inches(11.7), Inches(0.8))
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_CARD
        card.line.color.rgb = COLOR_ORANGE if i==1 else COLOR_MUTED
        ctf = card.text_frame
        ctf.word_wrap = True
        
        cp1 = ctf.paragraphs[0]
        cp1.text = f"{st}:  {sd}"
        cp1.font.size = Pt(14)
        cp1.font.color.rgb = COLOR_TEXT

    # Tech stack tag at bottom
    tb = s4.shapes.add_textbox(Inches(0.8), Inches(6.8), Inches(11.7), Inches(0.5))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    p.text = "Stack: Python 3.12 (FastAPI) · Tailwind CSS Storefront · Aiven PostgreSQL · Aiven Kafka · Aiven OpenSearch"
    p.font.size = Pt(12)
    p.font.color.rgb = COLOR_MUTED

    # ==========================================
    # SLIDE 5: Unique Innovations (What Sets Us Apart)
    # ==========================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s5)
    add_header(s5, "UNIQUE INNOVATIONS (UNMET USER DEMANDS)", "Features Designed Specifically for Modern Indian Consumers")

    innovations = [
        ("🎙️ 'Bolo aur Kharido' (Voice Search)", "Native Web Speech API integration with hi-IN localization. Shoppers can speak naturally in Hindi/Hinglish (e.g. 'तूर दाल'). Punctuation like Hindi full-stops (।) is sanitized and translated in real-time."),
        ("🚚 Cross-City Stock Routing", "If an item is out of stock in the user's city (e.g. Bengaluru), MyStore automatically discovers inventory in other Indian hubs (Mumbai/Delhi) and offers 2-Day Express Shipping instead of losing the sale."),
        ("⚠️ Semantic Fallback Engine", "When a query cannot be found, MyStore avoids dead-end 0-hit screens. OpenSearch dense vector similarity automatically surfaces the top 4 closest semantic recommendations with an interactive 'Similar Found' badge."),
        ("🔬 Real-Time X-Ray Pipeline (/pipeline)", "Server-Sent Events (SSE) live stream exposing the internal journey of every order across DB locks, Kafka topics, and OpenSearch sync for full developer observability.")
    ]

    for i, (it, idesc) in enumerate(innovations):
        row = i // 2
        col = i % 2
        card = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + col*5.95), Inches(2.0 + row*2.4), Inches(5.75), Inches(2.2))
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_CARD
        card.line.color.rgb = COLOR_GREEN if i < 2 else COLOR_BLUE
        ctf = card.text_frame
        ctf.word_wrap = True
        
        cp1 = ctf.paragraphs[0]
        cp1.text = it
        cp1.font.bold = True
        cp1.font.size = Pt(16)
        cp1.font.color.rgb = COLOR_TEXT
        
        cp2 = ctf.add_paragraph()
        cp2.text = idesc
        cp2.font.size = Pt(12)
        cp2.font.color.rgb = COLOR_MUTED
        cp2.space_before = Pt(8)

    # ==========================================
    # SLIDE 6: Live Benchmarks & Proof
    # ==========================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s6)
    add_header(s6, "PROVEN RELIABILITY & SEARCH BENCHMARKS", "Hard Empirical Evidence From Real Workloads")

    # Left Card: Stress test
    c1 = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.0), Inches(5.6), Inches(4.5))
    c1.fill.solid()
    c1.fill.fore_color.rgb = COLOR_CARD
    c1.line.color.rgb = COLOR_ORANGE
    ctf1 = c1.text_frame
    ctf1.word_wrap = True
    
    cp = ctf1.paragraphs[0]
    cp.text = "10-Buyer Last Unit Concurrency Test"
    cp.font.bold = True
    cp.font.size = Pt(18)
    cp.font.color.rgb = COLOR_ORANGE

    test_metrics = [
        ("Simultaneous Buyers", "10 async requests"),
        ("Succeeded Checkouts", "1 buyer (Won unit)"),
        ("Rejected Checkouts", "9 buyers (OutOfStockError)"),
        ("Final Store Stock", "0 units remaining"),
        ("Double-Sell Invariant", "VERIFIED PRESERVED (0 Oversold)")
    ]
    for lbl, val in test_metrics:
        p = ctf1.add_paragraph()
        p.text = f"• {lbl}: {val}"
        p.font.size = Pt(13)
        p.font.color.rgb = COLOR_TEXT
        p.space_before = Pt(10)

    # Right Card: Search Scorecard Table
    c2 = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(2.0), Inches(5.7), Inches(4.5))
    c2.fill.solid()
    c2.fill.fore_color.rgb = COLOR_CARD
    c2.line.color.rgb = COLOR_GREEN
    ctf2 = c2.text_frame
    ctf2.word_wrap = True
    
    cp = ctf2.paragraphs[0]
    cp.text = "Search Quality Scorecard (30 Queries)"
    cp.font.bold = True
    cp.font.size = Pt(18)
    cp.font.color.rgb = COLOR_GREEN

    scorecard_lines = [
        ("BM25 Full-Text Only", "90.00%", "0.8233 MRR"),
        ("Vector Only (384-d kNN)", "93.33%", "0.7844 MRR"),
        ("MyStore Hybrid (RRF)", "100.00%", "0.8261 MRR")
    ]
    for strat, rec, mrr in scorecard_lines:
        p = ctf2.add_paragraph()
        p.text = f"• {strat}: Recall@5 = {rec} ({mrr})"
        p.font.size = Pt(13)
        p.font.color.rgb = COLOR_TEXT
        p.space_before = Pt(12)

    p_note = ctf2.add_paragraph()
    p_note.text = "Evaluated on Indian retail typos ('bluetoth earphones'), Hinglish terms ('sasta atta'), brand protections, and vernacular Devanagari speech."
    p_note.font.size = Pt(11)
    p_note.font.color.rgb = COLOR_MUTED
    p_note.space_before = Pt(18)

    # ==========================================
    # SLIDE 7: Live Links & Demo
    # ==========================================
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s7)
    add_header(s7, "EXPERIENCE MYSTORE LIVE", "Production Deployment on Render & GitHub Repository")

    links = [
        ("🛍️ Customer Storefront", "https://online-store-cd1p.onrender.com/", "Full catalog, voice search, city switcher, accurate images, and atomic cart"),
        ("🔬 X-Ray Pipeline Dashboard", "https://online-store-cd1p.onrender.com/pipeline", "Real-time SSE event timeline, live Kafka audit log, and 10-buyer stress test"),
        ("💻 GitHub Repository", "https://github.com/yograjd30/online-store", "Complete open-source codebase, migration scripts, and architecture documentation")
    ]
    for i, (lt, lurl, ldesc) in enumerate(links):
        card = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.0 + i*1.6), Inches(11.7), Inches(1.3))
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_CARD
        card.line.color.rgb = COLOR_ORANGE if i==0 else (COLOR_BLUE if i==1 else COLOR_GREEN)
        ctf = card.text_frame
        ctf.word_wrap = True
        
        cp1 = ctf.paragraphs[0]
        cp1.text = lt
        cp1.font.bold = True
        cp1.font.size = Pt(16)
        cp1.font.color.rgb = COLOR_TEXT
        
        cp2 = ctf.add_paragraph()
        cp2.text = lurl
        cp2.font.bold = True
        cp2.font.size = Pt(14)
        cp2.font.color.rgb = COLOR_ORANGE
        cp2.space_before = Pt(4)
        
        cp3 = ctf.add_paragraph()
        cp3.text = ldesc
        cp3.font.size = Pt(11)
        cp3.font.color.rgb = COLOR_MUTED

    output_path = "c:\\Users\\HP\\online-store\\MyStore_Hackathon_Presentation.pptx"
    prs.save(output_path)
    print(f"Presentation saved successfully to: {output_path}")

if __name__ == "__main__":
    create_presentation()
