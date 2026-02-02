import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.utils import secure_filename
import random
from datetime import datetime, timedelta

# ==========================================
# KONFIGURASI APP
# ==========================================
app = Flask(__name__)
app.secret_key = 'super_secret_key_meow_sheets_final_v12'
app.permanent_session_lifetime = timedelta(days=1)

# --- PATH MANUAL ---
basedir = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ==========================================
# GOOGLE CREDENTIALS VIA ENVIRONMENT VARIABLE
# ==========================================
google_creds_raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")

if not google_creds_raw:
    raise Exception("GOOGLE_CREDENTIALS_JSON env not found")

GOOGLE_CREDENTIALS = json.loads(google_creds_raw)




# Nama Google Sheet
SHEET_NAME = "CashflowDB"

# ==========================================
# KONEKSI GOOGLE SHEETS
# ==========================================
def get_db_connection():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        return sheet
    except Exception as e:
        print(f"Error Connect Sheet: {e}")
        return None

def get_settings():
    conn = get_db_connection()
    # Ganti 'Settings' dengan nama tab yang kamu buat
    try:
        sheet_settings = conn.spreadsheet.worksheet('Settings')
        records = sheet_settings.get_all_records()
        # Mengubah list records menjadi dictionary agar mudah diakses
        return {r['key']: r['value'] for r in records}
    except:
        return {}

def update_setting(key_name, value):
    conn = get_db_connection()
    try:
        sheet_settings = conn.spreadsheet.worksheet('Settings')
        # Ambil semua data di kolom A (Key)
        keys = sheet_settings.col_values(1)
        if key_name in keys:
            row_idx = keys.index(key_name) + 1
            sheet_settings.update_cell(row_idx, 2, value)
            return True
        else:
            # Jika key belum ada, tambah baris baru
            sheet_settings.append_row([key_name, value])
            return True
    except Exception as e:
        print(f"Update Setting Error: {e}")
        return False

def fetch_all_data():
    sheet = get_db_connection()
    if not sheet: return []
    try:
        records = sheet.get_all_records()
        fixed = []

        for i, r in enumerate(records, start=2):  # start=2 karena row 1 header
            raw_date = r.get('date')
            d = None

            # ... (logika pengecekan raw_date yang sudah ada) ...
            if isinstance(raw_date, datetime):
                d = raw_date
            elif isinstance(raw_date, str):
                raw = raw_date.strip()
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
                    try:
                        d = datetime.strptime(raw, fmt)
                        break
                    except: continue
            elif isinstance(raw_date, (int, float)):
                d = datetime(1899, 12, 30) + timedelta(days=float(raw_date))

            if not d:
                continue

            # 🔥 PERBAIKAN PENGAMAN ANGKA:
            r['category'] = str(r.get('category', '📝 Lainnya'))
            r['desc'] = str(r.get('desc', '-'))

            # Ambil data amount asli
            raw_amt = r.get('amount', 0)
            if isinstance(raw_amt, str):
                # Hanya hapus titik jika dia teks (string)
                clean_amt = raw_amt.replace('.', '').replace(',', '.')
                r['amount'] = float(clean_amt if clean_amt else 0)
            else:
                # Jika sudah angka, langsung jadikan float tanpa ganggu digitnya
                r['amount'] = float(raw_amt)

            r['date'] = d.strftime("%Y-%m-%d")
            r['_dt'] = d
            r['_row'] = i
            fixed.append(r)

        fixed.sort(key=lambda x: x.get('_dt', datetime.min), reverse=True)
        return fixed

    except Exception as e:
        print(f"Error Fetching: {e}")
        return []


#===========
def generate_available_months(data):
    months = set()
    for t in data:
        dt = t.get('_dt')
        if dt:
            months.add(dt.strftime("%Y-%m"))  # YYYY-MM

    return sorted(list(months), reverse=True)



# ==========================================
# USER CONFIG
# ==========================================
DEFAULT_CATS = ["🛍️ Belanja", "🍔 Makan", "💅 Skincare", "🚕 Transport", "🏠 Tagihan", "🐾 Kucing", "✨ Income"]

USERS = {
    "silviapasya": { "username": "silviapasya", "pin": "080599", "name": "Sisil", "gender": "female", "avatar_file": None, "categories": DEFAULT_CATS.copy() },
    "rdfarizi": { "username": "rdfarizi", "pin": "028465", "name": "Fariz", "gender": "male", "avatar_file": None, "categories": DEFAULT_CATS.copy() }
}

# ==========================================
# LOGIC PERHITUNGAN
# ==========================================
def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        return None

def filter_transactions(data_list, filter_type, s_date=None, e_date=None, month=None):
    res = []
    # --- TAMBAHKAN +8 JAM UNTUK WITA ---
    now_wita = datetime.utcnow() + timedelta(hours=8)
    today = now_wita.date()
    yesterday = today - timedelta(days=1)
    # -----------------------------------

    for t in data_list:
        dt = t.get('_dt')
        if not dt:
            continue

        d = dt.date()

        if filter_type == 'today':
            if d == today:
                res.append(t)

        elif filter_type == 'yesterday':
            if d == yesterday:
                res.append(t)

        elif filter_type == 'month' and month:
            # month format: YYYY-MM
            if dt.strftime("%Y-%m") == month:
                res.append(t)

        elif filter_type == 'range' and s_date and e_date:
            try:
                sd = datetime.strptime(s_date, "%Y-%m-%d").date()
                ed = datetime.strptime(e_date, "%Y-%m-%d").date()
                if sd <= d <= ed:
                    res.append(t)
            except:
                pass

        elif filter_type == 'single' and s_date:
            try:
                sd = datetime.strptime(s_date, "%Y-%m-%d").date()
                if d == sd:
                    res.append(t)
            except:
                pass

        elif filter_type == 'all':
            res.append(t)

    return res




def calculate_stats(data_list):
    total_in = sum(float(t['amount']) for t in data_list if t['type'] == 'in')
    total_out = sum(float(t['amount']) for t in data_list if t['type'] == 'out')
    balance = total_in - total_out

    out_pribadi = sum(float(t['amount']) for t in data_list if t['type'] == 'out' and t.get('usage') == 'pribadi')
    out_bisnis = sum(float(t['amount']) for t in data_list if t['type'] == 'out' and t.get('usage') == 'bisnis')

    return balance, total_in, total_out, out_pribadi, out_bisnis

# ==========================================
# HTML TEMPLATE (VERSI 11 - UI SEMPURNA)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Cashflow App</title>
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        :root { --bg-deep: #1F1D2B; --bg-card: #252836; --bg-modal: #2D303E; --primary-grad: linear-gradient(135deg, #FF9A9E 0%, #FECFEF 100%); --text-main: #ffffff; --text-soft: #B7B9D2; --accent-pink: #FF758C; --accent-green: #00E396; --accent-blue: #5D5FEF; }
        * { box-sizing: border-box; margin: 0; padding: 0; outline: none; -webkit-tap-highlight-color: transparent; }
        body { font-family: 'Quicksand'; background: var(--bg-deep); color: var(--text-main); padding-bottom: 100px; min-height: 100vh; overflow-x: hidden; }
        .bg-anim { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; pointer-events: none; }
        .paw { position: absolute; color: rgba(255,154,158,0.05); font-size: 2rem; animation: float 15s linear infinite; }
        @keyframes float { 0% { transform: translateY(0); opacity:0; } 100% { transform: translateY(-100vh); opacity:0; } }
        .container { max-width: 500px; margin: 0 auto; padding: 25px; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
        .greeting h1 { font-size: 1.6rem; font-weight: 700; background: var(--primary-grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .user-avatar { width: 45px; height: 45px; border-radius: 50%; background-size: cover; background-position: center; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; border: 2px solid #FF9A9E; background-color: var(--bg-card); }
        .wallet-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 25px; padding: 25px; margin-bottom: 25px; box-shadow: 0 10px 30px rgba(118,75,162,0.4); }
        .balance-val { font-size: 2.2rem; font-weight: 700; margin: 5px 0 15px 0; }
        .wallet-stats { display: flex; gap: 10px; }
        .stat-pill { background: rgba(0,0,0,0.2); padding: 8px 14px; border-radius: 15px; font-size: 0.8rem; flex: 1; font-weight: 600; display:flex; align-items:center; gap:5px; }
        select, input { -webkit-appearance: none; appearance: none; }
        .input-box { width: 100%; background: #1F1D2B; border: 1px solid rgba(255,255,255,0.1); padding: 15px; border-radius: 15px; color: white; font-family: 'Quicksand'; font-size: 1rem; }
        .submit-btn { width: 100%; padding: 16px; border: none; border-radius: 18px; background: var(--primary-grad); color: white; font-weight: 700; cursor: pointer; margin-top: 15px; box-shadow: 0 5px 15px rgba(255,154,158,0.4); }
        .submit-btn.logout { background: transparent; border: 1px solid #FF4444; color: #FF4444; box-shadow: none; }
        .filter-bar { display: flex; gap: 10px; margin-bottom: 20px; overflow-x: auto; padding-bottom: 5px; }
        .filter-btn { padding: 8px 16px; border-radius: 20px; background: var(--bg-card); color: var(--text-soft); border: 1px solid rgba(255,255,255,0.1); font-size: 0.8rem; white-space: nowrap; cursor: pointer; text-decoration: none; }
        .filter-btn.active { background: rgba(255, 117, 140, 0.2); color: var(--accent-pink); border-color: var(--accent-pink); font-weight: bold; }
        .trans-item { background: var(--bg-card); padding: 15px; border-radius: 20px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
        .usage-badge { font-size: 0.6rem; padding: 2px 6px; border-radius: 6px; margin-right: 5px; text-transform: uppercase; font-weight: 700; }
        .badge-pribadi { background: rgba(255, 117, 140, 0.2); color: var(--accent-pink); }
        .badge-bisnis { background: rgba(93, 95, 239, 0.2); color: var(--accent-blue); }
        .btn-mini { background: none; border: none; color: var(--text-soft); padding: 5px; cursor: pointer; font-size: 0.9rem; }
        .cat-tag-container { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }
        .cat-tag { background: rgba(255,255,255,0.1); padding: 8px 12px; border-radius: 12px; font-size: 0.85rem; display: flex; align-items: center; gap: 8px; }
        .cat-delete { color: #FF4444; cursor: pointer; font-weight: bold; }
        .flash-msg { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: rgba(40, 40, 50, 0.9); backdrop-filter: blur(10px); padding: 15px 25px; border-radius: 50px; border: 1px solid var(--accent-pink); color: white; z-index: 1000; font-size: 0.9rem; width: 90%; max-width: 400px; animation: slideDown 0.5s ease-out, fadeOut 0.5s ease-in 2.5s forwards; display: flex; align-items: center; gap: 10px; }
        @keyframes slideDown { from{top:-50px;} to{top:20px;} }
        @keyframes fadeOut { from{opacity:1;} to{opacity:0; visibility:hidden;} }
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
        .stat-box { background: var(--bg-card); padding: 20px; border-radius: 20px; text-align: center; }
        .stat-label { font-size: 0.75rem; color: var(--text-soft); text-transform: uppercase; margin-bottom: 5px; }
        .stat-num { font-size: 1.1rem; font-weight: 700; }
        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; height: 70px; background: var(--bg-card); display: flex; justify-content: space-around; align-items: center; border-top: 1px solid rgba(255,255,255,0.05); z-index: 90; }
        .nav-item { display: flex; flex-direction: column; align-items: center; gap: 5px; color: var(--text-soft); text-decoration: none; font-size: 0.75rem; width: 60px; }
        .nav-item.active { color: var(--accent-pink); }
        .fab-container { position: relative; top: -25px; width: 60px; height: 60px; border-radius: 50%; background: var(--bg-deep); display: flex; align-items: center; justify-content: center; padding: 5px; }
        .fab-btn { width: 100%; height: 100%; border-radius: 50%; background: var(--primary-grad); border: none; color: white; font-size: 1.5rem; cursor: pointer; box-shadow: 0 5px 15px rgba(255, 154, 158, 0.5); }
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); backdrop-filter: blur(5px); z-index: 200; display: none; align-items: flex-end; justify-content: center; }
        .modal-overlay.active { display: flex; animation: slideUp 0.3s ease-out; }
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        .modal-card { background: var(--bg-modal); width: 100%; max-width: 500px; border-radius: 30px 30px 0 0; padding: 30px 25px 40px 25px; }
        .login-wrapper { display: flex; flex-direction: column; justify-content: center; align-items: center; height: 90vh; text-align: center; }
        .login-card { background: var(--bg-card); padding: 40px 30px; border-radius: 30px; width: 100%; border: 1px solid rgba(255,255,255,0.05); }
    </style>
</head>
<body>
    <div class="bg-anim"><i class="fa-solid fa-paw paw" style="left:10%"></i><i class="fa-solid fa-paw paw" style="left:80%; animation-delay:5s"></i></div>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash-msg"><i class="fa-solid fa-bell" style="color:#FF9A9E"></i> {{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <div class="container">
        {% if page == 'login' %}
        <div class="login-wrapper">
            <div class="login-card">
                <div style="font-size:3rem; margin-bottom:20px;">💸</div>
                <h2 style="margin-bottom:10px;">Cashflow App</h2>
                <p style="color:var(--text-soft); margin-bottom:30px;">Login untuk mengatur keuangan</p>
                {% if error %}
                    <div style="background:rgba(255, 68, 68, 0.2); border:1px solid #FF4444; color:#FF4444; padding:10px; border-radius:10px; margin-bottom:15px; font-size:0.9rem;">⚠️ {{ error }}</div>
                    <script>alert("{{ error }}");</script>
                {% endif %}
                <form action="/login" method="POST">
                    <input type="text" name="username" class="input-box" placeholder="Username" style="text-align:center; margin-bottom:15px;" required>
                    <input type="password" name="pin" class="input-box" placeholder="PIN (6 Digit)" style="text-align:center; margin-bottom:15px;" inputmode="numeric" maxlength="6" pattern="\d{6}" required>
                    <button class="submit-btn">MASUK</button>
                </form>
            </div>
        </div>

        {% elif page == 'home' %}
        <div class="top-nav">
            <div class="greeting"><small>Hi, {{ user.name }}!</small><h1>Dashboard</h1></div>
            <div class="user-avatar" style="{% if user.avatar_file %}background-image:url('/uploads/{{user.avatar_file}}');{% endif %}">{% if not user.avatar_file %}{{ '👧' if user.gender == 'female' else '👦' }}{% endif %}</div>
        </div>
        <div class="wallet-card">
            <div style="font-size:0.8rem; opacity:0.8;">SALDO</div>
            <div class="balance-val">{{ balance_str }}</div>
            <div class="wallet-stats">
                <div class="stat-pill"><i class="fa-solid fa-arrow-down" style="color:#00E396"></i> {{ in_str }}</div>
                <div class="stat-pill"><i class="fa-solid fa-arrow-up" style="color:#FF4444"></i> {{ out_str }}</div>
            </div>
        </div>
        <div class="section-head" style="margin-bottom:15px; display:flex; justify-content:space-between;">
            <h3>Data Terakhir</h3>
            <a href="/data" style="color:var(--accent-blue); text-decoration:none; font-size:0.85rem;">View All</a>
        </div>
        {% for t in transactions[:5] %}
        <div class="trans-item">
            <div style="display:flex; gap:10px; align-items:center;">
                {# Paksa category jadi string dulu dengan |string agar tidak error jika isinya angka #}
            {% set cat_str = t.category|string %}
            <div style="font-size:1.5rem;">{{ cat_str.split(' ')[0] if ' ' in cat_str else '📝' }}</div>
            <div>
                <div style="font-weight:600; font-size:0.95rem;">
                    {{ cat_str.split(' ', 1)[1] if ' ' in cat_str else cat_str }}
                </div>
                <div style="font-size:0.75rem; color:var(--text-soft);">{{ t.date }} • {{ t.desc }}</div>
            </div>
            </div>
            <div class="amt {{ t.type }}" style="font-weight:700;">{{ '+' if t.type == 'in' else '-' }}Rp {{ "{:,.0f}".format(t.amount).replace(',', '.') }}</div>
        </div>
        {% endfor %}

        {% elif page == 'stats' %}
        <div class="top-nav"><div class="greeting"><h1>Statistik</h1></div></div>
        <form action="/stats" method="GET">
            <div class="filter-bar">
                <button type="submit" name="filter" value="today"
                    class="filter-btn {{ 'active' if filter_active == 'today' else '' }}">
                    Hari Ini
                </button>

                <button type="submit" name="filter" value="yesterday"
                    class="filter-btn {{ 'active' if filter_active == 'yesterday' else '' }}">
                    Kemarin
                </button>

                <button type="button" onclick="toggleMonth(this)"
                    class="filter-btn {{ 'active' if filter_active == 'month' else '' }}">
                    Bulan
                </button>

                <button type="button" onclick="toggleRange(this)"
                    class="filter-btn {{ 'active' if filter_active in ['range','single'] else '' }}">
                    Pilih Tanggal
                </button>
            </div>

            <div id="monthBoxStats" style="display:none; margin-bottom:12px;">
                {% set bulan = ["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"] %}
                <select name="month" class="input-box">
                    <option value="">Pilih Bulan</option>
                    {% for ym in available_months %}
                        <option value="{{ ym }}" {% if month_selected == ym %}selected{% endif %}>
                            {% set y = ym.split('-')[0] %}
                            {% set m = ym.split('-')[1]|int %}
                            {{ bulan[m-1] }} {{ y }}
                        </option>
                        {% endfor %}

                </select>

                <div style="display:flex; justify-content:flex-end; margin-top:10px;">
                    <button type="submit" name="filter" value="month"
                        class="filter-btn active"
                        style="margin-left:12px; padding:10px 18px;">
                        Go
                    </button>
                </div>

                {% if filter_active == 'month' and month_selected %}
                    <div style="margin-top:6px; font-size:13px; color:#666;">
                        Filter aktif:
                        <b>
                        {% set y = month_selected.split('-')[0] %}
                        {% set m = month_selected.split('-')[1]|int %}
                        {{ bulan[m-1] }} {{ y }}
                        </b>
                    </div>
                {% endif %}
            </div>



            <div id="rangeBoxStats" style="display:none; margin-bottom:12px;">
                <div style="display:flex; gap:10px; align-items:center;">
                    <input type="date" name="start_date" id="sd" class="input-box" style="flex:1;">
                    <input type="date" name="end_date" id="ed" class="input-box" style="flex:1;">
                    <button type="submit" name="filter" value="range"class="filter-btn active"style="white-space:nowrap;">Go</button>
                </div>


                {% if filter_active == 'range' and start_date and end_date %}
                    <div style="margin-top:6px; font-size:13px; color:#666;">
                        Filter aktif:
                        <b>{{ start_date }}</b> sampai <b>{{ end_date }}</b>
                    </div>
                {% elif filter_active == 'range' and start_date and not end_date %}
                    <div style="margin-top:6px; font-size:13px; color:#666;">
                        Filter aktif:
                        <b>{{ start_date }}</b>
                    </div>
                {% endif %}
            </div>


        </form>
        <div class="wallet-card" style="background:var(--bg-card); box-shadow:none; border:1px solid rgba(255,255,255,0.1);">
            <div style="text-align:center;">
                <div style="font-size:0.8rem; color:var(--text-soft);">TOTAL PENGELUARAN ({{ filter_label }})</div>
                <div style="font-size:2rem; font-weight:700; color:var(--accent-pink); margin-top:5px;">{{ out_str }}</div>
            </div>
        </div>
        <div class="stats-grid">
    <div class="stat-box">
        <div class="stat-label" style="color:var(--accent-green);">TOTAL PEMASUKAN</div>
        <div class="stat-num">{{ in_str }}</div>
    </div>

    <div class="stat-box">
        <div class="stat-label" style="color:var(--accent-pink);">TOTAL PENGELUARAN</div>
        <div class="stat-num">{{ out_str }}</div>
    </div>

    <div class="stat-box">
        <div class="stat-label" style="color:var(--accent-pink);">PRIBADI</div>
        <div class="stat-num">{{ out_pribadi_str }}</div>
    </div>

    <div class="stat-box">
        <div class="stat-label" style="color:var(--accent-blue);">BISNIS</div>
        <div class="stat-num">{{ out_bisnis_str }}</div>
    </div>
</div>


        {% elif page == 'data' %}
        <div class="top-nav"><div class="greeting"><h1>Riwayat Data</h1></div></div>
        <form action="/data" method="GET">
           <div class="filter-bar">
                <button type="submit" name="filter" value="today"
                    class="filter-btn {{ 'active' if filter_active == 'today' else '' }}">
                    Hari Ini
                </button>

                <button type="submit" name="filter" value="yesterday"
                    class="filter-btn {{ 'active' if filter_active == 'yesterday' else '' }}">
                    Kemarin
                </button>

                <button type="button" onclick="toggleMonth(this)"
                    class="filter-btn {{ 'active' if filter_active == 'month' else '' }}">
                    Bulan
                </button>

                <button type="button" onclick="toggleRange(this)"
                    class="filter-btn {{ 'active' if filter_active in ['range','single'] else '' }}">
                    Pilih Tanggal
                </button>
            </div>

            <div id="monthBoxData" style="display:none; margin-bottom:12px;">
                {% set bulan = ["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"] %}
                <select name="month" class="input-box">
                    <option value="">Pilih Bulan</option>
                    {% for ym in available_months %}
                    <option value="{{ ym }}" {% if month_selected == ym %}selected{% endif %}>
                        {% set y = ym.split('-')[0] %}
                        {% set m = ym.split('-')[1]|int %}
                        {{ bulan[m-1] }} {{ y }}
                    </option>
                    {% endfor %}

                </select>

                <div style="display:flex; gap:10px; align-items:center; justify-content:flex-end; margin-top:10px;">
                <button type="submit" name="filter" value="month"class="filter-btn active"style="white-space:nowrap;">Go</button>
            </div>

            </div>


        <div id="rangeBoxData" style="display:none; margin-bottom:12px;">
            <div style="display:flex; gap:10px; align-items:center;">
                <input type="date" name="start_date" class="input-box" style="flex:1;" value="{{ start_date or '' }}">
                <input type="date" name="end_date" class="input-box" style="flex:1;" value="{{ end_date or '' }}">
                <button type="submit" name="filter" value="range" class="filter-btn active" style="white-space:nowrap;">Go</button>
            </div>
        </div>



        </form>
        <div style="padding-bottom:50px;">
            {% for t in transactions %}
            <div class="trans-item">
                <div style="flex:1;">
                    <div style="font-weight:600;">{{ t.category }} <span style="font-size:0.7rem; color:var(--text-soft);">({{ t.by }})</span></div>
                    <div style="font-size:0.75rem; color:var(--text-soft);">
                        <span class="usage-badge {{ 'badge-pribadi' if t.usage == 'pribadi' else 'badge-bisnis' }}">{{ t.usage }}</span>
                        {{ t.date }} • {{ t.desc }}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div class="amt {{ t.type }}" style="font-weight:700; font-size:0.9rem;">Rp {{ "{:,.0f}".format(t.amount).replace(',', '.') }}</div>
                    <div style="margin-top:5px;">
                        <button
                            onclick='openEditModal({
                                "row": {{ t._row }},
                                "amount": {{ t.amount }},
                                "desc": {{ t.desc|tojson }},
                                "category": {{ t.category|tojson }},
                                "type": {{ t.type|tojson }},
                                "usage": {{ t.usage|tojson }}
                            })'
                            class="btn-mini">
                            <i class="fa-solid fa-pen"></i>
                            </button>

                        <a href="/delete/{{ t.id }}" onclick="return confirm('Yakin hapus data ini?')" class="btn-mini" style="color:#FF4444;"><i class="fa-solid fa-trash"></i></a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>

        {% elif page == 'settings' %}
        <div class="top-nav"><div class="greeting"><h1>Me</h1></div></div>
        <div style="background:var(--bg-card); padding:30px; border-radius:30px;">
            <div style="text-align:center; margin-bottom:20px;">
                <div class="user-avatar" style="width:90px; height:90px; font-size:3rem; margin:0 auto 15px auto; {% if user.avatar_file %}background-image:url('/uploads/{{user.avatar_file}}');{% endif %}">{% if not user.avatar_file %}{{ '👧' if user.gender == 'female' else '👦' }}{% endif %}</div>
                <h3>{{ user.name }}</h3>
                <p style="color:var(--text-soft);">@{{ user.username }}</p>
            </div>
            <div style="margin-bottom:20px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:20px;">
                <label style="font-size:0.8rem; color:#FF9A9E; font-weight:bold; margin-bottom:10px; display:block;">KATEGORI SAYA</label>
                <div class="cat-tag-container">
    {% for cat in user.categories %}
    <div class="cat-tag">
        {{ cat }}
        <div style="display:flex; gap:5px; margin-left:5px;">
            <i class="fa-solid fa-pen" style="font-size:0.7rem; cursor:pointer; color:var(--accent-blue);"
               onclick="promptEditCategory('{{ cat }}')"></i>
            <a href="/delete_category/{{ cat }}" class="cat-delete" style="text-decoration:none;">×</a>
                </div>
         </div>
         {% endfor %}
        </div>
                <form action="/add_category" method="POST" style="display:flex; gap:10px;">
                    <input type="text" name="new_category" class="input-box" placeholder="Tambah kategori..." style="padding:10px; font-size:0.9rem;">
                    <button class="submit-btn" style="width:auto; margin:0; padding:0 20px;">+</button>
                </form>
            </div>
            <form action="/update_profile" method="POST" enctype="multipart/form-data">
                <div style="margin-bottom:15px;">
                    <label style="font-size:0.8rem; color:var(--text-soft); margin-left:5px;">Ganti Foto Profil</label>
                    <input type="file" name="avatar" class="input-box" style="padding:10px;">
                </div>
                <div style="margin-bottom:15px;">
                    <label style="font-size:0.8rem; color:var(--text-soft); margin-left:5px;">Nama Panggilan</label>
                    <input type="text" name="name" value="{{ user.name }}" class="input-box">
                </div>
                <div style="margin-bottom:15px;">
                    <label style="font-size:0.8rem; color:var(--text-soft); margin-left:5px;">Username</label>
                    <input type="text" name="new_username" value="{{ user.username }}" class="input-box">
                </div>
                <div style="margin-bottom:15px; border-top:1px solid rgba(255,255,255,0.1); padding-top:15px;">
                    <label style="font-size:0.8rem; color:#FF9A9E; margin-left:5px; font-weight:bold;">Ubah PIN (Opsional)</label>
                    <input type="password" name="old_pin" placeholder="Masukkan PIN Lama (Wajib jika ganti)" class="input-box" style="margin-bottom:10px;" maxlength="6" inputmode="numeric">
                    <input type="password" name="new_pin" placeholder="PIN Baru" class="input-box" maxlength="6" inputmode="numeric">
                </div>
                <button class="submit-btn">SIMPAN PERUBAHAN</button>
            </form>
            <a href="/logout"><button class="submit-btn logout">LOGOUT</button></a>
        </div>
        {% endif %}
    </div>

    {% if page != 'login' %}
    <div class="bottom-nav">
        <a href="/" class="nav-item {{ 'active' if page == 'home' else '' }}"><i class="fa-solid fa-house"></i><span>Home</span></a>
        <a href="/data" class="nav-item {{ 'active' if page == 'data' else '' }}"><i class="fa-solid fa-list-ul"></i><span>Data</span></a>
        <div class="fab-container"><button class="fab-btn" onclick="openAddModal()"><i class="fa-solid fa-plus"></i></button></div>
        <a href="/stats?filter=today" class="nav-item {{ 'active' if page == 'stats' else '' }}"><i class="fa-solid fa-chart-pie"></i><span>Stats</span></a>
        <a href="/settings" class="nav-item {{ 'active' if page == 'settings' else '' }}"><i class="fa-solid fa-user"></i><span>Me</span></a>
    </div>

    <div class="modal-overlay" id="inputModal">
        <div class="modal-card">
            <h3 id="modalTitle" style="margin-bottom:20px; text-align:center;">Tambah Data</h3>
            <form action="/add" method="POST" id="transForm">
                <input type="hidden" name="id" id="inputId">
                <input type="hidden" name="type" id="inputType" value="out">
                <input type="hidden" name="usage" id="inputUsage" value="pribadi">

                <div style="display:flex; gap:10px; margin-bottom:20px;">
                    <div id="btn-out" onclick="setType('out')" style="flex:1; padding:15px; text-align:center; background:rgba(255,117,140,0.2); color:#FF758C; border-radius:15px; font-weight:bold; cursor:pointer; border:1px solid #FF758C;">PENGELUARAN</div>
                    <div id="btn-in" onclick="setType('in')" style="flex:1; padding:15px; text-align:center; background:rgba(255,255,255,0.05); color:#B7B9D2; border-radius:15px; font-weight:bold; cursor:pointer; border:1px solid transparent;">PEMASUKAN</div>
                </div>

                <div style="margin-bottom:15px;">
                    <label style="font-size:0.8rem; color:#B7B9D2; margin-left:5px;">Nominal (Rp)</label>
                    <input type="text" name="amount" id="amtBox" placeholder="0" class="input-box" style="font-size:1.5rem; font-weight:bold; color:#FF758C;" required autocomplete="off" inputmode="numeric">
                </div>

                <div id="catWrapper" style="margin-bottom:15px;">
                    <label style="font-size:0.8rem; color:#B7B9D2; margin-left:5px;">Kategori</label>
                    <select name="category" id="catBox" class="input-box">
                        {% for cat in user.categories %}
                        <option value="{{ cat }}">{{ cat }}</option>
                        {% endfor %}
                    </select>
                </div>

                <div id="useWrapper" style="margin-bottom:15px;">
                    <label style="font-size:0.8rem; color:#B7B9D2; margin-left:5px;">Keperluan</label>
                    <div style="display:flex; gap:10px;">
                        <div class="filter-btn active" id="use-pribadi" onclick="setUsage('pribadi')" style="flex:1; text-align:center;">👤 Pribadi</div>
                        <div class="filter-btn" id="use-bisnis" onclick="setUsage('bisnis')" style="flex:1; text-align:center;">💼 Bisnis</div>
                    </div>
                </div>

                <div style="margin-bottom:20px;">
                    <input type="text" name="desc" id="descBox" placeholder="Keterangan" class="input-box">
                </div>

                <button class="submit-btn">SIMPAN</button>
                <button type="button" onclick="closeModal()" style="width:100%; padding:15px; background:none; border:none; color:#B7B9D2; cursor:pointer;">Batal</button>
            </form>
        </div>
    </div>
    {% endif %}

    <script>
        function promptEditCategory(oldName) {
            const newName = prompt("Ubah nama kategori '" + oldName + "' menjadi:", oldName);
                if (newName && newName !== oldName) {
                    // Buat form bayangan untuk kirim data ke Flask
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = '/edit_category';

                    const inputOld = document.createElement('input');
                    inputOld.type = 'hidden';
                    inputOld.name = 'old_name';
                    inputOld.value = oldName;

                    const inputNew = document.createElement('input');
                    inputNew.type = 'hidden';
                    inputNew.name = 'new_name';
                    inputNew.value = newName;

                    form.appendChild(inputOld);
                    form.appendChild(inputNew);
                    document.body.appendChild(form);
                    form.submit();
                    }
                }

        function toggleMonth(){
            const m = document.getElementById('monthBoxStats') || document.getElementById('monthBoxData');
            const r = document.getElementById('rangeBoxStats') || document.getElementById('rangeBoxData');
            const btnMonth = event.currentTarget; // Tombol yang diklik
            const btnRange = btnMonth.parentElement.querySelector('button[onclick="toggleRange()"]');

            if(!m) return;
            if(m.style.display === 'none'){
                m.style.display = 'block';
                if(r) r.style.display = 'none';
                btnMonth.classList.add('active'); // Nyalakan warna
                if(btnRange) btnRange.classList.remove('active'); // Matikan warna tombol sebelah
            }else{
                m.style.display = 'none';
                // Hanya hapus active jika filter_active dari backend bukan 'month'
                if("{{ filter_active }}" !== 'month') btnMonth.classList.remove('active');
            }
        }

        function toggleMonth(btn){
            const mBox = document.getElementById('monthBoxStats') || document.getElementById('monthBoxData');
            const rBox = document.getElementById('rangeBoxStats') || document.getElementById('rangeBoxData');

            // Matikan semua warna active di filter-bar
            const allBtns = btn.parentElement.querySelectorAll('.filter-btn');
            allBtns.forEach(b => b.classList.remove('active'));

            if(mBox.style.display === 'none'){
                mBox.style.display = 'block';
                if(rBox) rBox.style.display = 'none';
                btn.classList.add('active'); // Nyalakan hanya tombol ini
            } else {
                mBox.style.display = 'none';
                // Kembalikan warna ke filter yang sebenarnya aktif dari server
                const realActive = "{{ filter_active }}";
                if (realActive !== 'month') btn.classList.remove('active');
                // Trigger reload kecil atau biarkan user klik filter lain
            }
        }

        function toggleRange(btn){
            const mBox = document.getElementById('monthBoxStats') || document.getElementById('monthBoxData');
            const rBox = document.getElementById('rangeBoxStats') || document.getElementById('rangeBoxData');

            // Matikan semua warna active di filter-bar
            const allBtns = btn.parentElement.querySelectorAll('.filter-btn');
            allBtns.forEach(b => b.classList.remove('active'));

            if(rBox.style.display === 'none'){
                rBox.style.display = 'block';
                if(mBox) mBox.style.display = 'none';
                btn.classList.add('active'); // Nyalakan hanya tombol ini
            } else {
                rBox.style.display = 'none';
                const realActive = "{{ filter_active }}";
                if (realActive !== 'range' && realActive !== 'single') btn.classList.remove('active');
            }
        }

        window.onload = function(){
            const f = "{{ filter_active }}";
            const mBox = document.getElementById('monthBoxStats') || document.getElementById('monthBoxData');
            const rBox = document.getElementById('rangeBoxStats') || document.getElementById('rangeBoxData');

            if(f === 'month'){
                if(mBox) mBox.style.display = 'block';
            }
            if(f === 'range' || f === 'single'){
                if(rBox) rBox.style.display = 'block';
            }
        }


        function openAddModal() {
            document.getElementById('inputModal').classList.add('active');
            document.getElementById('modalTitle').innerText = "Tambah Data";
            document.getElementById('transForm').action = "/add";
            document.getElementById('inputId').value = "";
            document.getElementById('amtBox').value = "";
            document.getElementById('descBox').value = "";
            setType('out'); setUsage('pribadi');
        }
        function openEditModal(data) {
            document.getElementById('inputModal').classList.add('active');
            document.getElementById('modalTitle').innerText = "Edit Data";
            document.getElementById('transForm').action = "/edit_transaction";
            document.getElementById('inputId').value = data.row;
            document.getElementById('amtBox').value = data.amount.toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, ".");
            document.getElementById('descBox').value = data.desc;
            document.getElementById('catBox').value = data.category;
            setType(data.type); setUsage(data.usage);
        }
        function closeModal() { document.getElementById('inputModal').classList.remove('active'); }
        function setType(t) {
            document.getElementById('inputType').value = t;
            const bOut = document.getElementById('btn-out'); const bIn = document.getElementById('btn-in'); const ab = document.getElementById('amtBox');
            const catWrapper = document.getElementById('catWrapper'); const useWrapper = document.getElementById('useWrapper');
            if(t=='out'){
                bOut.style.background='rgba(255,117,140,0.2)'; bOut.style.color='#FF758C'; bOut.style.borderColor='#FF758C';
                bIn.style.background='rgba(255,255,255,0.05)'; bIn.style.color='#B7B9D2'; bIn.style.borderColor='transparent';
                ab.style.color='#FF758C';
                catWrapper.style.display = 'block'; useWrapper.style.display = 'block';
            } else {
                bIn.style.background='rgba(0,227,150,0.2)'; bIn.style.color='#00E396'; bIn.style.borderColor='#00E396';
                bOut.style.background='rgba(255,255,255,0.05)'; bOut.style.color='#B7B9D2'; bOut.style.borderColor='transparent';
                ab.style.color='#00E396';
                catWrapper.style.display = 'none'; useWrapper.style.display = 'none';
            }
        }
        function setUsage(u) {
            document.getElementById('inputUsage').value = u;
            document.getElementById('use-pribadi').classList.remove('active');
            document.getElementById('use-bisnis').classList.remove('active');
            document.getElementById('use-'+u).classList.add('active');
        }
        const amtBox = document.getElementById('amtBox');
        if(amtBox) amtBox.addEventListener('input', function(){ this.value = this.value.replace(/[^0-9]/g, '').replace(/\\B(?=(\\d{3})+(?!\\d))/g, "."); });
    </script>
</body>
</html>
"""

# ==========================================
# BACKEND ROUTES
# ==========================================
@app.route('/uploads/<filename>')
def uploaded_file(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        pin = request.form.get('pin')
        found_user = None
        for key, val in USERS.items():
            if val['username'] == username:
                found_user = (key, val)
                break
        if not found_user: return render_template_string(HTML_TEMPLATE, page='login', error="Username tidak ditemukan!")
        key, user_data = found_user
        if user_data['pin'] != pin: return render_template_string(HTML_TEMPLATE, page='login', error="PIN Salah! Coba lagi.")
        session.permanent = True
        session['user_key'] = key
        flash(f"Selamat datang, {user_data['name']}!", "success")
        return redirect('/')
    return render_template_string(HTML_TEMPLATE, page='login')

@app.route('/edit_transaction', methods=['POST'])
def edit_transaction():
    if 'user_key' not in session:
        return redirect('/login')

    sheet = get_db_connection()
    if not sheet:
        flash("Gagal koneksi ke database", "error")
        return redirect('/data')

    row = int(request.form.get('id'))   # row sheet
    amount = request.form.get('amount').replace('.', '')
    desc = request.form.get('desc')
    category = request.form.get('category')
    ttype = request.form.get('type')
    usage = request.form.get('usage')
    editor = USERS[session['user_key']]['name']  # 🔥 nama pengedit

    try:
        # Kolom asumsi:
        # A = date
        # B = type
        # C = amount
        # D = category
        # E = usage
        # F = desc
        # G = by

        sheet.update_cell(row, 3, category)     # category
        sheet.update_cell(row, 4, desc)   # desc
        sheet.update_cell(row, 5, amount)      # amount
        sheet.update_cell(row, 6, usage)       # usage
        sheet.update_cell(row, 7, editor)     # by (🔥 pengedit)

        flash("Data berhasil diedit", "success")
    except Exception as e:
        print("EDIT ERROR:", e)
        flash("Gagal edit data", "error")

    return redirect('/data')


@app.route('/logout')
def logout():
    session.pop('user_key', None)
    return redirect('/login')

@app.route('/')
def home():
    if 'user_key' not in session: return redirect('/login')

    user_key = session['user_key']
    live_data = get_settings() # 👈 Ambil data terbaru dari Cloud
    user = USERS[user_key]

    # Update data user sementara dengan data dari Sheets
    user['name'] = live_data.get(f"{user_key}_name", user['name'])
    user['avatar_file'] = live_data.get(f"{user_key}_avatar", user['avatar_file'])

    transactions = fetch_all_data()
    today = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
    daily_stats = [t for t in transactions if t['date'] == today]
    total_bal, _, _, _, _ = calculate_stats(transactions)
    _, d_in, d_out, _, _ = calculate_stats(daily_stats)

    return render_template_string(HTML_TEMPLATE,
        page='home',
        user=user, # 👈 Sekarang user sudah membawa info foto terbaru
        balance_str=f"Rp {total_bal:,.0f}".replace(',', '.'),
        in_str=f"Rp {d_in:,.0f}".replace(',', '.'),
        out_str=f"Rp {d_out:,.0f}".replace(',', '.'),
        transactions=transactions)
@app.route('/stats')
def stats():
    if 'user_key' not in session:
        return redirect('/login')

    transactions = fetch_all_data()
    available_months = generate_available_months(transactions)

    ftype = request.args.get('filter')
    s_date = request.args.get('start_date')
    e_date = request.args.get('end_date')
    month = request.args.get('month')

    # AUTO DETECT FILTER
    if ftype is None:
        if month:
            ftype = 'month'
        elif s_date and e_date:
            ftype = 'range'
        elif s_date and not e_date:
            ftype = 'single'
        else:
            ftype = 'today'

    filtered = filter_transactions(transactions, ftype, s_date, e_date, month)

    _, tin, tout, p, b = calculate_stats(filtered)

    # ==========================
    # LABEL HUMAN READABLE
    # ==========================
    if ftype == 'month' and month:
        try:
            y, m = month.split('-')
            bulan_map = ["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"]
            filter_label = f"{bulan_map[int(m)-1]} {y}"
        except:
            filter_label = month

    elif ftype == 'range' and s_date and e_date:
        filter_label = f"{s_date} s/d {e_date}"

    elif ftype == 'single' and s_date:
        filter_label = s_date

    elif ftype == 'today':
        filter_label = "Hari Ini"

    elif ftype == 'yesterday':
        filter_label = "Kemarin"

    else:
        filter_label = "Semua Data"

    return render_template_string(
        HTML_TEMPLATE,
        available_months=available_months,
        page='stats',
        user=USERS[session['user_key']],
        filter_active=ftype,
        in_str=f"Rp {tin:,.0f}".replace(',', '.'),
        out_str=f"Rp {tout:,.0f}".replace(',', '.'),
        out_pribadi_str=f"Rp {p:,.0f}".replace(',', '.'),
        out_bisnis_str=f"Rp {b:,.0f}".replace(',', '.'),
        month_selected=month,
        start_date=s_date,
        end_date=e_date,
        filter_label=filter_label
    )



@app.route('/data')
def data_page():
    if 'user_key' not in session: return redirect('/login')
    transactions = fetch_all_data()
    available_months = generate_available_months(transactions)

    ftype = request.args.get('filter', 'today')
    s_date = request.args.get('start_date')
    e_date = request.args.get('end_date')
    month = request.args.get('month')

    filtered = filter_transactions(transactions, ftype, s_date, e_date, month)

    return render_template_string(
    HTML_TEMPLATE,
    available_months=available_months,
    page='data',
    user=USERS[session['user_key']],
    transactions=filtered,
    filter_active=ftype,
    month_selected=month,
    start_date=s_date,
    end_date=e_date
    )


@app.route('/add', methods=['POST'])
def add():
    if 'user_key' not in session: return redirect('/login')
    sheet = get_db_connection()
    if not sheet:
        flash("Gagal connect ke Google Sheet!", "error")
        return redirect('/')

    amt = request.form.get('amount')
    type_ = request.form.get('type')

    # LOGIC AUTO INCOME
    category = "✨ Income" if type_ == 'in' else request.form.get('category')
    usage = "bisnis" if type_ == 'in' else request.form.get('usage')

    if amt:
        new_row = [
            random.randint(10000,99999), # ID Unik
            datetime.now().strftime("%Y-%m-%d"),
            category,
            request.form.get('desc'),
            int(amt.replace('.', '')),
            type_,
            usage,
            USERS[session['user_key']]['name']
        ]
        try:
            # Insert row 2 (after header)
            sheet.insert_row(new_row, 2)
            flash("Data berhasil disimpan ke Google Sheet!", "success")
        except Exception as e:
            flash(f"Error Saving: {e}", "error")

    return redirect('/')

@app.route('/delete/<int:tid>')
def delete_transaction(tid):
    if 'user_key' not in session: return redirect('/login')
    sheet = get_db_connection()
    try:
        cell = sheet.find(str(tid), in_column=1)
        if cell:
            sheet.delete_rows(cell.row)
            flash("Data dihapus dari Sheet.", "success")
    except Exception as e:
        flash(f"Gagal Hapus: {e}", "error")
    return redirect('/data')

# Settings & Category routes (Local only for simplification)
@app.route('/settings')
def settings():
    if 'user_key' not in session: return redirect('/login')

    user_key = session['user_key']
    live_data = get_settings() # Mengambil data dari tab 'Settings'
    user = USERS[user_key]

    # Ambil data dari Sheets untuk menimpa data sementara di USERS
    user['name'] = live_data.get(f"{user_key}_name", user['name'])
    user['avatar_file'] = live_data.get(f"{user_key}_avatar", user['avatar_file'])

    # Sinkronisasi Kategori
    cat_string = live_data.get(f"{user_key}_categories")
    if cat_string:
        # Mengubah string "Makan, Belanja" menjadi list ['Makan', 'Belanja']
        user['categories'] = [c.strip() for c in cat_string.split(',') if c.strip()]

    return render_template_string(HTML_TEMPLATE, page='settings', user=user)

@app.route('/add_category', methods=['POST'])
def add_category():
    if 'user_key' not in session: return redirect('/login')
    user_key = session['user_key']
    new_cat = request.form.get('new_category')

    if new_cat:
        live_data = get_settings()
        # 🔥 Gunakan user_key agar spesifik (misal: silviapasya_categories)
        key_name = f"{user_key}_categories"
        existing_cats = live_data.get(key_name, "")

        # Gabungkan kategori lama dengan yang baru
        updated_cats = f"{existing_cats}, {new_cat}" if existing_cats else new_cat

        # Simpan string baru ke Sheets
        update_setting(key_name, updated_cats)
        flash(f"Kategori {new_cat} berhasil ditambah!", "success")

    return redirect('/settings')

@app.route('/delete_category/<cat_name>')
def delete_category(cat_name):
    if 'user_key' not in session: return redirect('/login')
    user_key = session['user_key']
    key_name = f"{user_key}_categories"

    live_data = get_settings()
    existing_cats = live_data.get(key_name, "")

    # Bersihkan spasi dan pecah string menjadi list
    cat_list = [c.strip() for c in existing_cats.split(',') if c.strip()]

    if cat_name in cat_list:
        cat_list.remove(cat_name)
        # Gabungkan kembali jadi string untuk disimpan
        new_cat_string = ", ".join(cat_list)
        update_setting(key_name, new_cat_string)
        flash(f"Kategori {cat_name} dihapus!", "success")

    return redirect('/settings')

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_key' not in session: return redirect('/login')

    user_key = session['user_key'] # Ambil key (misal: 'silviapasya')
    user = USERS[user_key]

    # 1. Ambil data dari form
    new_name = request.form.get('name')
    new_username = request.form.get('new_username')
    new_pin = request.form.get('new_pin')
    old_pin = request.form.get('old_pin')

    # 2. Update Nama di Sheets (Gunakan key unik per user agar tidak tertukar)
    if new_name:
        user['name'] = new_name
        update_setting(f"{user_key}_name", new_name)

    # 3. Logika Update PIN (Masih lokal, tapi bisa kamu tambah ke Sheets nanti)
    if new_pin:
        if old_pin != user['pin']:
            flash("PIN Lama Salah!", "error")
            return redirect('/settings')
        user['pin'] = new_pin
        update_setting(f"{user_key}_pin", new_pin)

    # 4. Update Foto Profil ke Sheets
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file.filename != '':
            filename = secure_filename(file.filename)
            # Simpan file fisik ke folder /uploads (untuk sementara)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            # Simpan NAMA FILE ke Google Sheets agar bisa dipanggil lagi nanti
            user['avatar_file'] = filename
            update_setting(f"{user_key}_avatar", filename)

    flash("Profil berhasil disimpan ke Cloud Sheets!", "success")
    return redirect('/settings')

@app.route('/update_categories', methods=['POST'])
def update_categories():
    new_cats = request.form.get('categories') # Misalnya user input string dipisahkan koma
    if update_setting('categories', new_cats):
        return redirect(url_for('me'))
    return "Gagal update", 400
@app.route('/edit_category', methods=['POST'])
def edit_category():
    if 'user_key' not in session: return redirect('/login')
    user_key = session['user_key']
    old_cat = request.form.get('old_name')
    new_cat = request.form.get('new_name')

    if old_cat and new_cat:
        key_name = f"{user_key}_categories"
        live_data = get_settings()
        existing_cats = live_data.get(key_name, "")

        # Pecah string jadi list, ganti namanya, lalu gabung lagi
        cat_list = [c.strip() for c in existing_cats.split(',') if c.strip()]
        if old_cat in cat_list:
            idx = cat_list.index(old_cat)
            cat_list[idx] = new_cat

            new_cat_string = ", ".join(cat_list)
            update_setting(key_name, new_cat_string)
            flash(f"Kategori '{old_cat}' diubah menjadi '{new_cat}'", "success")

    return redirect('/settings')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

