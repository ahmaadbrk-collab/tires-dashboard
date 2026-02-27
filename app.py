from flask import Flask, request
import pandas as pd
import plotly.graph_objects as go
import os

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_2025():
    df = pd.read_csv(os.path.join(BASE_DIR, '2025_TIRE.csv'), sep=';', header=None)
    df.columns = ['SaleDate','SaleMonth','SaleYear','BranchName','BranchID','InvoiceID','TotalSales','TotalCost','TotalProfit','ItemCount']
    df['SaleDate'] = pd.to_datetime(df['SaleDate'])
    df['TotalSales'] = pd.to_numeric(df['TotalSales'], errors='coerce').fillna(0)
    df['TotalCost'] = pd.to_numeric(df['TotalCost'], errors='coerce').fillna(0)
    df['TotalProfit'] = pd.to_numeric(df['TotalProfit'], errors='coerce').fillna(0)
    df['Month'] = df['SaleDate'].dt.strftime('%Y-%m')
    df['branch_id'] = df['BranchName'].str.extract(r'(\d+)')
    return df

def load_profit_file(path, branch, month):
    df = pd.read_excel(os.path.join(BASE_DIR, path), header=1)
    df.columns = range(len(df.columns))
    totals = df[df[0].astype(str).str.contains('مبيعات فرع', na=False)]
    if totals.empty:
        return None
    row = totals.iloc[0]
    sales = pd.to_numeric(row[2], errors='coerce') or 0
    cost = pd.to_numeric(row[3], errors='coerce') or 0
    profit = pd.to_numeric(row[4], errors='coerce') or 0
    return {'branch_id': branch, 'Month': month, 'TotalSales': sales, 'TotalCost': cost, 'TotalProfit': profit}

def load_2026():
    files = [
        ('1_1.xlsx','1','2026-01'), ('1_2.xlsx','1','2026-02'),
        ('2_1.xlsx','2','2026-01'), ('2_2.xlsx','2','2026-02'),
        ('3_1.xlsx','3','2026-01'), ('3_2.xlsx','3','2026-02'),
        ('4_1.xlsx','4','2026-01'), ('4_2.xlsx','4','2026-02'),
    ]
    rows = [load_profit_file(p,b,m) for p,b,m in files]
    rows = [r for r in rows if r]
    df = pd.DataFrame(rows)
    df['SaleDate'] = pd.to_datetime(df['Month'] + '-01')
    df['BranchName'] = 'فرع ' + df['branch_id']
    return df

df25 = load_2025()
df26 = load_2026()

monthly25 = df25.groupby(['branch_id','Month','BranchName']).agg(
    sales=('TotalSales','sum'), cost=('TotalCost','sum'),
    profit=('TotalProfit','sum'), invoices=('InvoiceID','nunique')
).reset_index()

monthly26 = df26.rename(columns={'TotalSales':'sales','TotalCost':'cost','TotalProfit':'profit'})
monthly26['invoices'] = 0

all_monthly = pd.concat([
    monthly25[['branch_id','BranchName','Month','sales','cost','profit','invoices']],
    monthly26[['branch_id','BranchName','Month','sales','cost','profit','invoices']]
], ignore_index=True)

all_months = sorted(all_monthly['Month'].unique())
branches = sorted(all_monthly['branch_id'].unique())

@app.route('/')
def dashboard():
    branch_filter = request.args.get('branch', 'all')
    month_filter = request.args.get('month', 'all')

    filtered = all_monthly.copy()
    if branch_filter != 'all':
        filtered = filtered[filtered['branch_id'] == branch_filter]
    if month_filter != 'all':
        filtered = filtered[filtered['Month'] == month_filter]

    total_sales = filtered['sales'].sum()
    total_cost = filtered['cost'].sum()
    total_profit = filtered['profit'].sum()
    total_invoices = filtered['invoices'].sum()
    profit_pct = (total_profit / total_sales * 100) if total_sales > 0 else 0

    branch_summary = filtered.groupby(['branch_id','BranchName']).agg(
        sales=('sales','sum'), cost=('cost','sum'), profit=('profit','sum')
    ).reset_index()
    branch_summary['profit_pct'] = (branch_summary['profit'] / branch_summary['sales'] * 100).round(1)

    fig = go.Figure()
    fig.add_trace(go.Bar(name='المبيعات', x=branch_summary['BranchName'], y=branch_summary['sales'],
        marker_color='#3498db', text=branch_summary['sales'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.add_trace(go.Bar(name='الأرباح', x=branch_summary['BranchName'], y=branch_summary['profit'],
        marker_color='#2ecc71', text=branch_summary['profit'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.update_layout(title='مقارنة المبيعات والأرباح بين الفروع', barmode='group',
        font=dict(family='Arial'), dragmode=False, hovermode=False, margin=dict(t=60,b=40))
    graph_html = fig.to_html(full_html=False, config={'staticPlot': True, 'displayModeBar': False})

    monthly_total = filtered.groupby('Month').agg(sales=('sales','sum'), profit=('profit','sum')).reset_index()
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(name='المبيعات', x=monthly_total['Month'], y=monthly_total['sales'], marker_color='#3498db'))
    fig2.add_trace(go.Bar(name='الأرباح', x=monthly_total['Month'], y=monthly_total['profit'], marker_color='#2ecc71'))
    fig2.update_layout(title='المبيعات والأرباح الشهرية', barmode='group',
        font=dict(family='Arial'), dragmode=False, hovermode=False, margin=dict(t=60,b=40))
    graph2_html = fig2.to_html(full_html=False, config={'staticPlot': True, 'displayModeBar': False})

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
    month_opts = '<option value="all">كل الأشهر</option>' + ''.join([f'<option value="{m}" {"selected" if month_filter==m else ""}>{m}</option>' for m in all_months])

    return f'''<!DOCTYPE html><html dir="rtl"><head><title>داشبورد محلات الكفرات</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        *{{box-sizing:border-box}}body{{font-family:Arial;margin:0;padding:15px;background:#f0f2f5}}
        h1{{color:#2c3e50;text-align:center;margin-bottom:10px;font-size:22px}}
        .nav{{display:flex;gap:8px;justify-content:center;margin-bottom:15px;flex-wrap:wrap}}
        .nav a{{padding:9px 18px;border-radius:6px;text-decoration:none;font-weight:bold;color:white;font-size:14px}}
        .bc{{background:#8e44ad}}.ba{{background:#e74c3c}}.bp{{background:#e67e22}}
        .filters{{background:white;padding:12px;border-radius:10px;margin-bottom:15px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
        .filters label{{font-weight:bold;font-size:14px}}.filters select{{padding:7px;border-radius:5px;border:1px solid #ccc;font-size:14px}}
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
    <div class="filters"><form method="get" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <div><label>الفرع: </label><select name="branch">{branch_opts}</select></div>
        <div><label>الشهر: </label><select name="month">{month_opts}</select></div>
        <button type="submit">تطبيق</button>
    </form></div>
    <div class="kpi">
        <div class="kpi-card"><div class="kv">{total_invoices:,.0f}</div><div class="kl">عدد الفواتير</div></div>
        <div class="kpi-card"><div class="kv">{total_sales:,.0f}</div><div class="kl">إجمالي المبيعات</div></div>
        <div class="kpi-card"><div class="kv">{total_cost:,.0f}</div><div class="kl">إجمالي التكلفة</div></div>
        <div class="kpi-card"><div class="kv g">{total_profit:,.0f}</div><div class="kl">إجمالي الربح</div></div>
        <div class="kpi-card"><div class="kv o">{profit_pct:.1f}%</div><div class="kl">نسبة الربح</div></div>
    </div>
    {analysis_html}
    <div class="chart">{graph_html}</div>
    <div class="chart">{graph2_html}</div>
    </body></html>'''

@app.route('/compare')
def compare():
    period1 = request.args.get('period1', all_months[-2] if len(all_months) >= 2 else all_months[0])
    period2 = request.args.get('period2', all_months[-1])
    p1 = all_monthly[all_monthly['Month']==period1].groupby('branch_id').agg(sales=('sales','sum'),profit=('profit','sum')).reset_index()
    p2 = all_monthly[all_monthly['Month']==period2].groupby('branch_id').agg(sales=('sales','sum'),profit=('profit','sum')).reset_index()
    merged = p1.merge(p2, on='branch_id', suffixes=('_p1','_p2'))
    merged['cs'] = ((merged['sales_p2']-merged['sales_p1'])/merged['sales_p1']*100).round(1)
    merged['cp'] = ((merged['profit_p2']-merged['profit_p1'])/merged['profit_p1']*100).round(1)
    merged['BranchName'] = 'فرع ' + merged['branch_id']
    fig = go.Figure()
    fig.add_trace(go.Bar(name=period1, x=merged['BranchName'], y=merged['sales_p1'],
        marker_color='#3498db', text=merged['sales_p1'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.add_trace(go.Bar(name=period2, x=merged['BranchName'], y=merged['sales_p2'],
        marker_color='#e67e22', text=merged['sales_p2'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.update_layout(title=f'مقارنة: {period1} مقابل {period2}', barmode='group',
        font=dict(family='Arial'), dragmode=False, hovermode=False, margin=dict(t=60))
    graph_html = fig.to_html(full_html=False, config={'staticPlot':True,'displayModeBar':False})
    rows = ''
    for _, row in merged.iterrows():
        sc = '#2ecc71' if row['cs']>=0 else '#e74c3c'
        pc = '#2ecc71' if row['cp']>=0 else '#e74c3c'
        rows += f'<tr><td>فرع {row["branch_id"]}</td><td>{row["sales_p1"]:,.0f}</td><td>{row["sales_p2"]:,.0f}</td><td style="color:{sc};font-weight:bold;">{"↑" if row["cs"]>=0 else "↓"} {abs(row["cs"])}%</td><td>{row["profit_p1"]:,.0f}</td><td>{row["profit_p2"]:,.0f}</td><td style="color:{pc};font-weight:bold;">{"↑" if row["cp"]>=0 else "↓"} {abs(row["cp"])}%</td></tr>'
    o1 = ''.join([f'<option value="{m}" {"selected" if m==period1 else ""}>{m}</option>' for m in all_months])
    o2 = ''.join([f'<option value="{m}" {"selected" if m==period2 else ""}>{m}</option>' for m in all_months])
    return f'''<!DOCTYPE html><html dir="rtl"><head><title>مقارنة الفترات</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{{font-family:Arial;margin:0;padding:15px;background:#f0f2f5}}h1{{color:#2c3e50;text-align:center}}
    .nav{{text-align:center;margin:12px 0}}.nav a{{background:#3498db;color:white;padding:9px 18px;border-radius:6px;text-decoration:none;font-weight:bold}}
    .filters{{background:white;padding:12px;border-radius:10px;margin:12px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    .filters label{{font-weight:bold}}.filters select{{padding:7px;border-radius:5px;border:1px solid #ccc}}
    .filters button{{padding:7px 18px;background:#8e44ad;color:white;border:none;border-radius:5px;cursor:pointer;font-weight:bold}}
    .chart{{background:white;border-radius:10px;padding:12px;margin-bottom:12px;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    table{{width:100%;border-collapse:collapse;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    th{{background:#2c3e50;color:white;padding:10px;text-align:center;font-size:13px}}td{{padding:10px;text-align:center;border-bottom:1px solid #eee;font-size:13px}}</style></head><body>
    <h1>🔄 مقارنة الفترات</h1>
    <div class="nav"><a href="/">← العودة</a></div>
    <div class="filters"><form method="get" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <div><label>الفترة الأولى: </label><select name="period1">{o1}</select></div>
        <div><label>الفترة الثانية: </label><select name="period2">{o2}</select></div>
        <button type="submit">مقارنة</button>
    </form></div>
    <div class="chart">{graph_html}</div>
    <table><tr><th>الفرع</th><th>مبيعات {period1}</th><th>مبيعات {period2}</th><th>تغيير المبيعات</th><th>ربح {period1}</th><th>ربح {period2}</th><th>تغيير الربح</th></tr>{rows}</table>
    </body></html>'''

@app.route('/alerts')
def alerts():
    last_month = all_months[-1]
    prev_month = all_months[-2] if len(all_months)>=2 else all_months[-1]
    last = all_monthly[all_monthly['Month']==last_month].groupby('branch_id').agg(sales=('sales','sum'),profit=('profit','sum')).reset_index()
    prev = all_monthly[all_monthly['Month']==prev_month].groupby('branch_id').agg(sales=('sales','sum'),profit=('profit','sum')).reset_index()
    merged = last.merge(prev, on='branch_id', suffixes=('_l','_p'), how='left')
    merged['pp'] = (merged['profit_l']/merged['sales_l']*100).round(1)
    merged['sc'] = ((merged['sales_l']-merged['sales_p'])/merged['sales_p']*100).round(1)
    merged['pc'] = ((merged['profit_l']-merged['profit_p'])/merged['profit_p']*100).round(1)
    alerts_html = ''
    for _, row in merged.iterrows():
        bn = f'فرع {row["branch_id"]}'
        if row['sc'] < -20:
            alerts_html += f'<div class="alert red">🔴 <strong>{bn}</strong> — انخفضت المبيعات بنسبة <strong>{abs(row["sc"])}%</strong> مقارنة بـ {prev_month}</div>'
        elif row['sc'] < 0:
            alerts_html += f'<div class="alert orange">🟡 <strong>{bn}</strong> — انخفضت المبيعات بنسبة <strong>{abs(row["sc"])}%</strong> مقارنة بـ {prev_month}</div>'
        if row['pc'] < -20:
            alerts_html += f'<div class="alert red">🔴 <strong>{bn}</strong> — انخفض الربح بنسبة <strong>{abs(row["pc"])}%</strong> مقارنة بـ {prev_month}</div>'
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
    <div class="subtitle">مقارنة {last_month} بـ {prev_month}</div>
    <div class="nav"><a href="/">← العودة</a></div><br>{alerts_html}</body></html>'''

@app.route('/predictions')
def predictions():
    avg25 = monthly25.groupby('branch_id').agg(avg_sales=('sales','mean'),avg_profit=('profit','mean')).reset_index()
    avg25['avg_profit_pct'] = (avg25['avg_profit']/avg25['avg_sales']*100).round(1)
    avg25['avg_weekly'] = (avg25['avg_sales']/4).round(0)
    last_month = all_months[-1]
    last_data = all_monthly[all_monthly['Month']==last_month].groupby('branch_id').agg(last_sales=('sales','sum'),last_profit=('profit','sum')).reset_index()
    fc = avg25.merge(last_data, on='branch_id', how='left')
    fc['last_sales'] = fc['last_sales'].fillna(0)
    fc['trend'] = ((fc['last_sales']-fc['avg_sales'])/fc['avg_sales']*100).round(1)
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
    <table><tr><th>الفرع</th><th>متوسط المبيعات (2025)</th><th>متوسط الربح (2025)</th><th>نسبة الربح</th><th>توقع الأسبوع</th><th>آخر شهر ({last_month})</th><th>الاتجاه</th></tr>{rows}</table>
    <p class="note">* التوقعات مبنية على متوسط أداء 2025</p>
    </body></html>'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
