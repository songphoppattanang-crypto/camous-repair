# สรุปงานตามวันที่แจ้งซ่อม ใช้เวลาไทยและช่วงวันที่แบบรวมต้นไม่รวมปลาย
from datetime import date, datetime, timedelta, timezone
from flask import request
from enhancements import display_repairs
PERIODS={'day':'รายวัน','week':'รายสัปดาห์','month':'รายเดือน','year':'รายปี'}

def selection():
    today=datetime.now(timezone(timedelta(hours=7))).date()
    try:
        anchor=date.fromisoformat(request.args.get('date',today.isoformat()))
        if not 1900<=anchor.year<=9998:anchor=today
    except (ValueError,TypeError):anchor=today
    period=request.args.get('period','month')
    if period not in PERIODS:period='month'
    return anchor,period

def boundaries(anchor,period):
    if period=='day':return anchor,anchor+timedelta(days=1)
    if period=='week':
        start=anchor-timedelta(days=anchor.weekday());return start,start+timedelta(days=7)
    if period=='year':return date(anchor.year,1,1),date(anchor.year+1,1,1)
    start=anchor.replace(day=1)
    end=date(anchor.year+1,1,1) if anchor.month==12 else date(anchor.year,anchor.month+1,1)
    return start,end

def span_text(start,end):
    last=end-timedelta(days=1)
    return start.strftime('%d/%m/%Y') if start==last else start.strftime('%d/%m/%Y')+' – '+last.strftime('%d/%m/%Y')

def date_filter():
    anchor,period=selection();start,end=boundaries(anchor,period)
    return anchor,period,start,end

def dashboard_data(db,statuses):
    anchor,period,start,end=date_filter()
    # นับสี่ช่วงในคำสั่งเดียว ลดจำนวนครั้งที่ติดต่อฐานข้อมูลออนไลน์
    expressions=[];params=[];cards=[]
    for key,label in PERIODS.items():
        a,b=boundaries(anchor,key)
        expressions.append('SUM(CASE WHEN created_at>=? AND created_at<? THEN 1 ELSE 0 END) AS '+key+'_count')
        params.extend([a.isoformat(),b.isoformat()])
        cards.append({'key':key,'label':label,'range':span_text(a,b)})
    totals=db.execute('SELECT '+','.join(expressions)+' FROM repairs',params).fetchone()
    for card in cards:card['total']=totals[card['key']+'_count'] or 0
    counts={key:0 for key in statuses}
    where=(start.isoformat(),end.isoformat())
    state="CASE WHEN c.id IS NOT NULL THEN 'cancelled' ELSE r.status END"
    for row in db.execute('SELECT '+state+' AS status,COUNT(*) AS total FROM repairs r LEFT JOIN repair_cancellations c ON c.repair_id=r.id WHERE r.created_at>=? AND r.created_at<? GROUP BY '+state,where):counts[row['status']]=row['total']
    if period=='day':
        position,length=12,2
        bins=[(f'{hour:02d}',f'{hour:02d}:00') for hour in range(24)]
    elif period=='year':
        position,length=6,2
        bins=[(f'{month:02d}',label) for month,label in enumerate(['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'],1)]
    else:
        position,length=1,10
        bins=[((start+timedelta(days=i)).isoformat(),(start+timedelta(days=i)).strftime('%d/%m')) for i in range((end-start).days)]
    buckets={row['bucket']:row['total'] for row in db.execute(f'SELECT substr(created_at,{position},{length}) AS bucket,COUNT(*) AS total FROM repairs WHERE created_at>=? AND created_at<? GROUP BY substr(created_at,{position},{length})',where)}
    peak=max([buckets.get(key,0) for key,label in bins]+[1]);step=900/len(bins);bars=[]
    for i,(key,label) in enumerate(bins):
        value=buckets.get(key,0);height=150*value/peak
        bars.append({'label':label,'total':value,'x':round(50+i*step+step*.2,2),'width':round(step*.6,2),'height':round(height,2),'y':round(190-height,2),'center':round(50+(i+.5)*step,2),'show_label':len(bins)<=12 or i%5==0 or i==len(bins)-1})
    latest=db.execute('SELECT r.*,u.name AS owner,e.reporter_name,c.id AS cancelled_id FROM repairs r JOIN users u ON u.id=r.user_id LEFT JOIN repair_evidence e ON e.repair_id=r.id LEFT JOIN repair_cancellations c ON c.repair_id=r.id WHERE r.created_at>=? AND r.created_at<? ORDER BY r.id DESC LIMIT 5',where).fetchall()
    total=sum(counts.values())
    return {'anchor':anchor.isoformat(),'period':period,'periods':PERIODS,'range_label':span_text(start,end),'cards':cards,'counts':counts,'total':total,'open_total':counts['pending']+counts['working'],'done_rate':round(counts['done']/total*100) if total else 0,'bars':bars,'latest':display_repairs(latest)}
