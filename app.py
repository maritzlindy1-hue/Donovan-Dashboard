
from flask import Flask, render_template
import pandas as pd
from datetime import datetime
import math

app = Flask(__name__, template_folder="templates")
EXCEL_FILE = "Donovan_JC_Live_Dashboard.xlsx"


def safe_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()


def classify_commodity(job_type: str, desc: str = ""):
    text = f"{safe_str(job_type)} {safe_str(desc)}".lower()
    has_water = "water" in text or "flowiq" in text
    has_elec = "elec" in text or "elect" in text or "kva" in text or "omnipower" in text
    if has_water and has_elec:
        return "Mixed"
    if has_water:
        return "Water"
    if has_elec:
        return "Electrical"
    return "Other"


def simplify_status(status: str):
    s = safe_str(status)
    if not s:
        return "Unknown"
    if "_" in s:
        parts = s.split("_", 2)
        if len(parts) >= 3:
            return parts[2]
    return s


def derive_kpi_stage(days_overall):
    try:
        d = float(days_overall)
    except Exception:
        return "Unknown"
    if d <= 2:
        return "Day 0-2 Remote troubleshoot"
    if d <= 5:
        return "Day 3-5 Client follow-up"
    if d <= 6:
        return "Day 6 Escalation due"
    return "Over Day 6"


def derive_priority(days_overall):
    try:
        d = float(days_overall)
    except Exception:
        return "Unknown"
    if d > 6:
        return "Critical"
    if d >= 4:
        return "Warning"
    return "Healthy"


def load_data():
    raw = pd.read_excel(EXCEL_FILE, sheet_name="Report Job Card List")

    # filter Donovan active items
    if "Assigned To" in raw.columns:
        raw = raw[raw["Assigned To"].astype(str).str.contains("Donovan", case=False, na=False)]
    if "Is Active" in raw.columns:
        raw = raw[raw["Is Active"] == True]

    raw = raw.copy()
    raw["Commodity"] = raw.apply(lambda r: classify_commodity(r.get("Job Type", ""), r.get("Description", "")), axis=1)
    raw["Step"] = raw.get("Job Status", raw.get("Current Status", "")).apply(simplify_status)
    raw["KPI Stage"] = raw["Days Overall"].apply(derive_kpi_stage)
    raw["Priority"] = raw["Days Overall"].apply(derive_priority)
    raw["Customer"] = raw["Customer"].fillna("")
    raw["Contact"] = raw["Contact"].fillna("")
    raw["Email"] = raw["Email"].fillna("")
    raw["Mobile"] = raw["Mobile"].fillna("")
    raw["Next Required Action"] = raw["Next Required Action"].fillna("Review JC and update next action")
    raw["Job Number"] = raw["Job Number"].fillna("")
    raw["Days Overall"] = pd.to_numeric(raw["Days Overall"], errors="coerce").fillna(0)
    raw["Days In Status"] = pd.to_numeric(raw["Days In Status"], errors="coerce").fillna(0)
    raw["Modified Date"] = pd.to_datetime(raw["Modified Date"], errors="coerce")
    raw = raw.sort_values(["Days Overall", "Days In Status"], ascending=[False, False])
    return raw


@app.route("/")
def dashboard():
    df = load_data()

    total = len(df)
    critical = int((df["Priority"] == "Critical").sum())
    warning = int((df["Priority"] == "Warning").sum())
    healthy = int((df["Priority"] == "Healthy").sum())
    avg_age = round(df["Days Overall"].mean(), 1) if total else 0

    status_counts = df["Step"].value_counts().head(10)
    kpi_counts = df["KPI Stage"].value_counts()
    commodity_counts = df["Commodity"].value_counts()
    priority_counts = df["Priority"].value_counts()

    top_overdue = df[[
        "Job Number", "Customer", "Commodity", "Job Type", "Step", "Days Overall",
        "Days In Status", "Next Required Action", "Contact", "Email", "Mobile"
    ]].head(20).copy()

    tickets = df[[
        "Job Number", "Customer", "Commodity", "Job Type", "Step", "Days Overall",
        "Days In Status", "KPI Stage", "Priority", "Next Required Action", "Contact",
        "Email", "Mobile", "Description", "Modified Date"
    ]].copy()

    tickets["Modified Date"] = tickets["Modified Date"].dt.strftime("%Y-%m-%d %H:%M").fillna("")
    top_overdue = top_overdue.to_dict(orient="records")
    tickets = tickets.to_dict(orient="records")

    chart_data = {
        "status_labels": list(status_counts.index),
        "status_values": [int(v) for v in status_counts.values],
        "kpi_labels": list(kpi_counts.index),
        "kpi_values": [int(v) for v in kpi_counts.values],
        "commodity_labels": list(commodity_counts.index),
        "commodity_values": [int(v) for v in commodity_counts.values],
        "priority_labels": list(priority_counts.index),
        "priority_values": [int(v) for v in priority_counts.values],
    }

    return render_template(
        "index.html",
        total=total,
        critical=critical,
        warning=warning,
        healthy=healthy,
        avg_age=avg_age,
        updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        top_overdue=top_overdue,
        tickets=tickets,
        chart_data=chart_data,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
