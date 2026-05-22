
from flask import Flask, render_template
import pandas as pd
from datetime import datetime

app = Flask(__name__, template_folder="templates")
CURRENT_FILE = "Job Card List 202605221448.xlsx"
MORNING_FILE = "Job Card List 202605220822.xlsx"


def safe_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()


def load_raw(path):
    df = pd.read_excel(path, sheet_name="Report Job Card List")
    if "Assigned To" in df.columns:
        df = df[df["Assigned To"].astype(str).str.contains("Donovan", case=False, na=False)]
    if "Is Active" in df.columns:
        df = df[df["Is Active"] == True]
    return df.copy()


def classify_commodity(job_type: str, desc: str = "", assets: str = ""):
    text = f"{safe_str(job_type)} {safe_str(desc)} {safe_str(assets)}".lower()
    has_water = any(x in text for x in ["water", "flowiq", "lora", "visio", "gateway"])
    has_elec = any(x in text for x in ["elec", "elect", "kva", "omnipower", "modem", "kamstrup server meter"])
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
            return parts[2].replace("/", " / ")
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


def derive_next_action(status, days_overall):
    s = safe_str(status).lower()
    try:
        d = float(days_overall)
    except Exception:
        d = 0
    if "troubleshoot" in s or "investigation" in s:
        return "Troubleshoot remotely and add evidence/comment on JC"
    if "awaiting client feedback" in s:
        return "Follow up with client and record who was contacted + outcome"
    if "quote" in s and "sent" in s:
        return "Weekly quote follow-up; add call/email note to JC"
    if "quote population" in s or "quote to approve" in s:
        return "Push quote process / confirm hardware or call-out requirement"
    if "schedule" in s:
        return "Confirm installation/commissioning date and update JC"
    if "install complete" in s or "sign off" in s:
        return "Review install info, sign off or move to next department"
    if "final invoice" in s:
        return "Confirm final invoice/monthly check and close where applicable"
    if d > 6:
        return "Escalate / agree action plan with Lindy and update JC"
    if d >= 4:
        return "Call client today and add full JC comment"
    return "Continue within Day 0-2 remote troubleshooting window"


def prepare(df):
    df = df.copy()
    for col in ["Customer", "Contact", "Email", "Mobile", "Job Number", "Job Type", "Description", "Customer Assets", "Job Status", "Modified Date"]:
        if col not in df.columns:
            df[col] = ""
    df["Days Overall"] = pd.to_numeric(df.get("Days Overall", 0), errors="coerce").fillna(0)
    df["Days In Status"] = pd.to_numeric(df.get("Days In Status", 0), errors="coerce").fillna(0)
    df["Commodity"] = df.apply(lambda r: classify_commodity(r["Job Type"], r["Description"], r["Customer Assets"]), axis=1)
    df["Step"] = df["Job Status"].apply(simplify_status)
    df["KPI Stage"] = df["Days Overall"].apply(derive_kpi_stage)
    df["Priority"] = df["Days Overall"].apply(derive_priority)
    df["Next Required Action"] = df.apply(lambda r: derive_next_action(r["Job Status"], r["Days Overall"]), axis=1)
    df["Modified Date"] = pd.to_datetime(df["Modified Date"], errors="coerce")
    return df.sort_values(["Days Overall", "Days In Status"], ascending=[False, False])


def compare_progress(morning, current):
    m_ids = set(morning["Job Number"].astype(str))
    c_ids = set(current["Job Number"].astype(str))
    removed = sorted(list(m_ids - c_ids))
    added = sorted(list(c_ids - m_ids))
    return {
        "morning_total": len(morning),
        "current_total": len(current),
        "net_change": len(current) - len(morning),
        "removed_count": len(removed),
        "added_count": len(added),
        "removed": removed,
        "added": added,
        "note": f"Morning list: {len(morning)} tickets. Current list: {len(current)} tickets. Net improvement: {len(morning)-len(current)} fewer ticket(s). {len(removed)} ticket(s) moved off Donovan's active list today, while {len(added)} new ticket(s) were added."
    }


@app.route("/")
def dashboard():
    morning = prepare(load_raw(MORNING_FILE))
    df = prepare(load_raw(CURRENT_FILE))
    progress = compare_progress(morning, df)

    total = len(df)
    critical = int((df["Priority"] == "Critical").sum())
    warning = int((df["Priority"] == "Warning").sum())
    healthy = int((df["Priority"] == "Healthy").sum())
    avg_age = round(df["Days Overall"].mean(), 1) if total else 0
    stuck = int((df["Days In Status"] >= 7).sum())

    status_counts = df["Step"].value_counts().head(12)
    kpi_counts = df["KPI Stage"].value_counts()
    commodity_counts = df["Commodity"].value_counts()
    priority_counts = df["Priority"].value_counts()

    top_overdue_df = df[["Job Number", "Customer", "Commodity", "Job Type", "Step", "Days Overall", "Days In Status", "Next Required Action", "Contact", "Email", "Mobile"]].head(20).copy()
    tickets_df = df[["Job Number", "Customer", "Commodity", "Job Type", "Step", "Days Overall", "Days In Status", "KPI Stage", "Priority", "Next Required Action", "Contact", "Email", "Mobile", "Description", "Modified Date"]].copy()
    tickets_df["Modified Date"] = tickets_df["Modified Date"].dt.strftime("%Y-%m-%d %H:%M").fillna("")

    chart_data = {
        "status_labels": list(status_counts.index),
        "status_values": [int(v) for v in status_counts.values],
        "kpi_labels": list(kpi_counts.index),
        "kpi_values": [int(v) for v in kpi_counts.values],
        "commodity_labels": list(commodity_counts.index),
        "commodity_values": [int(v) for v in commodity_counts.values],
        "priority_labels": list(priority_counts.index),
        "priority_values": [int(v) for v in priority_counts.values],
        "progress_labels": ["Morning", "Now"],
        "progress_values": [progress["morning_total"], progress["current_total"]],
    }

    return render_template("index.html", total=total, critical=critical, warning=warning, healthy=healthy, avg_age=avg_age, stuck=stuck, updated=datetime.now().strftime("%Y-%m-%d %H:%M"), progress=progress, top_overdue=top_overdue_df.to_dict(orient="records"), tickets=tickets_df.to_dict(orient="records"), chart_data=chart_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
