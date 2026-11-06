"""Presentation-only Streamlit theme. No payroll, schedule, or storage logic."""
import streamlit as st

PALETTES = {
    "Ciemny": {
        "bg": "#0b1120", "surface": "#121d31", "raised": "#192840",
        "text": "#eef5ff", "muted": "#9db0c9", "border": "#2c3d57",
        "accent": "#65a9ff", "accent_text": "#06182c", "input": "#111d30",
        "success": "#1c433e", "success_text": "#b8f5df",
        "danger": "#4a2636", "danger_text": "#ffd2dd",
        "shadow": "0 12px 36px rgba(0,0,0,.20)",
    },
    "Jasny": {
        "bg": "#f3f6fb", "surface": "#ffffff", "raised": "#eaf1fb",
        "text": "#16243a", "muted": "#546780", "border": "#dbe4f0",
        "accent": "#205bb5", "accent_text": "#ffffff", "input": "#ffffff",
        "success": "#e5f7ee", "success_text": "#12694a",
        "danger": "#fff0f1", "danger_text": "#a0203b",
        "shadow": "0 10px 28px rgba(28,57,94,.07)",
    },
}


def apply_theme(mode):
    """Render a scoped CSS skin while keeping Streamlit widgets accessible."""
    p = PALETTES[mode]
    vars_css = ";".join(f"--premium-{key.replace('_','-')}:{value}" for key, value in p.items())
    st.markdown(
        f"""<style>
        :root {{{vars_css};color-scheme: {'dark' if mode == 'Ciemny' else 'light'};}}
        .stApp, [data-testid="stAppViewContainer"] {{
            background: var(--premium-bg) !important;
            color: var(--premium-text) !important;
        }}
        [data-testid="stHeader"] {{background: transparent !important;}}
        [data-testid="stSidebar"] {{
            background: var(--premium-surface) !important;
            border-right: 1px solid var(--premium-border);
        }}
        [data-testid="stSidebar"] * {{color: var(--premium-text);}}
        .stApp h1, .stApp h2, .stApp h3, .stApp h4,
        .stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"] {{
            color: var(--premium-text);
        }}
        .stApp [data-testid="stCaptionContainer"],
        .stApp [data-testid="stWidgetLabel"] p {{
            color: var(--premium-muted) !important;
        }}
        .block-container {{
            max-width: 1320px;
            padding-top: 1rem;
            padding-bottom: 2rem;
        }}
        /* Compact business application shell inspired by Fluent forms. */
        .work-commandbar {{
            display:flex; align-items:center; gap:13px; flex-wrap:wrap;
            min-height:42px; padding:8px 15px; margin-bottom:10px;
            background:var(--premium-surface); border:1px solid var(--premium-border);
            border-radius:7px; font-size:.79rem; color:var(--premium-muted);
        }}
        .work-commandbar-brand {{
            color:var(--premium-accent); font-weight:750; letter-spacing:.045em;
            padding-right:15px; border-right:1px solid var(--premium-border);
        }}
        .work-commandbar-arrow {{opacity:.45;}}
        .work-record-header {{
            display:flex; align-items:center; justify-content:space-between;
            gap:16px; padding:15px 19px; margin-bottom:13px;
            background:var(--premium-surface); border:1px solid var(--premium-border);
            border-radius:8px;
        }}
        .work-record-kicker, .work-section-heading {{
            font-size:.69rem; font-weight:750; letter-spacing:.08em;
            color:var(--premium-muted); margin-bottom:6px;
        }}
        .work-record-header h2 {{margin:0 0 3px; font-size:1.35rem;}}
        .work-record-header p {{margin:0; color:var(--premium-muted); font-size:.81rem;}}
        .work-record-state {{
            color:var(--premium-accent); font-size:.76rem; white-space:nowrap;
            border:1px solid var(--premium-border); padding:6px 10px; border-radius:20px;
        }}
        .work-section-heading {{margin:5px 0 7px;}}
        .stApp div[data-testid="stMetric"] {{
            box-shadow:none; border-radius:7px; padding:8px 12px;
        }}
        .stApp div[data-baseweb="tab-list"] {{border-bottom:1px solid var(--premium-border);}}
        @media(max-width:720px) {{
            .work-record-header {{align-items:flex-start; flex-direction:column;}}
            .work-commandbar-brand {{width:100%; border-right:0;}}
        }}
        .premium-hero {{
            padding: 14px 20px;
            margin: 2px 0 12px;
            border: 1px solid var(--premium-border);
            border-radius: 13px;
            background: linear-gradient(115deg, var(--premium-surface), var(--premium-raised));
            box-shadow: var(--premium-shadow);
        }}
        .premium-eyebrow {{
            font-size: .65rem;
            text-transform: uppercase;
            letter-spacing: .16em;
            color: var(--premium-accent);
            font-weight: 750;
        }}
        .premium-hero h1 {{
            font-size: clamp(1.3rem, 2vw, 1.85rem);
            margin: .18rem 0 .22rem;
            color: var(--premium-text);
            letter-spacing: -.035em;
        }}
        .premium-hero p {{color: var(--premium-muted); margin: 0;}}
        div[data-testid="stMetric"], div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {{
            background: var(--premium-surface);
            border: 1px solid var(--premium-border);
            border-radius: 11px;
            padding: 8px 12px;
            box-shadow: var(--premium-shadow);
        }}
        div[data-testid="stMetricValue"] {{
            color: var(--premium-accent) !important;
            font-weight: 760;
            letter-spacing: -.025em;
        }}
        div[data-testid="stMetricLabel"] {{color: var(--premium-muted);}}
        /* Compact, restrained visual hierarchy without shrinking interactive targets excessively. */
        .stApp h1 {{font-size: 1.7rem;}}
        .stApp h2 {{font-size: 1.32rem; margin-bottom: .45rem;}}
        .stApp h3 {{font-size: 1.08rem; margin-bottom: .35rem;}}
        .stApp [data-testid="stMetricValue"] {{font-size: 1.45rem; line-height: 1.25;}}
        .stApp [data-testid="stMetricLabel"] {{font-size: .79rem;}}
        .stApp [data-testid="stVerticalBlock"] {{gap: .65rem;}}
        .stApp [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{gap: .45rem;}}
        .stApp [data-testid="stSidebar"] h2 {{font-size: 1.1rem;}}
        .stApp [data-testid="stSidebar"] h3 {{font-size: .95rem;}}
        .premium-hero p {{font-size: .84rem;}}
        .stApp div[data-baseweb="tab-list"] {{
            gap: 5px;
            overflow-x: auto;
            padding-bottom: 8px;
        }}
        .stApp button[data-baseweb="tab"] {{
            border-radius: 12px;
            background: var(--premium-surface);
            border: 1px solid var(--premium-border);
            color: var(--premium-muted);
            padding: 6px 10px;
            white-space: nowrap;
        }}
        .stApp button[data-baseweb="tab"][aria-selected="true"] {{
            color: var(--premium-accent);
            border-color: var(--premium-accent);
            background: var(--premium-raised);
        }}
        .stApp div.stButton > button, .stApp div.stDownloadButton > button,
        .stApp div.stFormSubmitButton > button {{
            border-radius: 11px;
            font-weight: 650;
            border: 1px solid var(--premium-border);
            background: var(--premium-surface);
            color: var(--premium-text);
        }}
        .stApp button[kind="primary"] {{
            background: var(--premium-accent) !important;
            color: var(--premium-accent-text) !important;
            border-color: var(--premium-accent) !important;
        }}
        .stApp button:focus-visible, .stApp input:focus-visible {{
            outline: 3px solid var(--premium-accent) !important;
            outline-offset: 2px;
        }}
        .stApp div[data-baseweb="input"], .stApp div[data-baseweb="select"],
        .stApp div[data-baseweb="textarea"] {{
            background: var(--premium-input);
            border-radius: 10px;
            color: var(--premium-text);
        }}
        .stApp input, .stApp textarea {{
            color: var(--premium-text) !important;
            caret-color: var(--premium-accent);
        }}
        .stApp div[data-testid="stDataFrame"] {{
            border: 1px solid var(--premium-border);
            border-radius: 14px;
            overflow: hidden;
        }}
        .alert-box {{
            background: var(--premium-danger);
            color: var(--premium-danger-text);
            border-left: 4px solid #f47791;
            padding: 14px;
            border-radius: 12px;
        }}
        .success-box {{
            background: var(--premium-success);
            color: var(--premium-success-text);
            border-left: 4px solid #36b991;
            padding: 14px;
            border-radius: 12px;
        }}
        .pay-slip {{
            background: #fff;
            color: #14243a;
            border: 1px solid #b8c8dc;
            border-radius: 14px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .pay-slip, .pay-slip * {{color: #14243a !important;}}
        .pay-slip-header {{border-bottom: 2px solid #205bb5; padding-bottom: 10px;}}
        @media (max-width: 760px) {{
            .block-container {{padding: 1rem .7rem 3rem;}}
            .premium-hero {{padding: 18px;}}
        }}
        @media print {{
            .stApp header, .stApp footer, [data-testid="stSidebar"],
            [data-testid="stToolbar"], .premium-hero {{display:none !important;}}
            .stApp {{background:#fff !important;}}
            .pay-slip {{page-break-inside:avoid;box-shadow:none;}}
        }}
        </style>""",
        unsafe_allow_html=True,
    )


def hero():
    st.markdown(
        """<section class="premium-hero" aria-label="System Premii">
        <div class="premium-eyebrow">Panel operacyjny / wersja testowa 2.7</div>
        <h1>SYSTEM PREMII 2.7 | WERSJA TESTOWA</h1>
        <p>Harmonogramy · Wydajność magazynu · Rozliczenia i analityka</p>
        </section>""",
        unsafe_allow_html=True,
    )

