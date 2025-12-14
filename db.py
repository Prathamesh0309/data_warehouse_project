import os
import mysql.connector
from mysql.connector import errorcode, Error
import hashlib
import datetime
import time
import socket
from cryptography.fernet import Fernet
from dotenv import load_dotenv
try:
    # loading .env file for local development
    load_dotenv("project.env")
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")


def is_port_open(host, port, timeout=2):
    """Check if MySQL port is open/listening"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    finally:
        sock.close()


def get_connection(max_retries=3, retry_delay=2):
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.environ.get("DB_USER", "root")
    password = os.environ.get("DB_PASSWORD")
    database = os.environ.get("DB_NAME")

    # First check if MySQL is running
    if not is_port_open(host, port):
        raise ConnectionError(f"MySQL server not running or not accessible at {host}:{port}")

    # Simpler connection (avoid pool on small single-process app to prevent pool exhaustion)
    for attempt in range(max_retries):
        try:
            conn = mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connection_timeout=10)
            try:
                # mysql-connector: set autocommit via attribute
                conn.autocommit = True
            except Exception:
                pass
            return conn
        except mysql.connector.Error as e:
            if attempt == max_retries - 1:
                raise ConnectionError(f"Failed to connect to MySQL after {max_retries} attempts. Error: {str(e)}")
            print(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay} seconds... ({e})")
            time.sleep(retry_delay)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db():
    """Create database and tables if they don't exist."""
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.environ.get("DB_USER", "root")
    password = os.environ.get("DB_PASSWORD")
    database = os.environ.get("DB_NAME")

    # Ensure password is provided via environment for security
    if not password:
        raise EnvironmentError(
            "DB_PASSWORD environment variable is not set.\n"
            "Set it in PowerShell before running, e.g.: $env:DB_PASSWORD = 'your_mysql_password'"
        )

    # First verify MySQL is running
    if not is_port_open(host, port):
        raise ConnectionError(
            f"\nERROR: MySQL server not running or not accessible at {host}:{port}\n"
            "Please check:\n"
            "1. MySQL service is running (Get-Service MySQL* in PowerShell)\n"
            "2. MySQL is listening on the correct port\n"
            "3. No firewall is blocking the connection"
        )

    # Connect to MySQL server, create database if necessary
    conn = None
    try:
        conn = mysql.connector.connect(host=host, port=port, user=user, password=password)
        cursor = conn.cursor()
        cursor.execute(cursor.execute("CREATE DATABASE IF NOT EXISTS " + f"`{database}`" + " DEFAULT CHARACTER SET utf8mb4"))
    except mysql.connector.Error as err:
        print("Failed creating database:", err)
        raise
    finally:
        if conn:
            conn.close()

    # Create tables
    conn = get_connection()
    cursor = conn.cursor()

    TABLES = {}
    TABLES['users'] = (
        "CREATE TABLE IF NOT EXISTS users ("
        "  id INT AUTO_INCREMENT PRIMARY KEY,"
        "  username VARCHAR(100) NOT NULL UNIQUE,"
        "  email VARCHAR(255) DEFAULT NULL,"
        "  password_hash VARCHAR(255) NOT NULL,"
        "  is_admin TINYINT DEFAULT 0,"
        "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ") ENGINE=InnoDB"
    )

    TABLES['events'] = (
        "CREATE TABLE IF NOT EXISTS events ("
        "  id INT AUTO_INCREMENT PRIMARY KEY,"
        "  title VARCHAR(255) NOT NULL,"
        "  description TEXT,"
        "  event_date DATETIME,"
        "  event_time TIME,"
        "  location VARCHAR(255),"
        "  capacity INT DEFAULT 0,"
        "  price DECIMAL(8,2) DEFAULT 0.00,"
        "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ") ENGINE=InnoDB"
    )

    TABLES['registrations'] = (
        "CREATE TABLE IF NOT EXISTS registrations ("
        "  id INT AUTO_INCREMENT PRIMARY KEY,"
        "  user_id INT NOT NULL,"
        "  event_id INT NOT NULL,"
        "  status VARCHAR(50) DEFAULT 'registered'," 
        "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        "  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE," 
        "  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE"
        ") ENGINE=InnoDB"
    )

    TABLES['payments'] = (
        "CREATE TABLE IF NOT EXISTS payments ("
        "  id INT AUTO_INCREMENT PRIMARY KEY,"
        "  registration_id INT NOT NULL,"
        "  amount DECIMAL(8,2) NOT NULL,"
        "  status VARCHAR(50) DEFAULT 'pending'," 
        "  txn_id VARCHAR(255),"
        "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP," 
        "  FOREIGN KEY (registration_id) REFERENCES registrations(id) ON DELETE CASCADE"
        ") ENGINE=InnoDB"
    )

    # Create tables with fresh connections per table to avoid stale/pooled connection issues
    for name, ddl in TABLES.items():
        attempts = 3
        for attempt in range(attempts):
            try:
                conn_tbl = get_connection()
                cur = conn_tbl.cursor()
                # disable notes on this session
                cur.execute("SET sql_notes = 0")
                cur.execute(ddl)
            except mysql.connector.Error as err:
                # specific handling if table exists
                if getattr(err, 'errno', None) == errorcode.ER_TABLE_EXISTS_ERROR:
                    print(f"Table {name} already exists")
                    try:
                        cur.close()
                        conn_tbl.close()
                    except Exception:
                        pass
                    break
                # transient/connection issues -> retry
                print(f"Attempt {attempt+1} failed creating table {name}: {err}")
                try:
                    cur.close()
                    conn_tbl.close()
                except Exception:
                    pass
                if attempt == attempts - 1:
                    raise
                time.sleep(1)
                continue
            else:
                print(f"Created table {name}")
                try:
                    cur.execute("SET sql_notes = 1")
                except Exception:
                    pass
                cur.close()
                conn_tbl.close()
                break


# User functions

def create_user(first_name: str, last_name: str, phone: str, email: str, password: str, user_role: str = "user") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    pw_hash = _hash_password(password)
    try:
        cursor.execute(
            "INSERT INTO users (first_name, last_name, phone, email, password_hash, user_role) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (first_name, last_name, phone, email, pw_hash, user_role)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_user_by_email(email: str):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, first_name, last_name, phone, email, password_hash, user_role "
            "FROM users WHERE email=%s",
            (email,)
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def authenticate_user(email: str, password: str):
    user = get_user_by_email(email)
    if not user:
        return None
    if user['password_hash'] == _hash_password(password):
        return {
            'user_id': user['user_id'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'email': user['email'],
            'phone': user['phone'],
            'user_role': user['user_role']
        }
    return None


# Event functions

def add_event(event_name, event_description, event_date, event_time, location, event_type, organizer_id, price):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO events (event_name, event_description, event_date, event_time, location, event_type, organizer_id, price)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (event_name, event_description, event_date, event_time, location, event_type, organizer_id, price)
    )
    conn.commit()
    cursor.close()
    conn.close()


def list_events():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT event_id, event_name, event_description, event_date, event_time,location, price
            FROM events
            WHERE is_active = 1
            ORDER BY event_date ASC
        """)
        rows = cursor.fetchall()
        # Map to keys expected by frontend
        events = []
        for ev in rows:
            events.append({
                'id': ev['event_id'],                  # map to 'id'
                'title': ev['event_name'],             # map to 'title'
                'description': ev['event_description'],# map to 'description'
                'event_date': ev['event_date'],
                'event_time': ev['event_time'],
                'location': ev['location'],
                'price': float(ev['price'])
            })
        return events
    finally:
        cursor.close()
        conn.close()


def get_event(event_id: int):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT event_id, event_name, event_description, event_date,event_time, price
            FROM events
            WHERE event_id=%s
        """, (event_id,))
        ev = cursor.fetchone()
        if not ev:
            return None
        # Map to keys used in frontend
        return {
            'id': ev['event_id'],
            'title': ev['event_name'],
            'description': ev['event_description'],
            'event_date': ev['event_date'],
            'event_time': ev['event_time'],
            'price': float(ev['price'])
        }
    finally:
        cursor.close()
        conn.close()


def delete_event(event_id: int):
    #Soft delete by setting is_active to 0
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE events SET is_active = 0 WHERE event_id = %s", (event_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# Registration & payment

def register_user_for_event(user_id: int, event_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO registrations (user_id, event_id, payment_status) VALUES (%s, %s, %s)",
            (user_id, event_id, 'Pending')
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()



def event_stats(event_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Count total registrations for the event
        cursor.execute("SELECT COUNT(*) FROM registrations WHERE event_id = %s", (event_id,))
        total_reg = cursor.fetchone()[0]

        # Sum payments for successful transactions
        cursor.execute("""
            SELECT COALESCE(SUM(p.amount), 0)
            FROM payments p
            JOIN registrations r ON p.registration_id = r.registration_id
            WHERE r.event_id = %s AND p.payment_status = 'Success'
        """, (event_id,))
        total_amt = cursor.fetchone()[0] or 0.0

        return {'registrations': total_reg, 'revenue': float(total_amt)}
    finally:
        cursor.close()
        conn.close()



def get_user_registrations(user_id: int):
    """Return a list of registrations for a user with event info and latest payment status."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.registration_id, e.event_id, e.event_name AS title, e.event_description AS description,
                   e.event_date, e.price,
                   r.payment_status AS registration_status,
                   (SELECT p.payment_status 
                    FROM payments p 
                    WHERE p.registration_id = r.registration_id 
                    ORDER BY p.payment_date DESC 
                    LIMIT 1) as payment_status
            FROM registrations r
            JOIN events e ON r.event_id = e.event_id
            WHERE r.user_id = %s
              AND r.registration_id = (
                    SELECT MAX(r2.registration_id)
                    FROM registrations r2
                    WHERE r2.user_id = r.user_id
                      AND r2.event_id = r.event_id
              )
            ORDER BY e.event_date ASC
            """,
            (user_id,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()




try:
    fernet_key = os.getenv("FERNET_KEY")
    fernet = Fernet(fernet_key)
except Exception as e:
    print(f"Error initializing Fernet encryption: {e}")
    raise 

def encrypt_data(data):
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(data):
    return fernet.decrypt(data.encode()).decode()

def get_saved_cards(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM saved_cards WHERE user_id = %s", (user_id,))
    rows = cursor.fetchall()
    for r in rows:
        r['card_number_decrypted'] = decrypt_data(r['card_number_encrypted'])
    cursor.close()
    conn.close()
    return rows

def add_saved_card(user_id, holder, number, cvv, expiry_date):
    conn = get_connection()
    cursor = conn.cursor()
    enc_number = encrypt_data(number)
    enc_cvv = encrypt_data(cvv)
    cursor.execute("""
        INSERT INTO saved_cards (user_id, card_holder_name, card_number_encrypted, cvv_encrypted, expiry_date)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, holder, enc_number, enc_cvv, expiry_date))
    conn.commit()
    cursor.close()
    conn.close()

    
def record_payment(user_id: int, registration_id: int, card_id: int = None, amount: float = 0.0, payment_type: str = "Free", payment_status: str = 'Success'):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO payments (user_id, registration_id, card_id, amount, payment_type, payment_status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, registration_id, card_id, amount, payment_type, payment_status))

        cursor.execute("""
            UPDATE registrations
            SET payment_status = %s
            WHERE registration_id = %s
        """, ('Success', registration_id))

        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()