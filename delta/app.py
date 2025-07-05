from flask import Flask, request, render_template, redirect, url_for,jsonify,render_template_string
import sqlite3
from datetime import datetime

app = Flask(__name__)

# HTML will be injected from a separate file

DB = "flights.db"
def get_connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn
@app.route('/')
def view_page():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id,flightno, src, dst, departure, arrival, duration
        FROM flights
    """)
    rows = cur.fetchall()
    conn.close()

    # Organize data by destination
    data_by_dest = {}
    for row in rows:
        dst = row['dst']
        src = row ['src']
        srcdst = src+'=>'+dst
        departure = datetime.strptime(row['departure'], '%Y-%m-%d %H:%M:%S')
        arrival = datetime.strptime(row['arrival'], '%Y-%m-%d %H:%M:%S')
        #print('date format',row['departure'],departure,arrival)
        if srcdst not in data_by_dest:
            data_by_dest[srcdst] = []
        data_by_dest[srcdst].append({
            'flightno': row['flightno'],
            'departure': departure.strftime('%H:%M'),
            'arrival': arrival.strftime('%H:%M'),
            'duration':row['duration'],
            'id':row['id']
        })

    return render_template("view.html", data=data_by_dest)

    
@app.route("/add", methods=["GET", "POST"])
def index():
    message = ""
    if request.method == "POST":
        try:
            flightno = request.form["flightno"]
            src = request.form["src"].upper()
            dst = request.form["dst"].upper()
            departure = request.form["departure"]
            arrival = request.form["arrival"]
            duration = int(request.form["duration"])

            # Validate time format
            datetime.strptime(departure, "%Y-%m-%d %H:%M:%S")
            datetime.strptime(arrival, "%Y-%m-%d %H:%M:%S")

            conn = sqlite3.connect(DB)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO flights (flightno, src, dst, departure, arrival, duration)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (flightno, src, dst, departure, arrival, duration))
            conn.commit()
            conn.close()
            message = "✅ Flight added successfully!"
        except Exception as e:
            message = f"❌ Error: {e}"
    print('xxxxxxxxxxxxxxxxx')
    return render_template("update_form.html",message=message)
    #return render_template_string(HTML_TEMPLATE, message=message)
    
@app.route("/delete_flight/<int:flight_id>", methods=["POST"])
def delete_flight(flight_id):
    try:
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM flights WHERE id = ?", (flight_id,))
        conn.commit()
        conn.close()
        # Return a JSON response indicating success
        return jsonify(success=True, message=f"Flight {flight_id} deleted successfully.")
    except Exception as e:
        print(f"Error deleting flight {flight_id}: {e}")
        # Return a JSON response indicating failure with an error message
        return jsonify(success=False, message=str(e)), 500 # Return 500 status for server error

if __name__ == "__main__":
    app.run(debug=True)
