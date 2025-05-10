from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_very_secure_secret_key_123!'

# Database Setup
def get_db_connection():
    conn = sqlite3.connect('restaurant.db')
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    if os.path.exists('restaurant.db'):
        os.remove('restaurant.db')
    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE Customers (
                    Name TEXT NOT NULL,
                    PhoneNumber TEXT PRIMARY KEY,
                    Address TEXT,
                    VIP BOOLEAN DEFAULT FALSE)''')

    cursor.execute('''CREATE TABLE Menu (
                    FoodID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Food TEXT NOT NULL,
                    Cost INTEGER NOT NULL)''')

    cursor.execute('''CREATE TABLE Orders (
                    OrderID INTEGER PRIMARY KEY AUTOINCREMENT,
                    PhoneNumber TEXT NOT NULL,
                    FoodID INTEGER NOT NULL,
                    Quantity INTEGER NOT NULL,
                    OrderDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    Priority TEXT DEFAULT 'medium' CHECK (Priority IN ('low', 'medium', 'high')),
                    Status TEXT DEFAULT 'pending' CHECK (Status IN ('pending', 'preparing', 'completed')),
                    FOREIGN KEY (PhoneNumber) REFERENCES Customers(PhoneNumber),
                    FOREIGN KEY (FoodID) REFERENCES Menu(FoodID))''')

    menu_items = [
        ('Paneer Butter Masala', 250), ('Chicken Biryani', 320), ('Masala Dosa', 80),
        ('Veg Pulao', 150), ('Chole Bhature', 120), ('Mutton Rogan Josh', 400),
        ('Pav Bhaji', 110), ('Tandoori Chicken', 350), ('Dal Makhani', 200),
        ('Hyderabadi Biryani', 340), ('Gulab Jamun', 50), ('Kadhai Paneer', 230),
        ('Fish Curry', 280), ('Rajma Chawal', 160), ('Butter Naan', 40),
        ('Malai Kofta', 210), ('Shahi Paneer', 240), ('Keema Paratha', 180),
        ('Prawn Masala', 420), ('Chicken Tikka Masala', 300)
    ]
    cursor.executemany("INSERT INTO Menu (Food, Cost) VALUES (?, ?)", menu_items)
    conn.commit()
    conn.close()

# Initialize database
with app.app_context():
    initialize_database()

@app.route('/')
def home():
    return render_template('auth.html')

@app.route('/auth', methods=['POST'])
def auth_user():
    try:
        data = request.get_json()
        if not data or not data.get('phone'):
            return jsonify({'message': 'Phone number is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM Customers WHERE PhoneNumber = ?", (data['phone'],))
        user = cursor.fetchone()

        if user:
            session['phone'] = data['phone']
            session['vip'] = bool(user['VIP'])
            conn.close()
            return jsonify({'message': 'Login successful'}), 200
        else:
            if not data.get('name') or not data.get('address'):
                return jsonify({'message': 'Name and Address are required'}), 400
            
            vip_status = bool(data.get('vip', False))
            cursor.execute("INSERT INTO Customers (Name, PhoneNumber, Address, VIP) VALUES (?, ?, ?, ?)",
                         (data['name'], data['phone'], data['address'], vip_status))
            conn.commit()
            session['phone'] = data['phone']
            session['vip'] = vip_status
            conn.close()
            return jsonify({'message': 'Registration successful'}), 201
    except Exception as e:
        return jsonify({'message': f"Error: {str(e)}"}), 500

@app.route('/menu')
def get_menu():
    conn = get_db_connection()
    menu = conn.execute("SELECT * FROM Menu").fetchall()
    conn.close()
    return jsonify([dict(row) for row in menu])

@app.route('/menu_page')
def menu_page():
    return render_template('menu.html')

@app.route('/order')
def order():
    return render_template('order.html')

@app.route('/orders_page')
def orders_page():
    if 'phone' not in session:
        return redirect(url_for('home'))
    
    conn = get_db_connection()
    orders = conn.execute('''
        SELECT Menu.Food, Orders.Quantity, (Menu.Cost * Orders.Quantity) as TotalCost, 
               Orders.OrderDate, Orders.Priority
        FROM Orders
        JOIN Menu ON Orders.FoodID = Menu.FoodID
        WHERE Orders.PhoneNumber = ?
        ORDER BY Orders.OrderDate DESC
    ''', (session['phone'],)).fetchall()
    conn.close()
    
    return render_template('orders.html', orders=orders)

latest_orders = {}

@app.route('/latest_order')
def latest_order():
    if 'phone' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    phone = session['phone']
    order = latest_orders.get(phone, {'items': [], 'total': 0})
    
    # Format items with food names
    conn = get_db_connection()
    formatted_items = []
    for item in order['items']:
        food = conn.execute("SELECT Food, Cost FROM Menu WHERE FoodID = ?", (item['FoodID'],)).fetchone()
        if food:
            formatted_items.append({
                'Food': food['Food'],
                'Quantity': item['Quantity'],
                'TotalCost': food['Cost'] * item['Quantity'],
                'Priority': item.get('Priority', 'medium')
            })
    conn.close()
    
    return jsonify({
        'orders': formatted_items,
        'total_amount': order['total']
    })

@app.route('/previous_orders')
def previous_orders():
    if 'phone' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    conn = get_db_connection()
    orders = conn.execute('''
        SELECT Menu.Food, Orders.Quantity, (Menu.Cost * Orders.Quantity) as TotalCost, 
               Orders.OrderDate, Orders.Priority
        FROM Orders
        JOIN Menu ON Orders.FoodID = Menu.FoodID
        WHERE Orders.PhoneNumber = ?
        ORDER BY Orders.OrderDate DESC
    ''', (session['phone'],)).fetchall()
    conn.close()
    
    return jsonify([dict(order) for order in orders])

@app.route('/finish_purchase', methods=['POST'])
def finish_purchase():
    if 'phone' not in session:
        return jsonify({"message": "Not logged in"}), 401
    
    phone = session['phone']
    if phone in latest_orders:
        del latest_orders[phone]
    
    return jsonify({"message": "Purchase completed successfully!"}), 200

# Update your place_order route to store the latest order
MAX_KITCHEN_CAPACITY = 5
active_orders = set()  # Track order IDs of active orders

# Modify the place_order route to check capacity
@app.route('/place_order', methods=['POST'])
def place_order():
    if 'phone' not in session:
        return jsonify({"message": "Not logged in"}), 401

    # Check kitchen capacity
    conn = get_db_connection()
    active_count = conn.execute(
        "SELECT COUNT(*) FROM Orders WHERE Status != 'completed'"
    ).fetchone()[0]
    conn.close()
    
    if active_count >= MAX_KITCHEN_CAPACITY:
        return jsonify({
            "message": "The kitchen is busy right now with other orders. Please wait for some time and we will be ready for you!!",
            "kitchen_full": True
        }), 429  # 429 is Too Many Requests status code

    data = request.get_json()
    if not data or 'items' not in data:
        return jsonify({"message": "No items provided"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        priority = 'high' if session.get('vip', False) else 'medium'
        
        order_items = []
        total = 0
        
        for item in data['items']:
            cursor.execute("SELECT FoodID, Cost FROM Menu WHERE Food = ?", (item['food'],))
            food = cursor.fetchone()
            if food:
                cursor.execute(
                    "INSERT INTO Orders (PhoneNumber, FoodID, Quantity, Priority) VALUES (?, ?, ?, ?)",
                    (session['phone'], food['FoodID'], item['quantity'], priority)
                )
                order_items.append({
                    'FoodID': food['FoodID'],
                    'Quantity': item['quantity'],
                    'Priority': priority
                })
                total += food['Cost'] * item['quantity']
        
        conn.commit()
        conn.close()
        
        # Store the latest order for display
        latest_orders[session['phone']] = {
            'items': order_items,
            'total': total
        }
        
        return jsonify({
            "message": "Order placed successfully",
            "redirect": "/orders_page"
        }), 200
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500
    
@app.route('/kitchen')
def kitchen():
    return render_template('kitchen.html')

@app.route('/kitchen/orders')
def kitchen_orders():
    conn = get_db_connection()
    orders = conn.execute('''
        SELECT Orders.OrderID, Customers.Name, Menu.Food, Orders.Quantity, 
               Orders.Priority, Orders.Status, Orders.OrderDate
        FROM Orders
        JOIN Customers ON Orders.PhoneNumber = Customers.PhoneNumber
        JOIN Menu ON Orders.FoodID = Menu.FoodID
        WHERE Orders.Status != 'completed'
        ORDER BY 
            CASE Orders.Priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END,
            Orders.OrderDate
    ''').fetchall()
    conn.close()
    return jsonify([dict(row) for row in orders])

@app.route('/kitchen/update/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({"message": "Status required"}), 400

    try:
        conn = get_db_connection()
        conn.execute("UPDATE Orders SET Status = ? WHERE OrderID = ?", 
                    (data['status'], order_id))
        conn.commit()
        conn.close()
        
        # Update active orders tracking
        if data['status'] == 'completed':
            active_orders.discard(order_id)
        else:
            active_orders.add(order_id)
            
        return jsonify({"message": "Order status updated"}), 200
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)