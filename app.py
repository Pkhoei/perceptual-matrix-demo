"""Perceptual Matrix - Soundwalk Pilot v0.10.

Minimal, English-only Streamlit interface for a single-researcher pilot.
Run with: streamlit run app.py

This prototype captures subjective listening experiences. Schafer-inspired sound
roles and Westerkamp-inspired attention prompts are not validated questionnaires.
The two derived indicators are exploratory arithmetic on ordinal responses.
"""

from __future__ import annotations

import csv
import html
import math
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "perceptual_matrix_data"
OBS_FILE = DATA_DIR / "observations_v010.csv"
EVENT_FILE = DATA_DIR / "sound_events_v010.csv"

RATING_ANCHORS = {
    "Pleasantness": ("Very unpleasant", "Very pleasant"),
    "Loudness": ("Very quiet", "Very loud"),
    "Tension": ("No tension", "Very high tension"),
    "Attention": ("No attention drawn", "Very strong attention"),
}
LABELS = ["Calm", "Restorative", "Lively", "Stressful", "Intrusive", "Neutral"]
SOUND_ROLES = [
    "Keynote / Background",
    "Signal / Attention-getting",
    "Soundmark / Place-distinctive",
]
REASONS = ["Uncertain between interpretations", "Both interpretations coexist"]
HEATMAP_COLORS = ["#e8f0f7", "#c4d8e8", "#94b9d1", "#568aaa", "#285774"]

OBS_COLUMNS = [
    "observation_id", "timestamp", "soundwalk_id", "participant_id", "place",
    "route_segment", "assessment_scope", "event_count", "most_noticeable_event_id",
    "most_noticeable_sound", "sound_layering", "source_distinguishability",
    "pleasantness", "loudness", "tension", "attention", "primary_interpretation",
    "secondary_interpretation", "secondary_reason", "listening_effort",
    "emotional_balance", "optional_note",
]
EVENT_COLUMNS = [
    "observation_id", "soundwalk_id", "participant_id", "event_id",
    "event_order", "sound_event", "pleasantness", "loudness",
    "sound_roles", "most_noticeable",
]


def write_csv_rows(path: Path, columns: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        if needs_header:
            writer.writeheader()
        writer.writerows(rows)


def save_linked_csv(observation: dict, events: list[dict]) -> None:
    """Append both files; restore their previous sizes if either append fails.

    Intended for one local researcher, not multiple simultaneous writers.
    """
    paths = [(EVENT_FILE, EVENT_COLUMNS, events), (OBS_FILE, OBS_COLUMNS, [observation])]
    backups = {path: (path.exists(), path.stat().st_size if path.exists() else 0)
               for path, _columns, _rows in paths}
    try:
        for path, columns, rows in paths:
            write_csv_rows(path, columns, rows)
    except Exception:
        for path, (existed, original_bytes) in backups.items():
            if path.exists():
                if existed:
                    with path.open("r+b") as stream:
                        stream.truncate(original_bytes)
                else:
                    path.unlink()
        raise


def already_saved(soundwalk_id: str, participant_id: str) -> bool:
    if not OBS_FILE.exists():
        return False
    with OBS_FILE.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if (row.get("soundwalk_id", "").strip().casefold() == soundwalk_id.strip().casefold()
                    and row.get("participant_id", "").strip().casefold() == participant_id.strip().casefold()):
                return True
    return False


def indicators(ratings: dict[str, int]) -> dict[str, int]:
    return {
        "listening_effort": ratings["Attention"] * ratings["Tension"],
        "emotional_balance": ratings["Pleasantness"] - ratings["Tension"],
    }


def heatmap_value(value: object) -> tuple[str, str, str]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-", "#eceff2", "#616c76"
    if not math.isfinite(number) or not 1 <= number <= 5:
        return "-", "#eceff2", "#616c76"
    index = min(4, max(0, int(round(number)) - 1))
    label = str(int(number)) if number.is_integer() else f"{number:.1f}"
    return label, HEATMAP_COLORS[index], "#fff" if index >= 3 else "#223b4f"


def show_heatmap(rows: list[tuple[str, dict]], max_rows: int = 30) -> None:
    if not rows:
        st.info("No scores available.")
        return
    table = ['<div style="overflow-x:auto"><table style="border-collapse:collapse;'
             'font:13px Arial,sans-serif;width:100%;min-width:475px">']
    table.append('<thead><tr><th style="padding:8px;text-align:left;border:1px solid #c9d5df">'
                 'Assessment</th>')
    for dimension in RATING_ANCHORS:
        table.append(f'<th style="padding:8px;border:1px solid #c9d5df">'
                     f'{html.escape(dimension)}</th>')
    table.append('</tr></thead><tbody>')
    for title, values in rows[-max_rows:]:
        table.append(f'<tr><th style="padding:8px;text-align:left;border:1px solid #c9d5df;'
                     f'background:#f5f7f9;white-space:nowrap">{html.escape(str(title))}</th>')
        for dimension in RATING_ANCHORS:
            label, background, foreground = heatmap_value(values.get(dimension))
            table.append(f'<td style="padding:10px;text-align:center;border:1px solid #c9d5df;'
                         f'background:{background};color:{foreground};font-weight:bold">'
                         f'{label}</td>')
        table.append('</tr>')
    table.append('</tbody></table></div>')
    st.markdown(''.join(table), unsafe_allow_html=True)
    st.caption("Heatmap: 1 = light; 5 = dark; gray = missing. Darker does not mean better.")


def add_sound_event() -> None:
    name = st.session_state.get("new_event_name", "").strip()
    if not name:
        st.session_state["event_warning"] = "Enter a sound name before adding it."
        return
    if len(name) > 100:
        st.session_state["event_warning"] = "Sound names must be 100 characters or fewer."
        return
    st.session_state["events"].append({"id": uuid4().hex[:12], "name": name})
    st.session_state["new_event_name"] = ""
    st.session_state["event_warning"] = ""


def remove_sound_event(event_id: str) -> None:
    st.session_state["events"] = [e for e in st.session_state["events"] if e["id"] != event_id]
    if st.session_state.get("most_noticeable") == event_id:
        st.session_state["most_noticeable"] = "None"
    for prefix in ("event_pleasantness", "event_loudness", "event_roles"):
        st.session_state.pop(f"{prefix}::{event_id}", None)


def new_participant() -> None:
    """Keep walk and place, clear participant-specific answers."""
    keys = [
        "participant_id", "route_segment", "new_event_name", "events", "event_warning",
        "most_noticeable", "sound_layering", "source_distinguishability",
        "primary_interpretation", "secondary_interpretation", "secondary_reason",
        "optional_note", "last_saved_id",
    ]
    keys += [f"matrix::{key}" for key in RATING_ANCHORS]
    keys += [key for key in st.session_state if key.startswith((
        "event_pleasantness::", "event_loudness::", "event_roles::"))]
    for key in keys:
        st.session_state.pop(key, None)
    st.session_state["events"] = []


# ----------------------------------- Interface -----------------------------------
st.set_page_config(page_title="Perceptual Matrix | Pilot v0.10", layout="centered")
if "events" not in st.session_state:
    st.session_state["events"] = []

st.title("Perceptual Matrix")
st.caption("Soundwalk Research Pilot v0.10")
st.button("New Participant", on_click=new_participant)

st.subheader("1. Listening & Sound Events")

st.markdown("**Listen to a Recording (optional)**")
audio_files = sorted((APP_DIR / "audio").glob("*.wav"))
if audio_files:
    selected_audio = st.selectbox(
        "Choose a sound",
        range(len(audio_files)),
        format_func=lambda i: f"Sound {i + 1:03d}",
        key="selected_audio",
    )
    st.audio(audio_files[selected_audio].read_bytes(), format="audio/wav")
else:
    st.info("No WAV recordings found in the audio folder.")

walk_col, person_col = st.columns(2)
with walk_col:
    soundwalk_id = st.text_input("Soundwalk ID *", placeholder="SW001", key="soundwalk_id")
with person_col:
    participant_id = st.text_input("Participant ID *", placeholder="P001", key="participant_id")
place = st.text_input("Place / Study Area *", placeholder="City square", key="place")
with st.expander("Route details (optional)"):
    route_segment = st.text_input("Participant-selected route / segment", key="route_segment")

st.markdown("**Sounds noticed**")
e1, e2 = st.columns([4, 1])
with e1:
    st.text_input("Sound name", placeholder="e.g. Traffic, footsteps, birds", key="new_event_name")
with e2:
    st.write(" ")
    st.button("Add", on_click=add_sound_event, use_container_width=True)
if st.session_state.get("event_warning"):
    st.warning(st.session_state["event_warning"])

for event_number, event in enumerate(st.session_state["events"], start=1):
    left, right = st.columns([5, 1])
    left.write(f"{event_number}. {event['name']}")
    right.button("Remove", key=f"remove::{event['id']}",
                 on_click=remove_sound_event, args=(event["id"],))
    with st.expander(f"Optional event ratings / sound roles - {event_number}"):
        r1, r2 = st.columns(2)
        with r1:
            st.selectbox("Pleasantness", [None, 1, 2, 3, 4, 5],
                         format_func=lambda v: "Not rated" if v is None else str(v),
                         key=f"event_pleasantness::{event['id']}")
        with r2:
            st.selectbox("Loudness", [None, 1, 2, 3, 4, 5],
                         format_func=lambda v: "Not rated" if v is None else str(v),
                         key=f"event_loudness::{event['id']}")
        st.caption("Event ratings: 1 = low; 5 = high.")
        st.multiselect("Sound role (optional)", SOUND_ROLES,
                       key=f"event_roles::{event['id']}")
        st.caption("Sound roles are participant-reported impressions, not verified classifications.")

if not st.session_state["events"]:
    st.caption("No sound events added yet.")

by_id = {event["id"]: event["name"] for event in st.session_state["events"]}
event_ids = [event["id"] for event in st.session_state["events"]]
if st.session_state.get("most_noticeable", "None") not in ["None", *event_ids]:
    st.session_state["most_noticeable"] = "None"
most_noticeable = st.selectbox(
    "Most noticeable sound", ["None", *event_ids],
    format_func=lambda value: "Not selected" if value == "None" else by_id[value],
    key="most_noticeable",
)
layering = st.radio(
    "Sound layering", ["One dominant sound", "Several simultaneous sounds", "Not sure"],
    index=None, horizontal=False, key="sound_layering",
)
source_distinguishability = ""
if layering == "Several simultaneous sounds":
    source_distinguishability = st.radio(
        "Could you distinguish the overlapping sound sources?",
        ["Clearly", "Partly", "Not clearly"], index=None,
        horizontal=True, key="source_distinguishability",
    )

st.divider()
st.subheader("2. Overall Perceptual Matrix")
st.caption("Rate the overall soundwalk, not each individual sound. Scale: 1 to 5.")
ratings: dict[str, int | None] = {}
for name, (low, high) in RATING_ANCHORS.items():
    ratings[name] = st.radio(
        name, [1, 2, 3, 4, 5], index=None, horizontal=True, key=f"matrix::{name}",
    )
    st.caption(f"1 = {low} | 5 = {high}")

all_rated = all(value is not None for value in ratings.values())
if all_rated:
    st.markdown("**Matrix Heatmap**")
    show_heatmap([(participant_id.strip() or "Current participant", ratings)])

st.divider()
st.subheader("3. Interpretation & Ambiguity")
primary_choices = ["Select an interpretation", *LABELS]
primary = st.selectbox("Primary interpretation *", primary_choices,
                       key="primary_interpretation")
secondary_choices = ["None", *[label for label in LABELS if label != primary]]
if st.session_state.get("secondary_interpretation", "None") not in secondary_choices:
    st.session_state["secondary_interpretation"] = "None"
secondary = st.selectbox("Secondary interpretation (optional)", secondary_choices,
                         key="secondary_interpretation")
reason = ""
if secondary != "None":
    reason = st.radio("Why a second interpretation?", REASONS,
                      index=None, key="secondary_reason")
with st.expander("Short listening note (optional)"):
    note = st.text_area("Participant's own words", height=75, key="optional_note")

st.divider()
st.subheader("4. Results & Save")
if all_rated:
    results = indicators(ratings)
    r1, r2 = st.columns(2)
    r1.metric("Listening Effort", f"{results['listening_effort']} / 25")
    r2.metric("Emotional Balance", f"{results['emotional_balance']} (-4 to +4)")
    st.caption("Exploratory indicators using ordinal ratings; not validated ISO measures.")
else:
    st.info("Rate all four matrix dimensions to calculate the exploratory indicators.")

if st.button("Save Assessment", type="primary", use_container_width=True):
    errors = []
    if not soundwalk_id.strip():
        errors.append("Enter Soundwalk ID.")
    if not participant_id.strip():
        errors.append("Enter Participant ID.")
    if not place.strip():
        errors.append("Enter Place / Study Area.")
    if not st.session_state["events"]:
        errors.append("Add at least one sound event.")
    if layering is None:
        errors.append("Select a sound-layering answer.")
    if layering == "Several simultaneous sounds" and source_distinguishability is None:
        errors.append("Select the source-distinguishability answer.")
    if not all_rated:
        errors.append("Complete all four overall matrix ratings.")
    if primary == "Select an interpretation":
        errors.append("Select a primary interpretation.")
    if secondary != "None" and reason is None:
        errors.append("Select why you chose a secondary interpretation.")
    if not errors:
        try:
            if already_saved(soundwalk_id, participant_id):
                errors.append("This participant already has an assessment for that Soundwalk ID.")
        except (OSError, csv.Error, UnicodeError) as exc:
            errors.append(f"Could not verify earlier assessments: {exc}")

    if errors:
        for message in errors:
            st.error(message)
    else:
        assessment_id = "OBS-" + uuid4().hex[:12].upper()
        result = indicators(ratings)
        observation = {
            "observation_id": assessment_id,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "soundwalk_id": soundwalk_id.strip(),
            "participant_id": participant_id.strip(),
            "place": place.strip(),
            "route_segment": route_segment.strip(),
            "assessment_scope": "overall_soundwalk",
            "event_count": len(event_ids),
            "most_noticeable_event_id": "" if most_noticeable == "None" else most_noticeable,
            "most_noticeable_sound": "" if most_noticeable == "None" else by_id[most_noticeable],
            "sound_layering": layering,
            "source_distinguishability": source_distinguishability or "",
            **{name.lower(): ratings[name] for name in RATING_ANCHORS},
            "primary_interpretation": primary,
            "secondary_interpretation": "" if secondary == "None" else secondary,
            "secondary_reason": "" if secondary == "None" else reason,
            **result,
            "optional_note": note.strip(),
        }
        event_rows = []
        for event_number, event in enumerate(st.session_state["events"], start=1):
            eid = event["id"]
            p = st.session_state.get(f"event_pleasantness::{eid}")
            l = st.session_state.get(f"event_loudness::{eid}")
            roles = st.session_state.get(f"event_roles::{eid}", [])
            event_rows.append({
                "observation_id": assessment_id,
                "soundwalk_id": soundwalk_id.strip(),
                "participant_id": participant_id.strip(),
                "event_id": eid,
                "event_order": event_number,
                "sound_event": event["name"],
                "pleasantness": "" if p is None else p,
                "loudness": "" if l is None else l,
                "sound_roles": " | ".join(roles),
                "most_noticeable": int(eid == most_noticeable),
            })
        try:
            save_linked_csv(observation, event_rows)
        except (OSError, csv.Error, UnicodeError, ValueError) as exc:
            st.error(f"Could not save the assessment: {exc}")
        else:
            st.success(f"Assessment saved: {assessment_id}")
            st.caption("To assess another person on the same walk, click New Participant.")

with st.expander("Saved data & comparison heatmap"):
    if OBS_FILE.exists():
        try:
            data = pd.read_csv(OBS_FILE, dtype={"participant_id": str, "soundwalk_id": str})
            st.dataframe(data.tail(25), use_container_width=True, hide_index=True)
            if not data.empty:
                matrix_rows = []
                for _, record in data.tail(25).iterrows():
                    title = (f"{record['participant_id']} | {record['place']} "
                             f"({record['soundwalk_id']})")
                    matrix_rows.append((title, {name: record[name.lower()]
                                               for name in RATING_ANCHORS}))
                show_heatmap(matrix_rows)
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError, KeyError) as exc:
            st.warning(f"Could not display saved assessments: {exc}")
        st.download_button("Download assessments CSV", OBS_FILE.read_bytes(),
                           OBS_FILE.name, "text/csv")
    else:
        st.caption("No saved assessments yet.")
    if EVENT_FILE.exists():
        st.download_button("Download sound events CSV", EVENT_FILE.read_bytes(),
                           EVENT_FILE.name, "text/csv")

st.caption("Pilot instrument. Interpretations, sound roles and derived scores are exploratory.")
