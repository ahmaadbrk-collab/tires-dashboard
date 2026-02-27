from flask import Flask, request
import pandas as pd
import plotly.graph_objects as go
import os

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PROFIT_RATES = {
    ('1','2026-01'): 0.2879, ('1','2026-02'): 0.3413,
    ('2','2026-01'): 0.4195, ('2','2026-02'): 0.3329,
    ('3','2026-01'): 0.3286, ('3','2026-02'): 0.3738,
    ('4','2026-01'): 0.2338, ('4','2026-02'): 0.2342,
}

def load_2025():
    df = pd.read_csv(os.path.join(BASE_DIR, '2025_TIRE.csv'), sep=';', header=None)
    df.columns = ['SaleDate','SaleMonth','SaleYear','BranchName','BranchID','InvoiceID','TotalSales','TotalCost','TotalProfit','ItemCount']
    df['SaleDate'] = pd.to_datetime(df['SaleDate'])
    df['TotalSales'] = pd.to_numeric(df['TotalSales'], errors='coerce').fillna(0) / 1.15
    df['TotalCost'] = pd.to_numeric(df['TotalCost'], errors='coerce').fillna(0) / 1.15
    df['TotalProfit'] = pd.to_numeric(df['TotalProfit'], errors='coerce').fillna(0) / 1.15
    df['Month'] = df['SaleDate'].dt.strftime('%Y-%m')
    df['branch_id'] = df['BranchName'].str.extract(r'(\d+)')
    return df

def parse_date_flexible(val, row_num):
    val = str(val).strip()
    # صيغة dd/mm/yyyy
    if '/' in val:
        return pd.to_datetime(val, dayfirst=True, errors='coerce')
    # صيغة YYYY-MM-DD - إذا كان الشهر = رقم اليوم (مشكلة استخراج)
    ts = pd.to_datetime(val, errors='coerce')
    if pd.isna(ts):
        return None
    # إذا اليوم = 1 والشهر يساوي رقم الصف — يعني الشهر هو رقم اليوم فعلياً
    if ts.day == 1 and ts.month == row_num and row_num <= 12:
        return pd.Timestamp(f'{ts.year}-01-{row_num:02d}')
    return ts

def load_2026_daily():
    df = pd.read_excel(os.path.join(BASE_DIR, 'ج.xlsx'), header=2)
    # استخدام أسماء الأعمدة مباشرة
    df = df[['الرقم', 'التاريخ',
             'مبيعات فرع 1 | المجموع',
             'مبيعات فرع 2 | المجموع',
             'مبيعات فرع 3 | المجموع',
             'مبيعات فرع 4 | المجموع']].copy()
    df.columns = ['الرقم','التاريخ','ف1','ف2','ف3','ف4']
    df = df[df['التاريخ'].notna()]
    df['الرقم'] = pd.to_numeric(df['الرقم'], errors='coerce')
    df = df[df['الرقم'].notna() & (df['الرقم'] > 0)]
    df['التاريخ'] = df.apply(lambda r: parse_date_flexible(r['التاريخ'], int(r['الرقم'])), axis=1)
    df = df[df['التاريخ'].notna()]
    df = df[df['التاريخ'].dt.year == 2026]
    for col in ['ف1','ف2','ف3','ف4']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    rows = []
    for _, row in df.iterrows():
        date = row['التاريخ']
        month = date.strftime('%Y-%m')
        for branch, col in [('1','ف1'),('2','ف2'),('3','ف3'),('4','ف4')]:
            sales = row[col] / 1.15
            rate = PROFIT_RATES.get((branch, month), 0.30)
            profit = sales * rate
            cost = sales - profit
            rows.append({'SaleDate': date, 'Month': month, 'branch_id': branch,
                'BranchName': f'فرع {branch}', 'TotalSales': sales, 'TotalCost': cost, 'TotalProfit': profit})
    return pd.DataFrame(rows)

df25 = load_2025()
df26 = load_2026_daily()

# بيانات يومية كاملة
daily25 = df25.groupby(['branch_id','BranchName','SaleDate']).agg(
    sales=('TotalSales','sum'), cost=('TotalCost','sum'), profit=('TotalProfit','sum'), invoices=('InvoiceID','nunique')
).reset_index()
daily25['Month'] = daily25['SaleDate'].dt.strftime('%Y-%m')

daily26 = df26.groupby(['branch_id','BranchName','SaleDate']).agg(
    sales=('TotalSales','sum'), cost=('TotalCost','sum'), profit=('TotalProfit','sum')
).reset_index()
daily26['invoices'] = 0
daily26['Month'] = daily26['SaleDate'].dt.strftime('%Y-%m')

all_daily = pd.concat([daily25, daily26], ignore_index=True)

# ملخص شهري
monthly25 = df25.groupby(['branch_id','Month','BranchName']).agg(
    sales=('TotalSales','sum'), cost=('TotalCost','sum'),
    profit=('TotalProfit','sum'), invoices=('InvoiceID','nunique')
).reset_index()

branches = sorted(all_daily['branch_id'].unique())
min_date = all_daily['SaleDate'].min().strftime('%Y-%m-%d')
max_date = all_daily['SaleDate'].max().strftime('%Y-%m-%d')

@app.route('/')
def dashboard():
    branch_filter = request.args.get('branch', 'all')
    date_from = request.args.get('date_from', min_date)
    date_to = request.args.get('date_to', max_date)

    filtered = all_daily.copy()
    filtered = filtered[(filtered['SaleDate'] >= date_from) & (filtered['SaleDate'] <= date_to)]
    if branch_filter != 'all':
        filtered = filtered[filtered['branch_id'] == branch_filter]

    total_sales = filtered['sales'].sum()
    total_cost = filtered['cost'].sum()
    total_profit = filtered['profit'].sum()
    total_invoices = filtered['invoices'].sum()
    profit_pct = (total_profit / total_sales * 100) if total_sales > 0 else 0

    branch_summary = filtered.groupby(['branch_id','BranchName']).agg(
        sales=('sales','sum'), cost=('cost','sum'), profit=('profit','sum')
    ).reset_index()
    branch_summary['profit_pct'] = (branch_summary['profit'] / branch_summary['sales'] * 100).round(1)

    # مخطط الفروع
    fig = go.Figure()
    fig.add_trace(go.Bar(name='المبيعات', x=branch_summary['BranchName'], y=branch_summary['sales'],
        marker_color='#3498db', text=branch_summary['sales'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.add_trace(go.Bar(name='الأرباح', x=branch_summary['BranchName'], y=branch_summary['profit'],
        marker_color='#2ecc71', text=branch_summary['profit'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.update_layout(title='مقارنة المبيعات والأرباح بين الفروع', barmode='group',
        font=dict(family='Arial'), dragmode=False, hovermode=False, margin=dict(t=60,b=40))
    graph1 = fig.to_html(full_html=False, config={'staticPlot': True, 'displayModeBar': False})

    # مخطط يومي
    daily_agg = filtered.groupby('SaleDate').agg(sales=('sales','sum'), profit=('profit','sum')).reset_index()
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(name='المبيعات', x=daily_agg['SaleDate'], y=daily_agg['sales'], marker_color='#3498db'))
    fig2.add_trace(go.Bar(name='الأرباح', x=daily_agg['SaleDate'], y=daily_agg['profit'], marker_color='#2ecc71'))
    fig2.update_layout(title='المبيعات اليومية', barmode='group',
        font=dict(family='Arial'), dragmode=False, hovermode=False, margin=dict(t=60,b=40))
    graph2 = fig2.to_html(full_html=False, config={'staticPlot': True, 'displayModeBar': False})

    if not branch_summary.empty:
        b1 = branch_summary.loc[branch_summary['sales'].idxmax()]
        b2 = branch_summary.loc[branch_summary['profit'].idxmax()]
        b3 = branch_summary.loc[branch_summary['profit_pct'].idxmax()]
        analysis_html = f'''<div class="analysis">
            <div class="ac"><div class="ai">🏆</div><div class="at"><strong>أعلى مبيعات</strong><span class="ab">{b1["BranchName"]}</span><span class="av">{b1["sales"]:,.0f} ريال</span></div></div>
            <div class="ac"><div class="ai">💰</div><div class="at"><strong>أعلى أرباح</strong><span class="ab">{b2["BranchName"]}</span><span class="av">{b2["profit"]:,.0f} ريال</span></div></div>
            <div class="ac"><div class="ai">📊</div><div class="at"><strong>أعلى نسبة ربح</strong><span class="ab">{b3["BranchName"]}</span><span class="av">{b3["profit_pct"]}%</span></div></div>
        </div>'''
    else:
        analysis_html = ''

    branch_opts = '<option value="all">كل الفروع</option>' + ''.join([f'<option value="{b}" {"selected" if branch_filter==b else ""}>فرع {b}</option>' for b in branches])

    return f'''<!DOCTYPE html><html dir="rtl"><head><title>داشبورد محلات الكفرات</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        *{{box-sizing:border-box}}body{{font-family:Arial;margin:0;padding:15px;background:#f0f2f5}}
        h1{{color:#2c3e50;text-align:center;margin-bottom:10px;font-size:22px}}
        .nav{{display:flex;gap:8px;justify-content:center;margin-bottom:15px;flex-wrap:wrap}}
        .nav a{{padding:9px 18px;border-radius:6px;text-decoration:none;font-weight:bold;color:white;font-size:14px}}
        .bc{{background:#8e44ad}}.ba{{background:#e74c3c}}.bp{{background:#e67e22}}
        .filters{{background:white;padding:12px;border-radius:10px;margin-bottom:15px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
        .filters label{{font-weight:bold;font-size:14px;color:#2c3e50}}
        .filters select,.filters input{{padding:7px;border-radius:5px;border:1px solid #ccc;font-size:14px}}
        .filters button{{padding:7px 18px;background:#3498db;color:white;border:none;border-radius:5px;cursor:pointer;font-weight:bold}}
        .kpi{{display:flex;gap:8px;margin-bottom:15px;flex-wrap:wrap}}
        .kpi-card{{background:white;padding:15px;border-radius:10px;text-align:center;flex:1;min-width:120px;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
        .kv{{font-size:22px;font-weight:bold;color:#3498db}}.kv.g{{color:#2ecc71}}.kv.o{{color:#e67e22}}
        .kl{{color:#7f8c8d;font-size:12px;margin-top:4px}}
        .chart{{background:white;border-radius:10px;padding:12px;margin-bottom:15px;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
        .analysis{{display:flex;gap:10px;margin-bottom:15px;flex-wrap:wrap}}
        .ac{{background:white;border-radius:10px;padding:15px;flex:1;min-width:170px;box-shadow:0 2px 5px rgba(0,0,0,.1);display:flex;align-items:center;gap:12px}}
        .ai{{font-size:30px}}.at{{display:flex;flex-direction:column;gap:3px;font-size:14px}}
        .ab{{color:#2c3e50;font-size:15px;font-weight:bold}}.av{{color:#3498db;font-size:15px;font-weight:bold}}
    </style></head><body>
    <h1>🏪 داشبورد محلات الكفرات</h1>
    <div class="nav">
        <a href="/compare" class="bc">🔄 مقارنة الفترات</a>
        <a href="/alerts" class="ba">⚠️ التنبيهات</a>
        <a href="/predictions" class="bp">🔮 التوقعات</a>
    </div>
    <div class="filters">
        <form method="get" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
            <div><label>الفرع: </label><select name="branch">{branch_opts}</select></div>
            <div><label>من: </label><input type="date" name="date_from" value="{date_from}"></div>
            <div><label>إلى: </label><input type="date" name="date_to" value="{date_to}"></div>
            <button type="submit">تطبيق</button>
        </form>
    </div>
    <div class="kpi">
        <div class="kpi-card"><div class="kv">{total_invoices:,.0f}</div><div class="kl">عدد الفواتير</div></div>
        <div class="kpi-card"><div class="kv">{total_sales:,.0f}</div><div class="kl">إجمالي المبيعات</div></div>
        <div class="kpi-card"><div class="kv">{total_cost:,.0f}</div><div class="kl">إجمالي التكلفة</div></div>
        <div class="kpi-card"><div class="kv g">{total_profit:,.0f}</div><div class="kl">إجمالي الربح</div></div>
        <div class="kpi-card"><div class="kv o">{profit_pct:.1f}%</div><div class="kl">نسبة الربح</div></div>
    </div>
    {analysis_html}
    <div class="chart">{graph1}</div>
    <div class="chart">{graph2}</div>
    </body></html>'''

@app.route('/compare')
def compare():
    date_from1 = request.args.get('date_from1', '2026-01-01')
    date_to1 = request.args.get('date_to1', '2026-01-31')
    date_from2 = request.args.get('date_from2', '2026-02-01')
    date_to2 = request.args.get('date_to2', max_date)

    p1 = all_daily[(all_daily['SaleDate']>=date_from1)&(all_daily['SaleDate']<=date_to1)].groupby('branch_id').agg(sales=('sales','sum'),profit=('profit','sum')).reset_index()
    p2 = all_daily[(all_daily['SaleDate']>=date_from2)&(all_daily['SaleDate']<=date_to2)].groupby('branch_id').agg(sales=('sales','sum'),profit=('profit','sum')).reset_index()
    merged = p1.merge(p2, on='branch_id', suffixes=('_p1','_p2'))
    merged['cs'] = ((merged['sales_p2']-merged['sales_p1'])/merged['sales_p1']*100).round(1)
    merged['cp'] = ((merged['profit_p2']-merged['profit_p1'])/merged['profit_p1']*100).round(1)
    merged['BranchName'] = 'فرع ' + merged['branch_id']

    fig = go.Figure()
    fig.add_trace(go.Bar(name=f'{date_from1}:{date_to1}', x=merged['BranchName'], y=merged['sales_p1'],
        marker_color='#3498db', text=merged['sales_p1'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.add_trace(go.Bar(name=f'{date_from2}:{date_to2}', x=merged['BranchName'], y=merged['sales_p2'],
        marker_color='#e67e22', text=merged['sales_p2'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.update_layout(title='مقارنة المبيعات بين فترتين', barmode='group',
        font=dict(family='Arial'), dragmode=False, hovermode=False, margin=dict(t=60))
    graph_html = fig.to_html(full_html=False, config={'staticPlot':True,'displayModeBar':False})

    rows = ''
    for _, row in merged.iterrows():
        sc = '#2ecc71' if row['cs']>=0 else '#e74c3c'
        pc = '#2ecc71' if row['cp']>=0 else '#e74c3c'
        rows += f'<tr><td>فرع {row["branch_id"]}</td><td>{row["sales_p1"]:,.0f}</td><td>{row["sales_p2"]:,.0f}</td><td style="color:{sc};font-weight:bold;">{"↑" if row["cs"]>=0 else "↓"} {abs(row["cs"])}%</td><td>{row["profit_p1"]:,.0f}</td><td>{row["profit_p2"]:,.0f}</td><td style="color:{pc};font-weight:bold;">{"↑" if row["cp"]>=0 else "↓"} {abs(row["cp"])}%</td></tr>'

    return f'''<!DOCTYPE html><html dir="rtl"><head><title>مقارنة الفترات</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{{font-family:Arial;margin:0;padding:15px;background:#f0f2f5}}h1{{color:#2c3e50;text-align:center}}
    .nav{{text-align:center;margin:12px 0}}.nav a{{background:#3498db;color:white;padding:9px 18px;border-radius:6px;text-decoration:none;font-weight:bold}}
    .filters{{background:white;padding:12px;border-radius:10px;margin:12px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    .filters label{{font-weight:bold;color:#2c3e50}}.filters input{{padding:7px;border-radius:5px;border:1px solid #ccc}}
    .filters button{{padding:7px 18px;background:#8e44ad;color:white;border:none;border-radius:5px;cursor:pointer;font-weight:bold}}
    .sep{{font-weight:bold;color:#7f8c8d;padding:0 5px}}
    .chart{{background:white;border-radius:10px;padding:12px;margin-bottom:12px;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    table{{width:100%;border-collapse:collapse;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    th{{background:#2c3e50;color:white;padding:10px;text-align:center;font-size:13px}}td{{padding:10px;text-align:center;border-bottom:1px solid #eee;font-size:13px}}</style></head><body>
    <h1>🔄 مقارنة الفترات</h1>
    <div class="nav"><a href="/">← العودة</a></div>
    <div class="filters"><form method="get" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <strong>الفترة الأولى:</strong>
        <label>من</label><input type="date" name="date_from1" value="{date_from1}">
        <label>إلى</label><input type="date" name="date_to1" value="{date_to1}">
        <span class="sep">|</span>
        <strong>الفترة الثانية:</strong>
        <label>من</label><input type="date" name="date_from2" value="{date_from2}">
        <label>إلى</label><input type="date" name="date_to2" value="{date_to2}">
        <button type="submit">مقارنة</button>
    </form></div>
    <div class="chart">{graph_html}</div>
    <table><tr><th>الفرع</th><th>مبيعات الفترة 1</th><th>مبيعات الفترة 2</th><th>تغيير المبيعات</th><th>ربح الفترة 1</th><th>ربح الفترة 2</th><th>تغيير الربح</th></tr>{rows}</table>
    </body></html>'''

@app.route('/alerts')
def alerts():
    last7_to = max_date
    last7_from = (pd.to_datetime(max_date) - pd.Timedelta(days=6)).strftime('%Y-%m-%d')
    prev7_to = (pd.to_datetime(last7_from) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    prev7_from = (pd.to_datetime(prev7_to) - pd.Timedelta(days=6)).strftime('%Y-%m-%d')

    last = all_daily[(all_daily['SaleDate']>=last7_from)&(all_daily['SaleDate']<=last7_to)].groupby('branch_id').agg(sales=('sales','sum'),profit=('profit','sum')).reset_index()
    prev = all_daily[(all_daily['SaleDate']>=prev7_from)&(all_daily['SaleDate']<=prev7_to)].groupby('branch_id').agg(sales=('sales','sum'),profit=('profit','sum')).reset_index()
    merged = last.merge(prev, on='branch_id', suffixes=('_l','_p'), how='left')
    merged['pp'] = (merged['profit_l']/merged['sales_l']*100).round(1)
    merged['sc'] = ((merged['sales_l']-merged['sales_p'])/merged['sales_p']*100).round(1)
    merged['pc'] = ((merged['profit_l']-merged['profit_p'])/merged['profit_p']*100).round(1)

    alerts_html = ''
    for _, row in merged.iterrows():
        bn = f'فرع {row["branch_id"]}'
        if row['sc'] < -20:
            alerts_html += f'<div class="alert red">🔴 <strong>{bn}</strong> — انخفضت المبيعات بنسبة <strong>{abs(row["sc"])}%</strong> مقارنة بالأسبوع السابق</div>'
        elif row['sc'] < 0:
            alerts_html += f'<div class="alert orange">🟡 <strong>{bn}</strong> — انخفضت المبيعات بنسبة <strong>{abs(row["sc"])}%</strong> مقارنة بالأسبوع السابق</div>'
        if row['pc'] < -20:
            alerts_html += f'<div class="alert red">🔴 <strong>{bn}</strong> — انخفض الربح بنسبة <strong>{abs(row["pc"])}%</strong> مقارنة بالأسبوع السابق</div>'
        if row['pp'] < 10:
            alerts_html += f'<div class="alert red">🔴 <strong>{bn}</strong> — نسبة الربح منخفضة جداً: <strong>{row["pp"]}%</strong></div>'
        elif row['pp'] < 20:
            alerts_html += f'<div class="alert orange">🟡 <strong>{bn}</strong> — نسبة الربح أقل من المعتاد: <strong>{row["pp"]}%</strong></div>'
    if not alerts_html:
        alerts_html = '<div class="alert green">✅ لا توجد تنبيهات — كل الفروع تعمل بشكل طبيعي</div>'

    return f'''<!DOCTYPE html><html dir="rtl"><head><title>التنبيهات</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{{font-family:Arial;margin:0;padding:15px;background:#f0f2f5}}h1{{color:#2c3e50;text-align:center}}
    .subtitle{{text-align:center;color:#7f8c8d;margin-bottom:15px}}
    .nav{{text-align:center;margin:12px 0}}.nav a{{background:#3498db;color:white;padding:9px 18px;border-radius:6px;text-decoration:none;font-weight:bold}}
    .alert{{padding:14px 18px;border-radius:10px;margin-bottom:10px;font-size:15px;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    .alert.red{{background:#fdf0f0;border-right:5px solid #e74c3c}}
    .alert.orange{{background:#fef9e7;border-right:5px solid #f39c12}}
    .alert.green{{background:#eafaf1;border-right:5px solid #2ecc71;color:#27ae60;font-weight:bold}}</style></head><body>
    <h1>⚠️ التنبيهات</h1>
    <div class="subtitle">آخر 7 أيام ({last7_from} إلى {last7_to}) مقابل الأسبوع السابق</div>
    <div class="nav"><a href="/">← العودة</a></div><br>{alerts_html}</body></html>'''

@app.route('/predictions')
def predictions():
    avg25 = monthly25.groupby('branch_id').agg(avg_sales=('sales','mean'),avg_profit=('profit','mean')).reset_index()
    avg25['avg_profit_pct'] = (avg25['avg_profit']/avg25['avg_sales']*100).round(1)
    avg25['avg_weekly'] = (avg25['avg_sales']/4).round(0)
    last7_from = (pd.to_datetime(max_date) - pd.Timedelta(days=6)).strftime('%Y-%m-%d')
    last_data = all_daily[all_daily['SaleDate']>=last7_from].groupby('branch_id').agg(last_sales=('sales','sum')).reset_index()
    fc = avg25.merge(last_data, on='branch_id', how='left')
    fc['last_sales'] = fc['last_sales'].fillna(0)
    fc['trend'] = ((fc['last_sales']-fc['avg_weekly'])/fc['avg_weekly']*100).round(1)
    best = fc.loc[fc['avg_sales'].idxmax(),'branch_id']
    rows = ''
    for _, row in fc.iterrows():
        tc = '#2ecc71' if row['trend']>=0 else '#e74c3c'
        rows += f'<tr><td>فرع {row["branch_id"]}</td><td>{row["avg_sales"]:,.0f}</td><td>{row["avg_profit"]:,.0f}</td><td>{row["avg_profit_pct"]}%</td><td>{row["avg_weekly"]:,.0f}</td><td>{row["last_sales"]:,.0f}</td><td style="color:{tc};font-weight:bold;">{"↑" if row["trend"]>=0 else "↓"} {abs(row["trend"])}%</td></tr>'
    return f'''<!DOCTYPE html><html dir="rtl"><head><title>التوقعات</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{{font-family:Arial;margin:0;padding:15px;background:#f0f2f5}}h1{{color:#2c3e50;text-align:center}}
    .nav{{text-align:center;margin:12px 0}}.nav a{{background:#3498db;color:white;padding:9px 18px;border-radius:6px;text-decoration:none;font-weight:bold}}
    .st{{font-size:17px;font-weight:bold;color:#2c3e50;margin:18px 0 10px;border-right:4px solid #e67e22;padding-right:10px}}
    .hl{{background:white;border-radius:10px;padding:15px;margin-bottom:15px;box-shadow:0 2px 5px rgba(0,0,0,.1);font-size:16px;border-right:5px solid #e67e22}}
    .note{{color:#7f8c8d;font-size:12px;margin-top:12px;text-align:center}}
    table{{width:100%;border-collapse:collapse;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    th{{background:#2c3e50;color:white;padding:10px;text-align:center;font-size:13px}}td{{padding:10px;text-align:center;border-bottom:1px solid #eee;font-size:13px}}</style></head><body>
    <h1>🔮 التوقعات</h1>
    <div class="nav"><a href="/">← العودة</a></div>
    <div class="st">الفرع المتوقع الأعلى مبيعات</div>
    <div class="hl">🏆 بناءً على أداء 2025 — الفرع المتوقع: <strong>فرع {best}</strong></div>
    <div class="st">توقعات المبيعات لكل فرع</div>
    <table><tr><th>الفرع</th><th>متوسط المبيعات (2025)</th><th>متوسط الربح (2025)</th><th>نسبة الربح</th><th>توقع الأسبوع</th><th>مبيعات آخر 7 أيام</th><th>الاتجاه</th></tr>{rows}</table>
    <p class="note">* التوقعات مبنية على متوسط أداء 2025</p>
    </body></html>'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
