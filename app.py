
from flask import Flask, render_template
import pandas as pd
from datetime import datetime

app = Flask(__name__, template_folder="templates")

EXCEL_FILE = "Donovan_JC_Live_Dashboard.xlsx"

def load_data():
    df = pd.read_excel(EXCEL_FILE, sheet_name="Donovan Live Tracker")

    if "Days Overall" in df.columns:
        df["Risk"] = df["Days Overall"].apply(
            lambda x: "CRITICAL" if x >= 6 else ("WARNING" if x >= 4 else "OK")
        )

    return df

@app.route("/")
def dashboard():
    df = load_data()

    total = len(df)
    critical = len(df[df["Risk"] == "CRITICAL"])
    warning = len(df[df["Risk"] == "WARNING"])
    ok = len(df[df["Risk"] == "OK"])

    tickets = df.to_dict(orient="records")

    return render_template(
        "index.html",
        total=total,
        critical=critical,
        warning=warning,
        ok=ok,
        tickets=tickets,
        updated=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
