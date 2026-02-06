import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="cashflow_user",
        password="Cashflow123!",
        database="cashflow_db"
    )
