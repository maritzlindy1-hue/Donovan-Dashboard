
from flask import Flask, render_template
import pandas as pd
from datetime import datetime

app = Flask(__name__, template_folder="templates")
EXCEL_FILE = "Donovan_JC_Live_Dashboard.xlsx"
MORNING_BASELINE = 88
PREVIOUS_UPDATE = 86


def safe_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()


def get_sheet():
    xls = pd.ExcelFile(EXCEL_FILE)
    if "Report Job Card List" in xls.sheet_names:
        return "Report Job Card List"
    return xls.sheet_names[0]


def classify_commodity(job_type, desc="", materials="", assets=""):
    text = f"{safe_str(job_type)} {safe_str(desc)} {safe_str(materials)} {safe_str(assets)}".lower()
    has_water = any(x in text for x in ["water", "flowiq", "lora", "visio", "kamstrup flow"])
    has_elec = any(x in text for x in ["elec", "electrical", "omnipower", "kva", "ct", "server meter"])
    if has_water and has_elec:
        return "Mixed"
    if has_water:
        return "Water"
    if has_elec:
        return "Electrical"
    return "Other"


def simplify_status(status):
    s = safe_str(status)
    if not s:
        return "Unknown"
    if ">" in s:
        s = s.split(">")[-1].strip()
    if "_" in s:
        parts = s.split("_", 2)
        if len(parts) >= 3:
            return parts[2].replace("/", " / ")
    return s


def stage_group(status):
    text = safe_str(status).lower()
    if "troubleshoot" in text:
        return "Remote Troubleshoot"
    if "client feedback" in text:
        return "Awaiting Client Feedback"
    if "quote" in text:
        return "Quote / Approval"
    if "stock" in text:
        return "Stock / Logistics"
    if "schedule" in text or "install" in text or "commission" in text:
        return "Install / Commission"
    if "close" in text or "complete" in text:
        return "Complete / Close"
    return "Other Step"


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
    sheet = get_sheet()
    raw = pd.read_excel(EXCEL_FILE, sheet_name=sheet)
    raw.columns = [str(c).strip() for c in raw.columns]

    if "Assigned To" in raw.columns:
        raw = raw[raw["Assigned To"].astype(str).str.contains("Donovan", case=False, na=False)]
    if "Is Active" in raw.columns:
        raw = raw[raw["Is Active"].astype(str).str.lower().isin(["true", "yes", "1"])]
    elif "Closed" in raw.columns:
        raw = raw[~raw["Closed"].astype(str).str.lower().isin(["true", "yes", "1"])]

    raw = raw.copy()
    for col in ["Job Number", "Customer", "Job Type", "Description", "Materials", "Customer Assets", "Contact", "Email", "Mobile", "Next Required Action", "Job Status", "Status Flow", "Serial No"]:
        if col not in raw.columns:
            raw[col] = ""
    for col in ["Days Overall", "Days In Status"]:
        if col not in raw.columns:
            raw[col] = 0
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0).astype(int)

    raw["Commodity"] = raw.apply(lambda r: classify_commodity(r["Job Type"], r["Description"], r["Materials"], r["Customer Assets"]), axis=1)
    raw["Step"] = raw["Job Status"].apply(simplify_status)
    raw["Stage Group"] = raw["Job Status"].apply(stage_group)
    raw["KPI Stage"] = raw["Days Overall"].apply(derive_kpi_stage)
    raw["Priority"] = raw["Days Overall"].apply(derive_priority)
    raw["Next Required Action"] = raw["Next Required Action"].replace("", "Review JC and update next action")
    if "Modified Date" not in raw.columns:
        raw["Modified Date"] = ""
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
    closed_since_morning = max(MORNING_BASELINE - total, 0)
    change_since_previous = PREVIOUS_UPDATE - total

    def counts(col, top=None):
        vc = df[col].value_counts()
        if top:
            vc = vc.head(top)
        return list(vc.index), [int(v) for v in vc.values]

    status_labels, status_values = counts("Step", 10)
    stage_labels, stage_values = counts("Stage Group")
    kpi_labels, kpi_values = counts("KPI Stage")
    commodity_labels, commodity_values = counts("Commodity")
    priority_labels, priority_values = counts("Priority")

    cols = ["Job Number", "Customer", "Commodity", "Job Type", "Step", "Stage Group", "Days Overall", "Days In Status", "KPI Stage", "Priority", "Next Required Action", "Contact", "Email", "Mobile", "Serial No", "Description", "Modified Date"]
    tickets = df[cols].copy()
    tickets["Modified Date"] = tickets["Modified Date"].dt.strftime("%Y-%m-%d %H:%M").fillna("")
    top_overdue = tickets.head(20).to_dict(orient="records")
    tickets = tickets.to_dict(orient="records")

    chart_data = {
        "status_labels": status_labels, "status_values": status_values,
        "stage_labels": stage_labels, "stage_values": stage_values,
        "kpi_labels": kpi_labels, "kpi_values": kpi_values,
        "commodity_labels": commodity_labels, "commodity_values": commodity_values,
        "priority_labels": priority_labels, "priority_values": priority_values,
    }

    return render_template("index.html", total=total, critical=critical, warning=warning, healthy=healthy,
        avg_age=avg_age, updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        morning_baseline=MORNING_BASELINE, previous_update=PREVIOUS_UPDATE,
        closed_since_morning=closed_since_morning, change_since_previous=change_since_previous,
        top_overdue=top_overdue, tickets=tickets, chart_data=chart_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
