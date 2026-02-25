from flask import Flask, request
import pandas as pd
import plotly.graph_objects as go

app = Flask(__name__)

# ==============================
# تحميل البيانات
# ==============================
def load_file(path):
    df = pd.read_excel(path, header=1)
    df.columns = ['الرقم','التاريخ','فواتير','قيمة_الفاتورة','الزبون','طريقة_الدفع','المادة','الكمية','الإفرادي','المجموع','وقت_التحرير','تاريخ_التحرير','رصيد_المادة','المستودع','الفرع','ملاحظة','col17','آخر_شراء','سعر_التكلفة']
    df = df[df['التاريخ'].notna()]
    df = df[df['التاريخ'] != 'التاريخ']
    df['التاريخ'] = pd.to_datetime(df['التاريخ'], errors='coerce')
    df = df[df['التاريخ'].dt.year >= 2024]
    df['المجموع'] = pd.to_numeric(df['المجموع'], errors='coerce').fillna(0)
    df['الكمية'] = pd.to_numeric(df['الكمية'], errors='coerce').fillna(0)
    df['سعر_التكلفة'] = pd.to_numeric(df['سعر_التكلفة'], errors='coerce').fillna(0)
    df['تكلفة_السطر'] = df['الكمية'] * df['سعر_التكلفة']
    df['branch_id'] = df['المستودع'].astype(str).str.extract(r'(\d+)')[0]
    return df

def build_invoices(df):
    inv_id = 0
    ids = []
    for v in df['فواتير']:
        if pd.notna(v) and str(v).strip() != '':
            inv_id += 1
        ids.append(inv_id)
    df = df.copy()
    df['inv_id'] = ids
    inv = df.groupby(['inv_id','branch_id'], as_index=False).agg(
        date=('التاريخ','first'),
        sales=('المجموع','sum'),
        cost=('تكلفة_السطر','sum')
    )
    inv['profit'] = inv['sales'] - inv['cost']
    inv['month'] = inv['date'].dt.strftime('%Y-%m')
    inv['week'] = inv['date'].dt.to_period('W').astype(str)
    inv['profit_pct'] = (inv['profit'] / inv['sales'] * 100).where(inv['sales'] > 0, 0)
    return inv

df25 = load_file('2025.xlsx')
df26 = load_file('Book100000.xlsx')
inv25 = build_invoices(df25)
inv26 = build_invoices(df26)
all_inv = pd.concat([inv25, inv26], ignore_index=True)

# متوسط أسبوعي لكل فرع من 2025
weekly_avg = inv25.groupby(['branch_id','week'])['sales'].sum().reset_index()
branch_weekly_avg = weekly_avg.groupby('branch_id')['sales'].mean().to_dict()

# قائمة الأشهر المتاحة
all_months = sorted(all_inv['month'].dropna().unique())

# ==============================
# الصفحة الرئيسية
# ==============================
@app.route('/')
def dashboard():
    branch_filter = request.args.get('branch', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    filtered = all_inv.copy()
    if branch_filter != 'all':
        filtered = filtered[filtered['branch_id'] == branch_filter]
    if date_from:
        filtered = filtered[filtered['date'] >= pd.to_datetime(date_from)]
    if date_to:
        filtered = filtered[filtered['date'] <= pd.to_datetime(date_to)]

    total_sales = filtered['sales'].sum()
    total_cost = filtered['cost'].sum()
    total_profit = filtered['profit'].sum()
    total_invoices = filtered['inv_id'].nunique()
    profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0

    # ملخص الفروع
    branch_summary = filtered.groupby('branch_id').agg(
        المبيعات=('sales','sum'),
        الأرباح=('profit','sum')
    ).reset_index()
    branch_summary['اسم الفرع'] = 'فرع ' + branch_summary['branch_id'].astype(str)
    branch_summary['نسبة الربح'] = (branch_summary['الأرباح'] / branch_summary['المبيعات'] * 100).round(1)

    # مخطط الفروع
    fig = go.Figure()
    fig.add_trace(go.Bar(name='المبيعات', x=branch_summary['اسم الفرع'], y=branch_summary['المبيعات'],
        marker_color='#3498db', text=branch_summary['المبيعات'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.add_trace(go.Bar(name='الأرباح', x=branch_summary['اسم الفرع'], y=branch_summary['الأرباح'],
        marker_color='#2ecc71', text=branch_summary['الأرباح'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.update_layout(title='مقارنة المبيعات والأرباح بين الفروع', barmode='group',
        font=dict(family='Arial'), dragmode=False, hovermode=False, margin=dict(t=60))
    graph_html = fig.to_html(full_html=False, config={'staticPlot': True, 'displayModeBar': False})

    # التحليل النصي
    if not branch_summary.empty:
        best_sales = branch_summary.loc[branch_summary['المبيعات'].idxmax(), 'اسم الفرع']
        best_sales_val = branch_summary['المبيعات'].max()
        best_profit = branch_summary.loc[branch_summary['الأرباح'].idxmax(), 'اسم الفرع']
        best_profit_val = branch_summary['الأرباح'].max()
        best_margin = branch_summary.loc[branch_summary['نسبة الربح'].idxmax(), 'اسم الفرع']
        best_margin_val = branch_summary['نسبة الربح'].max()
        analysis_html = f'''
        <div class="analysis">
            <div class="analysis-card"><div class="analysis-icon">🏆</div><div class="analysis-text">
                <strong>أعلى مبيعات</strong><span class="ab">{best_sales}</span><span class="av">{best_sales_val:,.0f} ريال</span></div></div>
            <div class="analysis-card"><div class="analysis-icon">💰</div><div class="analysis-text">
                <strong>أعلى أرباح</strong><span class="ab">{best_profit}</span><span class="av">{best_profit_val:,.0f} ريال</span></div></div>
            <div class="analysis-card"><div class="analysis-icon">📊</div><div class="analysis-text">
                <strong>أعلى نسبة ربح</strong><span class="ab">{best_margin}</span><span class="av">{best_margin_val}%</span></div></div>
        </div>'''
    else:
        analysis_html = ''

    # خيارات الفروع
    branches = sorted(all_inv['branch_id'].dropna().unique())
    branch_options = '<option value="all">كل الفروع</option>'
    for b in branches:
        sel = 'selected' if branch_filter == str(b) else ''
        branch_options += f'<option value="{b}" {sel}>فرع {b}</option>'

    html = f'''<!DOCTYPE html><html dir="rtl"><head><title>داشبورد محلات الكفرات</title>
    <style>
        body{{font-family:Arial;margin:20px;background:#f0f2f5}}
        h1{{color:#2c3e50;text-align:center;margin-bottom:15px}}
        .nav{{text-align:center;margin-bottom:20px;display:flex;gap:10px;justify-content:center}}
        .nav a{{padding:10px 20px;border-radius:5px;text-decoration:none;font-weight:bold;color:white}}
        .btn-compare{{background:#8e44ad}}.btn-alerts{{background:#e74c3c}}.btn-predict{{background:#e67e22}}
        .filters{{background:white;padding:15px 20px;border-radius:10px;margin-bottom:20px;display:flex;gap:15px;align-items:center;flex-wrap:wrap;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}
        .filters label{{font-weight:bold;color:#2c3e50}}
        .filters select,.filters input{{padding:8px;border-radius:5px;border:1px solid #ccc;font-size:14px}}
        .filters button{{padding:8px 25px;background:#3498db;color:white;border:none;border-radius:5px;cursor:pointer;font-size:14px;font-weight:bold}}
        .kpi{{display:flex;justify-content:space-around;margin-bottom:20px;flex-wrap:wrap}}
        .kpi-card{{background:white;padding:20px 30px;border-radius:10px;text-align:center;flex:1;margin:8px;min-width:150px;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}
        .kpi-value{{font-size:28px;font-weight:bold;color:#3498db}}.green{{color:#2ecc71}}
        .kpi-label{{color:#7f8c8d;margin-top:5px}}
        .chart{{background:white;border-radius:10px;padding:15px;margin-bottom:20px;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}
        .analysis{{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap}}
        .analysis-card{{background:white;border-radius:10px;padding:20px;flex:1;min-width:200px;box-shadow:0 2px 5px rgba(0,0,0,0.1);display:flex;align-items:center;gap:15px}}
        .analysis-icon{{font-size:36px}}.analysis-text{{display:flex;flex-direction:column;gap:4px;font-size:15px}}
        .ab{{color:#2c3e50;font-size:18px;font-weight:bold}}.av{{color:#3498db;font-size:18px;font-weight:bold}}
    </style></head><body>
    <h1>داشبورد محلات الكفرات</h1>
    <div class="nav">
        <a href="/compare" class="nav btn-compare">🔄 مقارنة الفترات</a>
        <a href="/alerts" class="nav btn-alerts">⚠️ التنبيهات</a>
        <a href="/predictions" class="nav btn-predict">🔮 التوقعات</a>
    </div>
    <div class="filters"><form method="get" style="display:flex;gap:15px;align-items:center;flex-wrap:wrap;">
        <div><label>الفرع: </label><select name="branch">{branch_options}</select></div>
        <div><label>من: </label><input type="date" name="date_from" value="{date_from}"></div>
        <div><label>إلى: </label><input type="date" name="date_to" value="{date_to}"></div>
        <button type="submit">تطبيق</button>
    </form></div>
    <div class="kpi">
        <div class="kpi-card"><div class="kpi-value">{total_invoices:,}</div><div class="kpi-label">عدد الفواتير</div></div>
        <div class="kpi-card"><div class="kpi-value">{total_sales:,.0f}</div><div class="kpi-label">إجمالي المبيعات</div></div>
        <div class="kpi-card"><div class="kpi-value">{total_cost:,.0f}</div><div class="kpi-label">إجمالي التكلفة</div></div>
        <div class="kpi-card"><div class="kpi-value green">{total_profit:,.0f}</div><div class="kpi-label">إجمالي الربح</div></div>
    </div>
    {analysis_html}
    <div class="chart">{graph_html}</div>
    </body></html>'''
    return html


# ==============================
# صفحة مقارنة الفترات
# ==============================
@app.route('/compare')
def compare():
    period1 = request.args.get('period1', all_months[-2] if len(all_months) >= 2 else all_months[0])
    period2 = request.args.get('period2', all_months[-1])

    p1 = all_inv[all_inv['month'] == period1]
    p2 = all_inv[all_inv['month'] == period2]

    p1_branch = p1.groupby('branch_id').agg(sales=('sales','sum'), profit=('profit','sum')).reset_index()
    p2_branch = p2.groupby('branch_id').agg(sales=('sales','sum'), profit=('profit','sum')).reset_index()

    merged = p1_branch.merge(p2_branch, on='branch_id', suffixes=('_p1','_p2'))
    merged['تغيير_المبيعات'] = ((merged['sales_p2'] - merged['sales_p1']) / merged['sales_p1'] * 100).round(1)
    merged['اسم الفرع'] = 'فرع ' + merged['branch_id'].astype(str)

    fig = go.Figure()
    fig.add_trace(go.Bar(name=period1, x=merged['اسم الفرع'], y=merged['sales_p1'],
        marker_color='#3498db', text=merged['sales_p1'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.add_trace(go.Bar(name=period2, x=merged['اسم الفرع'], y=merged['sales_p2'],
        marker_color='#e67e22', text=merged['sales_p2'].apply(lambda x: f'{x:,.0f}'), textposition='outside'))
    fig.update_layout(title=f'مقارنة المبيعات: {period1} مقابل {period2}', barmode='group',
        font=dict(family='Arial'), dragmode=False, hovermode=False, margin=dict(t=60))
    graph_html = fig.to_html(full_html=False, config={'staticPlot': True, 'displayModeBar': False})

    # جدول نسب التغيير
    rows = ''
    for _, row in merged.iterrows():
        pct = row['تغيير_المبيعات']
        color = '#2ecc71' if pct >= 0 else '#e74c3c'
        arrow = '↑' if pct >= 0 else '↓'
        rows += f'''<tr>
            <td>فرع {row["branch_id"]}</td>
            <td>{row["sales_p1"]:,.0f}</td>
            <td>{row["sales_p2"]:,.0f}</td>
            <td style="color:{color};font-weight:bold;">{arrow} {abs(pct)}%</td>
        </tr>'''

    month_options1 = ''.join([f'<option value="{m}" {"selected" if m==period1 else ""}>{m}</option>' for m in all_months])
    month_options2 = ''.join([f'<option value="{m}" {"selected" if m==period2 else ""}>{m}</option>' for m in all_months])

    html = f'''<!DOCTYPE html><html dir="rtl"><head><title>مقارنة الفترات</title>
    <style>
        body{{font-family:Arial;margin:20px;background:#f0f2f5}}
        h1{{color:#2c3e50;text-align:center}}
        .nav{{text-align:center;margin:15px 0}}
        .nav a{{background:#3498db;color:white;padding:10px 20px;border-radius:5px;text-decoration:none;font-weight:bold}}
        .filters{{background:white;padding:15px 20px;border-radius:10px;margin:20px 0;display:flex;gap:15px;align-items:center;flex-wrap:wrap;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}
        .filters label{{font-weight:bold}}.filters select{{padding:8px;border-radius:5px;border:1px solid #ccc}}
        .filters button{{padding:8px 20px;background:#8e44ad;color:white;border:none;border-radius:5px;cursor:pointer;font-weight:bold}}
        .chart{{background:white;border-radius:10px;padding:15px;margin-bottom:20px;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}
        table{{width:100%;border-collapse:collapse;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}
        th{{background:#2c3e50;color:white;padding:12px;text-align:center}}
        td{{padding:12px;text-align:center;border-bottom:1px solid #eee}}
        tr:hover{{background:#f8f9fa}}
    </style></head><body>
    <h1>🔄 مقارنة الفترات</h1>
    <div class="nav"><a href="/">← العودة للداشبورد</a></div>
    <div class="filters"><form method="get" style="display:flex;gap:15px;align-items:center;flex-wrap:wrap;">
        <div><label>الفترة الأولى: </label><select name="period1">{month_options1}</select></div>
        <div><label>الفترة الثانية: </label><select name="period2">{month_options2}</select></div>
        <button type="submit">مقارنة</button>
    </form></div>
    <div class="chart">{graph_html}</div>
    <table>
        <tr><th>الفرع</th><th>مبيعات {period1}</th><th>مبيعات {period2}</th><th>نسبة التغيير</th></tr>
        {rows}
    </table>
    </body></html>'''
    return html


# ==============================
# صفحة التنبيهات
# ==============================
@app.route('/alerts')
def alerts():
    last_month = all_months[-1]
    prev_month = all_months[-2] if len(all_months) >= 2 else all_months[-1]

    last = all_inv[all_inv['month'] == last_month]
    prev = all_inv[all_inv['month'] == prev_month]

    last_branch = last.groupby('branch_id').agg(sales=('sales','sum'), profit=('profit','sum'), invoices=('inv_id','nunique')).reset_index()
    prev_branch = prev.groupby('branch_id').agg(sales=('sales','sum'), profit=('profit','sum')).reset_index()

    merged = last_branch.merge(prev_branch, on='branch_id', suffixes=('_last','_prev'), how='left')
    merged['profit_pct'] = (merged['profit_last'] / merged['sales_last'] * 100).round(1)
    merged['sales_change'] = ((merged['sales_last'] - merged['sales_prev']) / merged['sales_prev'] * 100).round(1)

    alerts_html = ''
    ok_count = 0

    for _, row in merged.iterrows():
        branch_name = f'فرع {row["branch_id"]}'

        # تنبيه انخفاض المبيعات أكثر من 20%
        if row['sales_change'] < -20:
            alerts_html += f'''<div class="alert red">
                🔴 <strong>{branch_name}</strong> — انخفضت المبيعات بنسبة <strong>{abs(row["sales_change"])}%</strong> مقارنة بالشهر الماضي
            </div>'''
        elif row['sales_change'] < 0:
            alerts_html += f'''<div class="alert orange">
                🟡 <strong>{branch_name}</strong> — انخفضت المبيعات بنسبة <strong>{abs(row["sales_change"])}%</strong> مقارنة بالشهر الماضي
            </div>'''
        else:
            ok_count += 1

        # تنبيه نسبة الربح
        if row['profit_pct'] < 10:
            alerts_html += f'''<div class="alert red">
                🔴 <strong>{branch_name}</strong> — نسبة الربح منخفضة جداً: <strong>{row["profit_pct"]}%</strong>
            </div>'''
        elif row['profit_pct'] < 20:
            alerts_html += f'''<div class="alert orange">
                🟡 <strong>{branch_name}</strong> — نسبة الربح أقل من المعتاد: <strong>{row["profit_pct"]}%</strong>
            </div>'''

    # فواتير خسارة
    loss_invoices = all_inv[all_inv['profit'] < 0]
    if not loss_invoices.empty:
        alerts_html += f'''<div class="alert red">
            🔴 يوجد <strong>{len(loss_invoices)}</strong> فاتورة تكلفتها أعلى من المبيعات (خسارة)
        </div>'''

    if not alerts_html:
        alerts_html = '<div class="alert green">✅ لا توجد تنبيهات — كل الفروع تعمل بشكل طبيعي</div>'

    html = f'''<!DOCTYPE html><html dir="rtl"><head><title>التنبيهات</title>
    <style>
        body{{font-family:Arial;margin:20px;background:#f0f2f5}}
        h1{{color:#2c3e50;text-align:center}}
        .nav{{text-align:center;margin:15px 0}}
        .nav a{{background:#3498db;color:white;padding:10px 20px;border-radius:5px;text-decoration:none;font-weight:bold}}
        .subtitle{{text-align:center;color:#7f8c8d;margin-bottom:20px}}
        .alert{{padding:15px 20px;border-radius:10px;margin-bottom:12px;font-size:16px;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}
        .alert.red{{background:#fdf0f0;border-right:5px solid #e74c3c}}
        .alert.orange{{background:#fef9e7;border-right:5px solid #f39c12}}
        .alert.green{{background:#eafaf1;border-right:5px solid #2ecc71;color:#27ae60;font-weight:bold}}
    </style></head><body>
    <h1>⚠️ التنبيهات</h1>
    <div class="subtitle">مقارنة {last_month} بـ {prev_month}</div>
    <div class="nav"><a href="/">← العودة للداشبورد</a></div>
    <br>
    {alerts_html}
    </body></html>'''
    return html


# ==============================
# صفحة التوقعات
# ==============================
@app.route('/predictions')
def predictions():
    # متوسط شهري لكل فرع من 2025
    branch_monthly_25 = inv25.groupby(['branch_id','month'])['sales'].sum().reset_index()
    branch_avg = branch_monthly_25.groupby('branch_id')['sales'].mean().reset_index()
    branch_avg.columns = ['branch_id','avg_monthly']

    # آخر شهر متوفر
    last_month = all_months[-1]
    last_data = all_inv[all_inv['month'] == last_month]
    last_branch = last_data.groupby('branch_id')['sales'].sum().reset_index()
    last_branch.columns = ['branch_id','last_sales']

    forecast = branch_avg.merge(last_branch, on='branch_id', how='left')
    forecast['last_sales'] = forecast['last_sales'].fillna(0)
    forecast['trend'] = ((forecast['last_sales'] - forecast['avg_monthly']) / forecast['avg_monthly'] * 100).round(1)

    # توقع الأسبوع القادم
    forecast['توقع_أسبوعي'] = (forecast['avg_monthly'] / 4).round(0)

    # أفضل فرع متوقع
    best_branch = forecast.loc[forecast['avg_monthly'].idxmax(), 'branch_id']

    # جدول التوقعات
    rows = ''
    for _, row in forecast.iterrows():
        trend_color = '#2ecc71' if row['trend'] >= 0 else '#e74c3c'
        arrow = '↑' if row['trend'] >= 0 else '↓'
        rows += f'''<tr>
            <td>فرع {row["branch_id"]}</td>
            <td>{row["avg_monthly"]:,.0f}</td>
            <td>{row["توقع_أسبوعي"]:,.0f}</td>
            <td>{row["last_sales"]:,.0f}</td>
            <td style="color:{trend_color};font-weight:bold;">{arrow} {abs(row["trend"])}%</td>
        </tr>'''

    html = f'''<!DOCTYPE html><html dir="rtl"><head><title>التوقعات</title>
    <style>
        body{{font-family:Arial;margin:20px;background:#f0f2f5}}
        h1{{color:#2c3e50;text-align:center}}
        .nav{{text-align:center;margin:15px 0}}
        .nav a{{background:#3498db;color:white;padding:10px 20px;border-radius:5px;text-decoration:none;font-weight:bold}}
        .section-title{{font-size:20px;font-weight:bold;color:#2c3e50;margin:25px 0 15px;border-right:4px solid #e67e22;padding-right:10px}}
        .highlight{{background:white;border-radius:10px;padding:20px;margin-bottom:20px;box-shadow:0 2px 5px rgba(0,0,0,0.1);font-size:18px;border-right:5px solid #e67e22}}
        table{{width:100%;border-collapse:collapse;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}
        th{{background:#2c3e50;color:white;padding:12px;text-align:center}}
        td{{padding:12px;text-align:center;border-bottom:1px solid #eee}}
        tr:hover{{background:#f8f9fa}}
        .note{{color:#7f8c8d;font-size:13px;margin-top:15px;text-align:center}}
    </style></head><body>
    <h1>🔮 التوقعات</h1>
    <div class="nav"><a href="/">← العودة للداشبورد</a></div>

    <div class="section-title">الفرع المتوقع الأعلى مبيعات</div>
    <div class="highlight">
        🏆 الفرع المتوقع أن يحقق أعلى مبيعات بناءً على أداء 2025: <strong>فرع {best_branch}</strong>
    </div>

    <div class="section-title">توقعات المبيعات لكل فرع</div>
    <table>
        <tr>
            <th>الفرع</th>
            <th>متوسط المبيعات الشهرية (2025)</th>
            <th>توقع الأسبوع القادم</th>
            <th>آخر شهر فعلي ({last_month})</th>
            <th>الاتجاه مقارنة بالمتوسط</th>
        </tr>
        {rows}
    </table>
    <p class="note">* التوقعات مبنية على متوسط أداء 2025 من أبريل إلى ديسمبر</p>
    </body></html>'''
    return html


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
