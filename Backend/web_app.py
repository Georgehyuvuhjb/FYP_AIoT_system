from flask import Flask, request, redirect, url_for, render_template_string
import db_manager

app = Flask(__name__)

PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Smart Ward Data Input</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; background: #f5f7fb; color: #1f2937; }
    h1 { margin-bottom: 8px; }
    .row { display: flex; gap: 20px; flex-wrap: wrap; }
    .card { background: white; border: 1px solid #d1d5db; border-radius: 8px; padding: 16px; width: 420px; }
    label { display: block; margin-top: 8px; font-size: 14px; }
    input, select { width: 100%; padding: 6px; margin-top: 4px; }
    button { margin-top: 14px; padding: 8px 14px; background: #0a66c2; color: white; border: none; border-radius: 6px; cursor: pointer; }
    .msg { margin: 10px 0; padding: 10px; border-radius: 6px; }
    .ok { background: #dcfce7; border: 1px solid #86efac; }
    .err { background: #fee2e2; border: 1px solid #fca5a5; }
  </style>
</head>
<body>
  <h1>Smart Ward Manual Data Input</h1>
  <p>Input-only interface for patient and card data.</p>

  {% if message %}
    <div class="msg {{ 'ok' if success else 'err' }}">{{ message }}</div>
  {% endif %}

  <div class="row">
    <div class="card">
      <h2>Add Patient</h2>
      <form method="post" action="/add_patient">
        <label>patient_id<input name="patient_id" required /></label>
        <label>age<input name="age" type="number" min="1" required /></label>
        <label>gender<input name="gender" required /></label>
        <label>mobility_level<input name="mobility_level" type="number" min="1" required /></label>
        <label>has_gastro_issue (0/1)<input name="has_gastro_issue" type="number" min="0" max="1" required /></label>
        <label>has_uro_issue (0/1)<input name="has_uro_issue" type="number" min="0" max="1" required /></label>
        <label>self_reported_max_seconds<input name="self_reported_max_seconds" type="number" min="1" required /></label>
        <label>anomaly_count<input name="anomaly_count" type="number" min="1" value="5" required /></label>
        <button type="submit">Add Patient (+ anomalies)</button>
      </form>
    </div>

    <div class="card">
      <h2>Register Card</h2>
      <p style="font-size:13px;color:#6b7280">Register a new card without assigning it to any patient.</p>
      <form method="post" action="/register_card">
        <label>card_uid<input name="card_uid" required /></label>
        <button type="submit">Register Card</button>
      </form>
    </div>

    <div class="card">
      <h2>Assign / Activate Card</h2>
      <p style="font-size:13px;color:#6b7280">Card must be registered and inactive first.</p>
      <form method="post" action="/assign_card">
        <label>card_uid<input name="card_uid" required /></label>
        <label>patient_id<input name="patient_id" required /></label>
        <button type="submit">Assign Card</button>
      </form>
    </div>

    <div class="card">
      <h2>Deactivate Card</h2>
      <p style="font-size:13px;color:#6b7280">Unlinks the card from its patient. Must reassign before use.</p>
      <form method="post" action="/deactivate_card">
        <label>card_uid<input name="card_uid" required /></label>
        <button type="submit" style="background:#dc2626">Deactivate Card</button>
      </form>
    </div>

    <div class="card">
      <h2>Generate Anomalies</h2>
      <form method="post" action="/generate_anomalies">
        <label>patient_id<input name="patient_id" required /></label>
        <label>count<input name="count" type="number" min="1" value="5" required /></label>
        <button type="submit">Generate Anomalies</button>
      </form>
    </div>
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    message = request.args.get("message", "")
    success = request.args.get("success", "1") == "1"
    return render_template_string(PAGE, message=message, success=success)


@app.route("/add_patient", methods=["POST"])
def add_patient_route():
    try:
        result = db_manager.add_patient(
            patient_id=request.form.get("patient_id"),
            age=request.form.get("age"),
            gender=request.form.get("gender"),
            mobility_level=request.form.get("mobility_level"),
            has_gastro_issue=request.form.get("has_gastro_issue"),
            has_uro_issue=request.form.get("has_uro_issue"),
            self_reported_max_seconds=request.form.get("self_reported_max_seconds"),
            auto_generate_anomalies=True,
            anomaly_count=request.form.get("anomaly_count", 5),
        )
        msg = f"Patient {result['patient_id']} created. Generated {result['anomalies_generated']} anomalies."
        return redirect(url_for("index", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("index", message=str(exc), success=0))


@app.route("/register_card", methods=["POST"])
def register_card_route():
    try:
        result = db_manager.register_card(card_uid=request.form.get("card_uid"))
        msg = f"Card {result['card_uid']} registered (inactive, unassigned)."
        return redirect(url_for("index", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("index", message=str(exc), success=0))


@app.route("/assign_card", methods=["POST"])
def assign_card_route():
    try:
        result = db_manager.assign_card(
            card_uid=request.form.get("card_uid"),
            patient_id=request.form.get("patient_id"),
        )
        msg = f"Card {result['card_uid']} assigned to patient {result['patient_id']} and activated."
        return redirect(url_for("index", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("index", message=str(exc), success=0))


@app.route("/deactivate_card", methods=["POST"])
def deactivate_card_route():
    try:
        result = db_manager.deactivate_card(card_uid=request.form.get("card_uid"))
        msg = f"Card {result['card_uid']} deactivated and unlinked."
        return redirect(url_for("index", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("index", message=str(exc), success=0))


@app.route("/generate_anomalies", methods=["POST"])
def generate_anomalies_route():
    try:
        result = db_manager.generate_anomalies_for_patient(
            patient_id=request.form.get("patient_id"),
            count=request.form.get("count", 5),
        )
        msg = f"Generated {result['anomalies_generated']} anomalies for {result['patient_id']}."
        return redirect(url_for("index", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("index", message=str(exc), success=0))


if __name__ == "__main__":
    db_manager.init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
