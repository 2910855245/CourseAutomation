import sqlite3
import sys

action = sys.argv[1] if len(sys.argv) > 1 else "list"
order_id = sys.argv[2] if len(sys.argv) > 2 else ""

conn = sqlite3.connect("data/orders.db")
c = conn.cursor()

if action == "list":
    c.execute("SELECT order_id, username, status, paid, price, website_id, task_type FROM orders")
    rows = c.fetchall()
    print(f"Total orders: {len(rows)}")
    for r in rows:
        print(r)

elif action == "delete" and order_id:
    c.execute("SELECT order_id, username, status, paid, price, website_id FROM orders WHERE order_id = ?", (order_id,))
    row = c.fetchone()
    if row:
        print(f"Found order: {row}")
        c.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
        c.execute("DELETE FROM queue_jobs WHERE order_id = ?", (order_id,))
        conn.commit()
        print("Order and related queue_jobs deleted successfully")
    else:
        print(f"Order {order_id} not found")

elif action == "find_abnormal":
    # Find unpaid but accepted/running orders
    c.execute("SELECT order_id, username, status, paid, price, website_id, task_type FROM orders WHERE paid = 0 AND status IN ('accepted', 'running')")
    rows = c.fetchall()
    print(f"Unpaid + accepted/running orders: {len(rows)}")
    for r in rows:
        print(r)

conn.close()
