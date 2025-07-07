from flask import Flask, request, render_template, redirect, url_for,jsonify,render_template_string
import sqlite3
from datetime import datetime,timedelta
import requests
app = Flask(__name__)

# HTML will be injected from a separate file

DB = "flights.db"

@app.route('/delta/view')
def view_page2():
    # Initialize lists for unique sources and destinations
    src_list = set()
    dst_list = set()
    rows_data = [] # To store all flight data as lists (matching row[0], row[1] etc.)

    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row # Allows access by column name
        cursor = conn.cursor()
        
        # Fetch all flights
        cursor.execute("SELECT flightno, src, dst, departure, arrival, duration FROM flights ORDER BY src, dst")
        all_flights = cursor.fetchall()
        conn.close()

        for flight in all_flights:
            # Add src and dst to their respective sets to ensure uniqueness
            src_list.add(flight['src'])
            dst_list.add(flight['dst'])
            
            # Append the flight data as a list of values
            # Ensure the order matches your HTML table columns: Flight No, From, To, Departure, Arrival, Duration
            
            rows_data.append([
                flight['flightno'],
                flight['src'],
                flight['dst'],
                datetime.strptime(flight['departure'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M'),
                datetime.strptime(flight['arrival'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M'),
                flight['duration']
            ])

    except Exception as e:
        print(f"Error fetching data for view_page2: {e}")
        # In a real app, you might want to return an error page or message
        return "Error loading data", 500

    # Convert sets to sorted lists for consistent dropdown order
    sorted_src_list = sorted(list(src_list))
    sorted_dst_list = sorted(list(dst_list))

    # Prepare the 'data' dictionary for the template
    template_data = {
        'srclist': sorted_src_list,
        'dstlist': sorted_dst_list,
        'rows': rows_data
    }

    # Render the template, passing the prepared data
    return render_template("delta_view2.html", data=template_data)
    

@app.route('/delta/')
def view_page():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
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

    return render_template("delta_view.html", data=data_by_dest)

    
@app.route("/delta/add", methods=["GET", "POST"])
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
    
    return render_template("delta_update_form.html",message=message)
    #return render_template_string(HTML_TEMPLATE, message=message)
    
@app.route("/delta/delete_flight/<int:flight_id>", methods=["POST"])
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
# --- NEW ROUTE FOR PARSING FLIGHTS VIA WEB FORM ---
@app.route("/delta/parse_flights", methods=["GET", "POST"])
def parse_flights_page():
    message = ""
    if request.method == "POST":
        src_iata = request.form.get("src_iata", "").upper()
        dst_iata = request.form.get("dst_iata", "").upper()

        if not src_iata or not dst_iata:
            message = "❌ Error: Both Source and Destination IATA codes are required."
        else:
            try:
                # Get tomorrow's date in YYYY-MM-DD format
                query_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

                API_KEY = '26ae356c0b45057250bdca8fbaacd231'  # Replace with your actual key
                BASE_URL = 'http://api.aviationstack.com/v1/flights'
                
                # List to store results from both directions
                all_parsed_flights = []

                # Iterate for both SRC->DST and DST->SRC
                for i in range(2):
                    current_src = src_iata if i == 0 else dst_iata
                    current_dst = dst_iata if i == 0 else src_iata

                    params = {
                        'access_key': API_KEY,
                        'dep_iata': current_src,
                        'arr_iata': current_dst,
                        'airline_iata':'DL',
                        'limit': 20, # Limit results to 20 per query
                        'flight_date': query_date # Add flight date to params
                    }

                    response = requests.get(BASE_URL, params=params)
                    data = response.json()
                    print(data)
                    if 'data' not in data or not data['data']:
                        # print(f"API error or no data for {current_src}->{current_dst}: {data}")
                        message += f"⚠️ Warning: No flights found for {current_src} to {current_dst}. "
                        continue # Continue to the next direction

                    conn = sqlite3.connect(DB)
                    cursor = conn.cursor()

                    for flight in data['data']:
                        airline = flight.get('airline', {}).get('name')
                        flight_number = flight.get('flight', {}).get('iata')
                        
                        # Only process Delta flights
                        if 'Delta' not in str(airline): 
                            continue

                        departure_time = flight.get('departure', {}).get('scheduled')
                        arrival_time = flight.get('arrival', {}).get('scheduled')
                        
                        # Use iata codes from the API response for accuracy
                        api_src = flight.get('departure', {}).get('iata')
                        api_dst = flight.get('arrival', {}).get('iata')

                        if departure_time and arrival_time and api_src and api_dst:
                            try:
                                dep_dt = datetime.fromisoformat(departure_time.replace('Z', '+00:00'))
                                arr_dt = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))

                                duration_minutes = int((arr_dt - dep_dt).total_seconds() // 60)

                                cursor.execute('''
                                    INSERT INTO flights (flightno, src, dst, departure, arrival, duration)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                ''', (
                                    flight_number,
                                    api_src, # Use API's src
                                    api_dst, # Use API's dst
                                    dep_dt.strftime('%Y-%m-%d %H:%M:%S'),
                                    arr_dt.strftime('%Y-%m-%d %H:%M:%S'),
                                    duration_minutes
                                ))
                                all_parsed_flights.append(f"{airline} {flight_number} ({api_src} to {api_dst}) added.")

                            except ValueError as ve:
                                print(f"Date parsing error for flight {flight_number}: {ve}")
                                message += f"❌ Error parsing date for {flight_number}. "
                            except Exception as insert_e:
                                print(f"Database insert error for flight {flight_number}: {insert_e}")
                                message += f"❌ Error saving {flight_number} to DB. "
                        else:
                            print(f"{airline} {flight_number} — Missing time/airport info\n")
                            message += f"⚠️ Warning: Missing info for {flight_number}. "
                    
                    conn.commit()
                    conn.close() # Close connection after each direction's processing

                if not message: # If no warnings or errors, assume success
                    message = f"✅ Flight data parsed and saved successfully for {src_iata} and {dst_iata}!"
                elif "Error" in message:
                    message = "❌ Some errors occurred during parsing: " + message
                else:
                    message = "⚠️ Warnings during parsing: " + message

            except requests.exceptions.RequestException as req_e:
                message = f"❌ Network Error: Could not connect to API. {req_e}"
            except Exception as e:
                message = f"❌ An unexpected error occurred: {e}"
    return render_template("delta_parseflights.html", message=message)
if __name__ == "__main__":
    app.run(debug=True)
