# -*- coding: utf-8 -*-
"""
SiFa Toolkit – Multi‑Modul App (Ein‑Datei, Streamlit)

Ziel: Mehrmodul-App für die Arbeit einer Fachkraft für Arbeitssicherheit (SiFa).
Die Gefährdungsbeurteilung ist nur EIN Modul unter mehreren (Wissen, Beratung,
Organisation/PDCA, Arbeitssystem, Arbeitsaufgaben, mechanische Einwirkungen,
SiFa‑Rolle, Dokumentation/Export).

Hinweis: Dieses Grundgerüst kann 1:1 auf Streamlit Community Cloud laufen.
Dateiname lokal: sifa_toolkit_multi.py

Schwerpunkte:
- Sidebar-Navigation zwischen Modulen
- Leichte, robuste Session‑Verwaltung
- Datenklassen für GB‑Objekte (Hazard/Measure/Assessment) – minimal
- Checklisten & Leitfragen aus den Wissensbausteinen als interaktive UI
- Platzhalter für künftige Tiefe (z.B. Maßnahmen‑Wirksamkeit, Doku‑Generator)

License: MIT
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Tuple
import re

import pandas as pd
import streamlit as st

# =========================
# Basis: App‑Config
# =========================

st.set_page_config(
    page_title="SiFa Toolkit – Multi‑Modul",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================
# GB – Datenklassen (leicht)
# =========================

STOP_LEVELS = [
    "S (Substitution/Quelle entfernen)",
    "T (Technisch)",
    "O (Organisatorisch)",
    "P (PSA)",
    "Q (Qualifikation/Unterweisung)",
]
STATUS_LIST = ["offen", "in Umsetzung", "wirksam", "nicht wirksam", "entfallen"]

@dataclass
class Measure:
    title: str
    stop_level: str = "O (Organisatorisch)"
    responsible: str = ""
    due_date: Optional[str] = None
    status: str = "offen"
    notes: str = ""

@dataclass
class Hazard:
    id: str
    area: str
    activity: str
    hazard: str
    sources: List[str] = field(default_factory=list)
    existing_controls: List[str] = field(default_factory=list)
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
    company: str = "Musterbetrieb GmbH"
    location: str = "Beispielstadt"
    created_at: str = date.today().isoformat()
    created_by: str = "SiFa/HSE"
    industry: str = "Allgemein"
    scope_note: str = ""
    risk_matrix_thresholds: Dict[str, List[int]] = field(default_factory=lambda: {"thresholds": [6, 12, 16]})
    hazards: List[Hazard] = field(default_factory=list)
    measures_plan_note: str = ""
    documentation_note: str = ""
    next_review_hint: str = ""

# =========================
# Utilities
# =========================

_SPLIT_PATTERN = re.compile(r"\s*(?:,|/| und | & )\s*")

def new_id(prefix="HZ", n=4) -> str:
    ts = datetime.now().strftime("%y%m%d%H%M%S%f")[-n:]
    return f"{prefix}-{int(datetime.now().timestamp())}-{ts}"


def split_hazard_text(text: str) -> List[str]:
    if not text:
        return []
    parts = [p.strip() for p in _SPLIT_PATTERN.split(text) if p and p.strip()]
    seen, uniq = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq or [text.strip()]


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


def hazard_to_row(h: Hazard) -> Dict[str, Any]:
    return {
        "ID": h.id,
        "Bereich": h.area,
        "Tätigkeit": h.activity,
        "Gefährdung": h.hazard,
        "Quellen/Einwirkungen": "; ".join(h.sources),
        "Bestehende Maßnahmen": "; ".join(h.existing_controls),
        "Eintrittswahrscheinlichkeit (1-5)": h.prob,
        "Schadensschwere (1-5)": h.sev,
        "Risikosumme": h.risk_value,
        "Risikostufe": h.risk_level,
        "Letzte Prüfung": h.last_review or "",
        "Prüfer/in": h.reviewer,
        "Dokumentationshinweis": h.documentation_note,
    }


# =========================
# Session init
# =========================

if "assessment" not in st.session_state:
    st.session_state.assessment = Assessment()
if "opt_split_multi_hazards" not in st.session_state:
    st.session_state.opt_split_multi_hazards = True

assess: Assessment = st.session_state.assessment

# =========================
# Sidebar: Stammdaten & Navigation
# =========================

st.sidebar.title("SiFa Toolkit – Module")
module = st.sidebar.radio(
    "Modul wählen",
    [
        "🏠 Dashboard",
        "🧭 Gesamtkonzept (GDA/Prozess)",
        "🧩 Arbeitssystem (Modell)",
        "🗂️ Arbeitsaufgabe",
        "🛡️ Mechanische Einwirkungen",
        "🏢 Organisation & Management (PDCA)",
        "🧑‍💼 SiFa‑Rolle & Beratung",
        "📝 Gefährdungsbeurteilung",
        "📦 Dokumente & Export",
    ],
)

st.sidebar.markdown("---")
st.sidebar.subheader("Stammdaten")
assess.company = st.sidebar.text_input("Unternehmen", assess.company)
assess.location = st.sidebar.text_input("Standort", assess.location)
assess.created_by = st.sidebar.text_input("Erstellt von", assess.created_by)
assess.created_at = st.sidebar.text_input("Erstellt am (ISO)", assess.created_at)
assess.industry = st.sidebar.text_input("Branche", assess.industry)

st.sidebar.checkbox(
    "Mehrfach‑Gefährdungen beim Hinzufügen automatisch auftrennen",
    key="opt_split_multi_hazards",
)

# =========================
# Modul‑Render‑Funktionen
# =========================

def ui_dashboard():
    st.title("🏠 SiFa Toolkit – Dashboard")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Gefährdungen im Projekt", len(assess.hazards))
    with c2:
        open_measures = sum(
            1 for h in assess.hazards for m in h.additional_measures if m.status == "offen"
        )
        st.metric("Maßnahmen offen", open_measures)
    with c3:
        st.metric("Branche", assess.industry)

    st.markdown("---")
    st.subheader("Schnellzugriff")
    st.write("• Prozessleitfaden GDA • Arbeitssystem‑Check • Mechanik‑Gefährdungsgruppen • PDCA‑Board • GB‑Editor • Doku")


def ui_gda_prozess():
    st.title("🧭 Gesamtkonzept – Beurteilung der Arbeitsbedingungen (GDA)")
    st.caption("Mini‑Leitfaden: Zweck, Gegenstand, Mindestanforderungen, Dokumentation, Fortschreibung")

    with st.expander("1) Zweck der Beurteilung (ArbSchG) – Kernpunkte"):
        st.checkbox("Maßnahmen des Arbeitsschutzes festlegen und umsetzen (Grundpflichten ArbSchG)")
        st.checkbox("Systematik sicherstellen: Ermitteln → Beurteilen → Gestalten → Umsetzen → Wirksamkeit prüfen → Fortschreiben")

    with st.expander("2) Gegenstand der Beurteilung – Tätigkeit & Arbeitssystem"):
        st.checkbox("Alle Tätigkeiten abdecken (vorhandene & vorhersehbare)")
        st.checkbox("Quellen von Gefährdungen, Belastungen, Ressourcen einbeziehen")
        st.text_area("Beschreibung des betrachteten Arbeitssystems (Grenzen/Schnittstellen)")

    with st.expander("3) Mindestanforderungen (GDA‑Leitlinie) – Checkliste"):
        st.checkbox("Gefährdungen/Belastungen/Ressourcen ermittelt & dokumentiert")
        st.checkbox("Konkrete Maßnahmen inkl. Termin & Verantwortliche festgelegt")
        st.checkbox("Wirksamkeit geprüft & Nachsteuerung geplant")

    with st.expander("4) Dokumentation & Fortschreibung"):
        assess.documentation_note = st.text_area("Dokumentationshinweise (Was, wie, wo? – Nachweisführung)", value=assess.documentation_note)
        assess.next_review_hint = st.text_input("Anlass/Frist für Fortschreibung (Termin, Ereignis)", value=assess.next_review_hint)


def ui_arbeitssystem():
    st.title("🧩 Arbeitssystem – Modell & Elemente")
    st.caption("Elemente: Arbeitsaufgabe • Person(en) • Arbeitsmittel • Arbeitsablauf/-verfahren • Arbeitsplatz/Arbeitsstätte • Arbeitsorganisation • Arbeitsumgebung")

    cols = st.columns(3)
    sys_desc = cols[0].text_area("Arbeitsaufgabe (Zweck, Output)")
    persons = cols[1].text_area("Person(en) / Rollen")
    tools = cols[2].text_area("Arbeitsmittel / Software / Mobiliar")

    cols2 = st.columns(3)
    process = cols2[0].text_area("Ablauf/Verfahren (inkl. Betriebszustände)")
    place = cols2[1].text_area("Arbeitsplatz/Arbeitsstätte (baulich, Umfeld)")
    orga = cols2[2].text_area("Organisation (Verantwortung, Schnittstellen)")

    with st.expander("Arbeitsumgebung & Wechselwirkungen"):
        st.text_area("Umgebungsfaktoren (z. B. Klima, Lärm, Licht) und Systemgrenzen")

    st.info("Nutze diese Struktur als Steckbrief pro Arbeitssystem. Verknüpfe anschließend mit GB‑Einträgen.")


def ui_arbeitsaufgabe():
    st.title("🗂️ Arbeitsaufgabe – Anforderungen & Gestaltung")
    st.caption("Vollständige Tätigkeiten • Aufgabenorientierung • Kriterien menschengerechter Gestaltung")

    with st.expander("Erfassen & Gliedern"):
        st.text_area("Gesamtarbeitsaufgabe (Beschreibung)")
        st.text_area("Teil-/Unterarbeitsaufgaben (Liste)")

    with st.expander("Vier Merkmale je Arbeitsaufgabe"):
        st.select_slider("Vielfalt der Tätigkeiten", options=["gering", "mittel", "hoch"])
        st.selectbox("Art der Tätigkeiten", ["planend", "ausführend", "kontrollierend", "gemischt"])
        st.selectbox("Arbeitsform", ["vorwiegend körperlich", "vorwiegend geistig", "gemischt"])
        st.text_area("Anforderungen (physisch/psychisch, Kenntnisse, Verantwortung)")

    with st.expander("Gestaltungskriterien – Häkchen setzen"):
        st.checkbox("Ganzheitlichkeit / Rückmeldung aus Tätigkeit")
        st.checkbox("Anforderungsvielfalt (Planen‑Ausführen‑Kontrollieren)")
        st.checkbox("Soziale Interaktion / Kooperation")
        st.checkbox("Autonomie / Entscheidungsspielräume")
        st.checkbox("Lern‑ & Entwicklungsmöglichkeiten")


def ui_mechanik():
    st.title("🛡️ Mechanische Einwirkungen – Ermitteln • Beurteilen • Gestalten")
    st.caption("Gruppen: 1) kontrolliert bewegte Teile 2) bewegte Arbeits-/Transportmittel 3) unkontrolliert bewegte Teile 4) gefährliche Oberflächen 5) Sturz 6) Absturz")

    grp = st.selectbox(
        "Einwirkungsgruppe", [
            "1 – kontrolliert bewegte ungeschützte Teile",
            "2 – bewegte Arbeits-/Transportmittel/Fahrzeuge",
            "3 – unkontrolliert bewegte Teile",
            "4 – Teile mit gefährlichen Oberflächen",
            "5 – Sturz",
            "6 – Absturz",
        ]
    )
    st.text_area("Typische Quellen / vorhersehbare Bedingungen", key=f"mech_src_{grp}")
    st.text_area("Schutzprinzipien / Gestaltungsansätze (S‑T‑O‑P‑Q)", key=f"mech_sol_{grp}")


def ui_pdca():
    st.title("🏢 Organisation & Management – PDCA & Aufbau/Ablauf")
    st.caption("Arbeitsschutz in die Führungsorganisation integrieren; kontinuierlich verbessern")

    c1, c2, c3, c4 = st.columns(4)
    c1.text_area("Plan – Ziele/Planung (Ziele, Programm, Verantwortliche, Ressourcen)")
    c2.text_area("Do – Umsetzung (Maßnahmen, Kommunikation, Unterweisung)")
    c3.text_area("Check – Überprüfen (Kennzahlen, Audits, Wirksamkeit)")
    c4.text_area("Act – Verbessern (Korrektur/Prävention, Standards anpassen)")

    with st.expander("Aufbau- & Ablauforganisation"):
        st.text_area("Aufbau: Rollen, Stabsstelle SiFa, Vertretungen")
        st.text_area("Ablauf: Prozesse, Schnittstellen, Dokumentation")


def ui_sifa_beratung():
    st.title("🧑‍💼 SiFa‑Rolle & Beratung – Strategie & Phasen")
    st.caption("Unterstützen, beobachten, beraten, auf Maßnahmen hinwirken, Wirksamkeit prüfen – ohne Weisungsbefugnis")

    with st.expander("Beratungsstrategie (2‑Schritt)"):
        st.text_area("1) Analyse des Betriebs als System (IST, Relevanz, Stakeholder)")
        st.text_area("2) Vorgehen planen (Ziele, Roadmap, Anschlussfähigkeit)")

    with st.expander("Phasen der Beratung"):
        st.checkbox("Kontakt & Auftragsklärung")
        st.checkbox("Analyse & Zielvereinbarung")
        st.checkbox("Intervention/Umsetzung begleiten")
        st.checkbox("Evaluation & Abschluss")


# --- Gefährdungsbeurteilung (Editor) ---

def ui_gb_editor():
    st.title("📝 Gefährdungsbeurteilung – Editor")

    thr = assess.risk_matrix_thresholds.get("thresholds", [6, 12, 16])
    cL, cR = st.columns([2, 1])
    with cR:
        st.subheader("Risikomatrix‑Grenzen")
        low = st.number_input("niedrig (≤)", 2, 10, value=int(thr[0]))
        mid = st.number_input("mittel (≤)", low + 1, 16, value=int(thr[1]))
        high = st.number_input("hoch (≤)", mid + 1, 24, value=int(thr[2]))
        assess.risk_matrix_thresholds["thresholds"] = [low, mid, high]

    with cL:
        st.subheader("Gefährdungen – Tabelle")
        if assess.hazards:
            df = pd.DataFrame([hazard_to_row(h) for h in assess.hazards])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Noch keine Einträge – unten hinzufügen.")

    with st.expander("➕ Gefährdung hinzufügen"):
        c1, c2 = st.columns(2)
        area = c1.text_input("Bereich")
        activity = c2.text_input("Tätigkeit")
        hazard_txt = st.text_input("Gefährdung(en) – Komma/Slash/‚und‘ trennen")
        sources = st.text_input("Quellen/Einwirkungen (; getrennt)")
        existing = st.text_input("Bestehende Maßnahmen (; getrennt)")
        if st.button("Hinzufügen"):
            items = split_hazard_text(hazard_txt) if st.session_state.get("opt_split_multi_hazards", True) else [hazard_txt]
            for hz in items:
                v, lvl = compute_risk(3, 3, assess.risk_matrix_thresholds["thresholds"])
                assess.hazards.append(
                    Hazard(
                        id=new_id(),
                        area=area,
                        activity=activity,
                        hazard=hz,
                        sources=[s.strip() for s in sources.split(";") if s.strip()],
                        existing_controls=[e.strip() for e in existing.split(";") if e.strip()],
                        risk_value=v,
                        risk_level=lvl,
                    )
                )
            st.success(f"{len(items)} Eintrag(e) hinzugefügt.")

    st.markdown("---")
    st.subheader("Detail bearbeiten / Maßnahmen")
    ids = [h.id for h in assess.hazards]
    sel = st.selectbox("Gefährdung wählen (ID)", options=["--"] + ids)
    if sel != "--":
        h = next(x for x in assess.hazards if x.id == sel)
        c1, c2 = st.columns(2)
        h.area = c1.text_input("Bereich", h.area, key=f"edit_area_{h.id}")
        h.activity = c2.text_input("Tätigkeit", h.activity, key=f"edit_act_{h.id}")
        h.hazard = st.text_input("Gefährdung (einzeln)", h.hazard, key=f"edit_hz_{h.id}")

        c3, c4 = st.columns(2)
        src = c3.text_area("Quellen", "; ".join(h.sources), key=f"src_{h.id}")
        ex = c4.text_area("Bestehende Maßnahmen", "; ".join(h.existing_controls), key=f"ex_{h.id}")
        h.sources = [s.strip() for s in src.split(";") if s.strip()]
        h.existing_controls = [e.strip() for e in ex.split(";") if e.strip()]

        c5, c6, c7 = st.columns(3)
        h.prob = c5.slider("Eintrittswahrsch. (1-5)", 1, 5, value=h.prob)
        h.sev = c6.slider("Schadensschwere (1-5)", 1, 5, value=h.sev)
        h.risk_value, h.risk_level = compute_risk(h.prob, h.sev, assess.risk_matrix_thresholds["thresholds"])
        c7.metric("Risiko", f"{h.risk_value}", h.risk_level)

        st.markdown("**Zusätzliche Maßnahmen (STOP+Q)**")
        with st.expander("➕ Maßnahme hinzufügen"):
            cA, cB = st.columns([0.6, 0.4])
            mtitle = cA.text_input("Titel", key=f"mtitle_{h.id}")
            mstop = cB.selectbox("STOP(+Q)", STOP_LEVELS, key=f"mstop_{h.id}")
            cC, cD, cE = st.columns([0.34, 0.33, 0.33])
            mresp = cC.text_input("Verantwortlich", key=f"mresp_{h.id}")
            mdue = cD.text_input("Fällig (ISO)", key=f"mdue_{h.id}")
            mnote = cE.text_input("Hinweis", key=f"mnotes_{h.id}")
            if st.button("Hinzufügen", key=f"btn_add_m_{h.id}"):
                h.additional_measures.append(Measure(title=mtitle, stop_level=mstop, responsible=mresp, due_date=mdue, notes=mnote))
                st.success("Maßnahme hinzugefügt.")

        if h.additional_measures:
            mdf = pd.DataFrame([
                {
                    "Maßnahme": m.title,
                    "STOP(+Q)": m.stop_level,
                    "Verantwortlich": m.responsible,
                    "Fällig": m.due_date or "",
                    "Status": m.status,
                    "Hinweis": m.notes,
                }
                for m in h.additional_measures
            ])
            st.dataframe(mdf, use_container_width=True, hide_index=True)

        cdel, cdoc = st.columns([0.2, 0.8])
        if cdel.button("🗑️ Eintrag löschen", key=f"del_{h.id}"):
            assess.hazards = [x for x in assess.hazards if x.id != h.id]
            st.warning("Gefährdung gelöscht.")
            st.experimental_rerun()
        h.documentation_note = cdoc.text_input("Dokumentationshinweis (Wirksamkeit/Begründung)", value=h.documentation_note)


# --- Dokumente & Export (JSON) ---

def ui_docs_export():
    st.title("📦 Dokumente & Export")

    st.subheader("JSON – komplette Beurteilung sichern/laden")
    blob = json.dumps(asdict(assess), ensure_ascii=False, indent=2)
    st.download_button("⬇️ Download JSON", data=blob, file_name="sifa_assessment.json", mime="application/json")

    up = st.file_uploader("Vorhandene JSON laden", type=["json"]) 
    if up is not None:
        try:
            data = json.loads(up.read().decode("utf-8"))
            # Minimal robustes Mapping
            hazards: List[Hazard] = []
            for h in data.get("hazards", []):
                ms = [Measure(**m) for m in h.get("additional_measures", [])]
                hazards.append(
                    Hazard(
                        id=h.get("id", new_id()),
                        area=h.get("area", ""),
                        activity=h.get("activity", ""),
                        hazard=h.get("hazard", ""),
                        sources=h.get("sources", []),
                        existing_controls=h.get("existing_controls", h.get("existing", [])),
                        prob=int(h.get("prob", 3)),
                        sev=int(h.get("sev", 3)),
                        risk_value=int(h.get("risk_value", 9)),
                        risk_level=h.get("risk_level", "mittel"),
                        additional_measures=ms,
                        last_review=h.get("last_review"),
                        reviewer=h.get("reviewer", ""),
                        documentation_note=h.get("documentation_note", ""),
                    )
                )
            st.session_state.assessment = Assessment(
                company=data.get("company", assess.company),
                location=data.get("location", assess.location),
                created_at=data.get("created_at", assess.created_at),
                created_by=data.get("created_by", assess.created_by),
                industry=data.get("industry", assess.industry),
                scope_note=data.get("scope_note", assess.scope_note),
                risk_matrix_thresholds=data.get("risk_matrix_thresholds", assess.risk_matrix_thresholds),
                hazards=hazards,
                measures_plan_note=data.get("measures_plan_note", assess.measures_plan_note),
                documentation_note=data.get("documentation_note", assess.documentation_note),
                next_review_hint=data.get("next_review_hint", assess.next_review_hint),
            )
            st.success("JSON geladen.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")

# =========================
# Router
# =========================

if module == "🏠 Dashboard":
    ui_dashboard()
elif module == "🧭 Gesamtkonzept (GDA/Prozess)":
    ui_gda_prozess()
elif module == "🧩 Arbeitssystem (Modell)":
    ui_arbeitssystem()
elif module == "🗂️ Arbeitsaufgabe":
    ui_arbeitsaufgabe()
elif module == "🛡️ Mechanische Einwirkungen":
    ui_mechanik()
elif module == "🏢 Organisation & Management (PDCA)":
    ui_pdca()
elif module == "🧑‍💼 SiFa‑Rolle & Beratung":
    ui_sifa_beratung()
elif module == "📝 Gefährdungsbeurteilung":
    ui_gb_editor()
elif module == "📦 Dokumente & Export":
    ui_docs_export()

# Ende
