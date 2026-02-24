from flask import Flask, request
import pandas as pd
import plotly.graph_objects as go

app = Flask(__name__)

# قراءة البيانات
df = pd.read_excel('Book10.xlsx')

# تجهيز البيانات
df['date'] = pd.to_datetime(df['date'], errors='coerce')
df['total'] = pd.to_numeric(df['total'], errors='coerce').fillna(0)
df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
df['cost'] = pd.to_numeric(df['cost'], errors='coerce').fillna(0)
df['line_cost'] = df['qty'] * df['cost']

# بناء رقم فاتورة داخلي
invoice_id = 0
ids = []
for v in df['invoice_no']:
    if pd.notna(v) and str(v).strip() != "":
        invoice_id += 1
    ids.append(invoice_id)
df['invoice_id'] = ids

# استخراج الفرع
df['branch_id'] = df['warehouse'].astype(str).str.extract(r'(\d+)')[0]

# مستوى الفاتورة
invoice_level = (
    df.groupby(['invoice_id', 'branch_id'], as_index=False)
      .agg(
          date=('date', 'first'),
          total_sales=('total', 'sum'),
          total_cost=('line_cost', 'sum'),
          note=('note', 'first')
      )
)
invoice_level['total_profit'] = invoice_level['total_sales'] - invoice_level['total_cost']

@app.route('/')
def dashboard():
    branch_filter = request.args.get('branch', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    filtered = invoice_level.copy()

    if branch_filter != 'all':
        filtered = filtered[filtered['branch_id'] == branch_filter]

    if date_from:
        filtered = filtered[filtered['date'] >= pd.to_datetime(date_from)]

    if date_to:
        filtered = filtered[filtered['date'] <= pd.to_datetime(date_to)]

    total_sales = filtered['total_sales'].sum()
    total_cost = filtered['total_cost'].sum()
    total_profit = filtered['total_profit'].sum()
    total_invoices = filtered['invoice_id'].nunique()

    # ملخص الفروع
    branch_summary = (
        filtered.groupby('branch_id', as_index=False)
                .agg(المبيعات=('total_sales', 'sum'),
                     الأرباح=('total_profit', 'sum'))
    )
    branch_summary['اسم الفرع'] = 'فرع ' + branch_summary['branch_id'].astype(str)

    # أفضل فرع
    if not branch_summary.empty:
        best_sales_branch = branch_summary.loc[branch_summary['المبيعات'].idxmax(), 'اسم الفرع']
        best_sales_val = branch_summary['المبيعات'].max()
        best_profit_branch = branch_summary.loc[branch_summary['الأرباح'].idxmax(), 'اسم الفرع']
        best_profit_val = branch_summary['الأرباح'].max()
        analysis_html = f'''
        <div class="analysis">
            <div class="analysis-card">
                <div class="analysis-icon">🏆</div>
                <div class="analysis-text">
                    <strong>أعلى مبيعات:</strong> {best_sales_branch}
                    <span class="analysis-val">{best_sales_val:,.0f} ريال</span>
                </div>
            </div>
            <div class="analysis-card">
                <div class="analysis-icon">💰</div>
                <div class="analysis-text">
                    <strong>أعلى أرباح:</strong> {best_profit_branch}
                    <span class="analysis-val">{best_profit_val:,.0f} ريال</span>
                </div>
            </div>
        </div>
        '''
    else:
        analysis_html = '<p>لا توجد بيانات للفترة المحددة.</p>'

    # مخطط أعمدة ثابت بدون تفاعل
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='المبيعات',
        x=branch_summary['اسم الفرع'],
        y=branch_summary['المبيعات'],
        marker_color='#3498db',
        text=branch_summary['المبيعات'].apply(lambda x: f'{x:,.0f}'),
        textposition='outside'
    ))
    fig.add_trace(go.Bar(
        name='الأرباح',
        x=branch_summary['اسم الفرع'],
        y=branch_summary['الأرباح'],
        marker_color='#2ecc71',
        text=branch_summary['الأرباح'].apply(lambda x: f'{x:,.0f}'),
        textposition='outside'
    ))
    fig.update_layout(
        title='مقارنة المبيعات والأرباح بين الفروع',
        barmode='group',
        yaxis_title='المبلغ (ريال)',
        xaxis_title='الفرع',
        legend_title='النوع',
        font=dict(family='Arial', size=13),
        dragmode=False,
        hovermode=False,
        margin=dict(t=60, b=60)
    )
    graph_html = fig.to_html(full_html=False, config={
        'staticPlot': True,
        'displayModeBar': False
    })

    # خيارات الفروع
    branches = sorted(invoice_level['branch_id'].dropna().unique())
    branch_options = '<option value="all">كل الفروع</option>'
    for b in branches:
        selected = 'selected' if branch_filter == str(b) else ''
        branch_options += f'<option value="{b}" {selected}>فرع {b}</option>'

    html = f'''
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <title>داشبورد محلات الكفرات</title>
        <style>
            body {{ font-family: Arial; margin: 20px; background: #f0f2f5; }}
            h1 {{ color: #2c3e50; text-align: center; margin-bottom: 20px; }}
            .filters {{ background: white; padding: 15px 20px; border-radius: 10px; margin-bottom: 20px; display: flex; gap: 15px; align-items: center; flex-wrap: wrap; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .filters label {{ font-weight: bold; color: #2c3e50; }}
            .filters select, .filters input {{ padding: 8px; border-radius: 5px; border: 1px solid #ccc; font-size: 14px; }}
            .filters button {{ padding: 8px 25px; background: #3498db; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; font-weight: bold; }}
            .kpi {{ display: flex; justify-content: space-around; margin-bottom: 20px; flex-wrap: wrap; }}
            .kpi-card {{ background: white; padding: 20px 30px; border-radius: 10px; text-align: center; flex: 1; margin: 8px; min-width: 150px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .kpi-value {{ font-size: 28px; font-weight: bold; color: #3498db; }}
            .kpi-value.green {{ color: #2ecc71; }}
            .kpi-label {{ color: #7f8c8d; margin-top: 5px; }}
            .chart {{ background: white; border-radius: 10px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .analysis {{ display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }}
            .analysis-card {{ background: white; border-radius: 10px; padding: 20px; flex: 1; min-width: 200px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); display: flex; align-items: center; gap: 15px; }}
            .analysis-icon {{ font-size: 36px; }}
            .analysis-text {{ display: flex; flex-direction: column; gap: 5px; font-size: 16px; }}
            .analysis-val {{ color: #3498db; font-size: 20px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>داشبورد محلات الكفرات</h1>

        <div class="filters">
            <form method="get" style="display:flex; gap:15px; align-items:center; flex-wrap:wrap;">
                <div>
                    <label>الفرع: </label>
                    <select name="branch">{branch_options}</select>
                </div>
                <div>
                    <label>من: </label>
                    <input type="date" name="date_from" value="{date_from}">
                </div>
                <div>
                    <label>إلى: </label>
                    <input type="date" name="date_to" value="{date_to}">
                </div>
                <button type="submit">تطبيق</button>
            </form>
        </div>

        <div class="kpi">
            <div class="kpi-card">
                <div class="kpi-value">{total_invoices:,}</div>
                <div class="kpi-label">عدد الفواتير</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{total_sales:,.0f}</div>
                <div class="kpi-label">إجمالي المبيعات</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{total_cost:,.0f}</div>
                <div class="kpi-label">إجمالي التكلفة</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value green">{total_profit:,.0f}</div>
                <div class="kpi-label">إجمالي الربح</div>
            </div>
        </div>

        <div class="chart">{graph_html}</div>

        {analysis_html}

    </body>
    </html>
    '''
    return html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
