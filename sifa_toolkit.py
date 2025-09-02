# sifa_toolkit.py
# ---------------------------------------------------------
# SiFa-Toolkit: Komplettes Werkzeug für Fachkräfte für Arbeitssicherheit
# Enthält die komplette Gefährdungsbeurteilung (aus deiner bisherigen App)
# + zusätzliche Module: Maßnahmen, Unterweisung, Begehung, ASA, Unfall, Gefahrstoffe,
#   Prüffristen, Rechtskataster, Kennzahlen, Dokumente.
# ---------------------------------------------------------

import json, re
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from io import BytesIO
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd
from dateutil.relativedelta import relativedelta
import streamlit as st
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import ColorScaleRule

# =========================
# 0) Seiten-Setup
# =========================
st.set_page_config(page_title="SiFa-Toolkit", layout="wide", initial_sidebar_state="expanded")
st.title("SiFa-Toolkit – Alles für die Fachkraft für Arbeitssicherheit")

# =========================
# 1) Datenmodelle (aus bisheriger App + Ergänzungen)
# =========================

STOP_LEVELS = [
    "S (Substitution/Quelle entfernen)",
    "T (Technisch)",
    "O (Organisatorisch)",
    "P (PSA)",
    "Q (Qualifikation/Unterweisung)"
]
STATUS_LIST = ["offen", "in Umsetzung", "wirksam", "nicht wirksam", "entfallen"]

@dataclass
class Measure:
    title: str
    stop_level: str
    responsible: str = ""
    due_date: Optional[str] = None  # ISO
    status: str = "offen"
    notes: str = ""

@dataclass
class Hazard:
    id: str
    area: str
    activity: str
    hazard: str
    sources: List[str]
    existing_controls: List[str]
    prob: int = 3
    sev: int = 3
    risk_value: int = 9
    risk_level: str = "mittel"
    additional_measures: List[Measure] = field(default_factory=list)
    last_review: Optional[str] = None
    reviewer: str = ""
    documentation_note: str = ""

@dataclass
class Assessment:
    company: str
    location: str
    created_at: str
    created_by: str
    industry: str = "Hotel/Gastgewerbe"
    scope_note: str = ""
    risk_matrix_thresholds: Dict[str, List[int]] = field(default_factory=lambda: {"thresholds": [6, 12, 16]})
    hazards: List[Hazard] = field(default_factory=list)
    measures_plan_note: str = ""
    documentation_note: str = ""
    next_review_hint: str = ""

# Zusätzliche Tabellen für neue Module
DEFAULT_TABLES = {
    "measures_board": pd.DataFrame(columns=["ID","Gefährdungs-ID","Maßnahme","STOP(+Q)","Verantwortlich","Fällig","Status","Hinweis"]),
    "trainings": pd.DataFrame(columns=["Unterweisung","Zielgruppe","Inhalt/BA","Turnus (Monate)","Nächste Fälligkeit","Verantwortlich","Nachweisablage"]),
    "walkthroughs": pd.DataFrame(columns=["Datum","Bereich","Feststellung","Risikoklasse","Maßnahme","Verantwortlich","Fällig","Status","Foto/Anhang"]),
    "asa": pd.DataFrame(columns=["Datum","Teilnehmer","Themen","Beschlüsse/Maßnahmen","Verantwortlich","Fällig","Status","Protokollablage"]),
    "incidents": pd.DataFrame(columns=["Datum","Bereich","Ereignis (Unfall/Beinahe)","Beschreibung","Verletzung/Schaden","Ursachen (5xWarums)","Sofortmaßnahme","Korrekturmaßnahme","Status","Meldewesen/Ablage"]),
    "chemicals": pd.DataFrame(columns=["Produkt","Gefahren","SDB Datum","Betriebsanweisung","Lagerort","Mengenklasse","Ersatzstoffprüfung","PPE","Erste Hilfe","Entsorgung"]),
    "assets": pd.DataFrame(columns=["Arbeitsmittel","Inventar-Nr.","Kategorie","Prüfgrundlage","Frist (Monate)","Letzte Prüfung","Nächste Prüfung","Verantwortlich","Dienstleister","Nachweisablage"]),
    "legal": pd.DataFrame(columns=["Rechtsquelle/Regelwerk","Anforderung (Kurz)","Gültig ab","Letzte Prüfung","Status (konform/offen)","Nachweis","Änderungsnotiz"]),
    "docs": pd.DataFrame(columns=["Bezeichnung","Typ","Ablageort","Version/Datum","Gültig bis","Hinweis"])
}

# =========================
# 2) Utilities
# =========================
def compute_risk(prob: int, sev: int, thresholds: List[int]) -> Tuple[int, str]:
    v = prob * sev
    if v <= thresholds[0]:
        return v, "niedrig"
    elif v <= thresholds[1]:
        return v, "mittel"
    elif v <= thresholds[2]:
        return v, "hoch"
    else:
        return v, "sehr hoch"

def new_id(prefix="HZ", n=4) -> str:
    ts = datetime.now().strftime("%y%m%d%H%M%S%f")[-n:]
    return f"{prefix}-{int(datetime.now().timestamp())}-{ts}"

def hazard_to_row(h: Hazard) -> Dict[str, Any]:
    return {
        "ID": h.id, "Bereich": h.area, "Tätigkeit": h.activity, "Gefährdung": h.hazard,
        "Quellen/Einwirkungen": "; ".join(h.sources), "Bestehende Maßnahmen": "; ".join(h.existing_controls),
        "Eintrittswahrscheinlichkeit (1-5)": h.prob, "Schadensschwere (1-5)": h.sev,
        "Risikosumme": h.risk_value, "Risikostufe": h.risk_level,
        "Letzte Prüfung": h.last_review or "", "Prüfer/in": h.reviewer,
        "Beurteilungs-/Dokumentationshinweis": h.documentation_note
    }

def measures_to_rows(h: Hazard) -> List[Dict[str, Any]]:
    rows = []
    for m in h.additional_measures:
        rows.append({
            "Gefährdungs-ID": h.id, "Bereich": h.area, "Gefährdung": h.hazard,
            "Maßnahme": m.title, "STOP(+Q)": m.stop_level, "Verantwortlich": m.responsible,
            "Fällig am": m.due_date or "", "Status": m.status, "Hinweis": m.notes
        })
    return rows

def as_json(assess: Assessment) -> str:
    return json.dumps(asdict(assess), ensure_ascii=False, indent=2)

def from_json(s: str) -> Assessment:
    data = json.loads(s)
    hazards = []
    for h in data.get("hazards", []):
        measures = [Measure(**m) for m in h.get("additional_measures", [])]
        hazards.append(Hazard(
            id=h["id"], area=h["area"], activity=h["activity"], hazard=h["hazard"],
            sources=h.get("sources", []),
            existing_controls=h.get("existing_controls", h.get("existing", [])),
            prob=h.get("prob", 3), sev=h.get("sev", 3),
            risk_value=h.get("risk_value", 9), risk_level=h.get("risk_level", "mittel"),
            additional_measures=measures, last_review=h.get("last_review"),
            reviewer=h.get("reviewer", ""), documentation_note=h.get("documentation_note", "")
        ))
    return Assessment(
        company=data.get("company",""), location=data.get("location",""),
        created_at=data.get("created_at",""), created_by=data.get("created_by",""),
        industry=data.get("industry","Hotel/Gastgewerbe"), scope_note=data.get("scope_note", ""),
        risk_matrix_thresholds=data.get("risk_matrix_thresholds", {"thresholds":[6,12,16]}),
        hazards=hazards, measures_plan_note=data.get("measures_plan_note",""),
        documentation_note=data.get("documentation_note",""), next_review_hint=data.get("next_review_hint","")
    )

def slug(*parts: str) -> str:
    s = "_".join(parts)
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s)
    return s[:80]

# =========================
# 3) Branchenbibliothek (aus deiner letzten Version, hier stark gekürzt als Platzhalter)
#    → Tipp: Ersetze diesen Block 1:1 mit deiner großen INDUSTRY_LIBRARY aus der letzten App.
# =========================
def M(title, stop="O (Organisatorisch)"):
    return {"title": title, "stop_level": stop}

# Mini-Demo (ersetzen durch deine vollständigen LIB_* Strukturen!)
LIB_DEMO = {
    "Küche": [
        {"activity":"Frittieren","hazard":"Fettbrand, Verbrennungen","sources":["Fritteuse"],"existing":["Löscheinrichtung"],"measures":[M("Keine Wasserzugabe"),M("Löschdecke bereit")]},
        {"activity":"Schneiden","hazard":"Schnittverletzung","sources":["Messer"],"existing":["Scharfe Messer"],"measures":[M("Schnittschutzhandschuhe","P (PSA)")]},
    ]
}
INDUSTRY_LIBRARY: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "Hotel/Gastgewerbe": LIB_DEMO,  # <— hier deine große Bibliothek einfügen!
}

# =========================
# 4) Vorlagen/Import
# =========================
def template_item_key(industry: str, area: str, item: Dict[str, Any]) -> str:
    return slug(industry, area, item.get("activity",""), item.get("hazard",""))

_SPLIT_PATTERN = re.compile(r"\s*(?:,|/| und | & )\s*")
def split_hazard_text(text: str) -> List[str]:
    if not text: return []
    parts = [p.strip() for p in _SPLIT_PATTERN.split(text) if p and p.strip()]
    seen, uniq = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p); uniq.append(p)
    return uniq or [text.strip()]

def add_template_items(assess: Assessment, template: Dict[str, List[Dict[str, Any]]],
                       selected_keys: Optional[List[str]] = None, industry_name: Optional[str] = None,
                       split_multi: Optional[bool] = None):
    if split_multi is None:
        split_multi = st.session_state.get("opt_split_multi_hazards", True)
    DEFAULT_STOP = "O (Organisatorisch)"

    def normalize_measure(m: Any) -> Optional[Measure]:
        if isinstance(m, dict):
            return Measure(
                title=(m.get("title") or "").strip(),
                stop_level=m.get("stop_level", DEFAULT_STOP),
                notes=m.get("notes","")
            )
        elif isinstance(m, str):
            t = m.strip()
            return Measure(title=t, stop_level=DEFAULT_STOP) if t else None
        return None

    for area, items in template.items():
        for item in items:
            key = template_item_key(industry_name or assess.industry, area, item)
            if selected_keys is not None and key not in selected_keys:
                continue
            hazard_text = item.get("hazard","")
            hazards_list = split_hazard_text(hazard_text) if split_multi else [hazard_text]
            for hz_text in hazards_list:
                hz = Hazard(
                    id=new_id(), area=area, activity=item.get("activity",""), hazard=hz_text,
                    sources=item.get("sources",[]) or [], existing_controls=item.get("existing",[]) or []
                )
                for m in item.get("measures",[]) or []:
                    mm = normalize_measure(m)
                    if mm and mm.title:
                        hz.additional_measures.append(mm)
                assess.hazards.append(hz)

def preload_industry(assess: Assessment, industry_name: str, replace: bool = True):
    assess.industry = industry_name
    if replace:
        assess.hazards = []
    template = INDUSTRY_LIBRARY.get(industry_name, {})
    add_template_items(assess, template, selected_keys=None, industry_name=industry_name)

# =========================
# 5) Excel-Export (wie bisher)
# =========================
def dump_excel(assess: Assessment) -> bytes:
    hazards_df = pd.DataFrame([hazard_to_row(h) for h in assess.hazards])
    measures_df = pd.DataFrame([r for h in assess.hazards for r in measures_to_rows(h)])

    plan_rows = []
    for h in assess.hazards:
        for m in h.additional_measures:
            plan_rows.append({
                "Gefährdungs-ID": h.id, "Bereich": h.area, "Tätigkeit": h.activity, "Gefährdung": h.hazard,
                "Risikosumme": h.risk_value, "Risikostufe": h.risk_level, "Maßnahme": m.title,
                "STOP(+Q)": m.stop_level, "Verantwortlich": m.responsible, "Fällig am": m.due_date or "",
                "Status": m.status, "Hinweis": m.notes,
            })
    plan_df = pd.DataFrame(plan_rows)
    review_df = pd.DataFrame([{
        "Gefährdungs-ID": h.id, "Bereich": h.area, "Tätigkeit": h.activity, "Gefährdung": h.hazard,
        "Letzte Prüfung": h.last_review or "", "Prüfer/in": h.reviewer,
        "Beurteilungs-/Dokumentationshinweis": h.documentation_note,
    } for h in assess.hazards])
    meta_df = pd.DataFrame(list({
        "Unternehmen": assess.company, "Standort": assess.location, "Erstellt am": assess.created_at,
        "Erstellt von": assess.created_by, "Branche": assess.industry, "Umfang/Scope": assess.scope_note,
    }.items()), columns=["Feld","Wert"])
    doc_df = pd.DataFrame({"Dokumentationshinweis":[assess.documentation_note or ""]})
    prog_df = pd.DataFrame({"Anlässe/Fristen (Fortschreibung)":[assess.next_review_hint or ""]})
    thresholds = assess.risk_matrix_thresholds.get("thresholds",[6,12,16])
    conf_df = pd.DataFrame({"Einstellung":["Grenze niedrig (≤)","Grenze mittel (≤)","Grenze hoch (≤)"],
                            "Wert":[thresholds[0],thresholds[1],thresholds[2]]})

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        meta_df.to_excel(writer, sheet_name="01_Stammdaten", index=False)
        hazards_df.to_excel(writer, sheet_name="10_Gefährdungen", index=False)
        measures_df.to_excel(writer, sheet_name="20_Maßnahmen", index=False)
        plan_df.to_excel(writer, sheet_name="30_Plan", index=False)
        review_df.to_excel(writer, sheet_name="40_Wirksamkeit", index=False)
        doc_df.to_excel(writer, sheet_name="50_Dokumentation", index=False)
        prog_df.to_excel(writer, sheet_name="60_Fortschreiben", index=False)
        conf_df.to_excel(writer, sheet_name="90_Konfiguration", index=False)

        readme_df = pd.DataFrame([
            ["Datei erstellt", datetime.now().strftime("%Y-%m-%d %H:%M")],
            ["Generator", "SiFa-Toolkit (Streamlit)"], ["Hinweis", "Blätter 10–60 = Prozessschritte"],
        ], columns=["Info","Wert"])
        readme_df.to_excel(writer, sheet_name="99_README", index=False)

        wb = writer.book
        header_fill = PatternFill("solid", fgColor="E6EEF8")
        bold = Font(bold=True)
        thin = Side(style="thin", color="DDDDDD")
        border = Border(left=thin,right=thin,top=thin,bottom=thin)

        def style_sheet(name: str, freeze=True, wide_wrap=True):
            ws = wb[name]
            if ws.max_row >= 1:
                for c in ws[1]:
                    c.font = bold; c.fill = header_fill
                    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                    c.border = border
            if ws.max_row >= 2:
                for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
                    for cell in row:
                        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                        cell.border = border
            for col_idx in range(1, ws.max_column+1):
                col = get_column_letter(col_idx)
                maxlen = 8
                for r in range(1, min(ws.max_row,200)+1):
                    val = ws.cell(row=r, column=col_idx).value
                    if val is None: continue
                    maxlen = max(maxlen, len(str(val)))
                ws.column_dimensions[col].width = min(maxlen+2, 60)
            if freeze and ws.max_row>1: ws.freeze_panes = "A2"
            return ws

        for sheet in ["01_Stammdaten","10_Gefährdungen","20_Maßnahmen","30_Plan",
                      "40_Wirksamkeit","50_Dokumentation","60_Fortschreiben","90_Konfiguration","99_README"]:
            style_sheet(sheet, freeze=True, wide_wrap=(sheet not in ["01_Stammdaten","90_Konfiguration","99_README"]))

        if "30_Plan" in wb.sheetnames:
            ws_plan = wb["30_Plan"]
            status_col_idx = None
            for c in range(1, ws_plan.max_column+1):
                if (ws_plan.cell(row=1, column=c).value or "").strip() == "Status":
                    status_col_idx = c; break
            if status_col_idx:
                dv = DataValidation(type="list", formula1='"' + ",".join(STATUS_LIST) + '"', allow_blank=True, showDropDown=True)
                ws_plan.add_data_validation(dv)
                dv.add(f"{get_column_letter(status_col_idx)}2:{get_column_letter(status_col_idx)}1048576")

        if "10_Gefährdungen" in wb.sheetnames:
            ws_h = wb["10_Gefährdungen"]
            risk_col = None
            for c in range(1, ws_h.max_column+1):
                if (ws_h.cell(row=1, column=c).value or "").strip() == "Risikosumme":
                    risk_col = c; break
            if risk_col:
                col_letter = get_column_letter(risk_col)
                rng = f"{col_letter}2:{col_letter}{ws_h.max_row}"
                rule = ColorScaleRule(
                    start_type="num", start_value=1, start_color="C6EFCE",
                    mid_type="num", mid_value=max(2, thresholds[1]), mid_color="FFEB9C",
                    end_type="num", end_value=max(3, thresholds[2]+1), end_color="F8CBAD"
                )
                ws_h.conditional_formatting.add(rng, rule)

        for name in wb.sheetnames:
            ws = wb[name]
            ws.page_setup.fitToWidth = 1
            ws.page_setup.fitToHeight = 0

    bio.seek(0)
    return bio.read()

# =========================
# 6) Session-Init
# =========================
def init_session():
    if "assessment" not in st.session_state or st.session_state.get("assessment") is None:
        st.session_state.assessment = Assessment(
            company="Musterbetrieb GmbH", location="Beispielstadt",
            created_at=date.today().isoformat(), created_by="SiFa",
            industry="Hotel/Gastgewerbe",
        )
        preload_industry(st.session_state.assessment, "Hotel/Gastgewerbe", replace=True)
    for key, df in DEFAULT_TABLES.items():
        if key not in st.session_state:
            st.session_state[key] = df.copy()
    if "opt_split_multi_hazards" not in st.session_state

