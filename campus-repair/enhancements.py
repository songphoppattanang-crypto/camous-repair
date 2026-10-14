# ตัวช่วยแบ่งหน้าและแสดงสถานะยกเลิก ใช้ร่วมกันหลายหน้า
import math
from flask import request, url_for

def paginate(db, query, params=()):
    try: page=max(1,int(request.args.get('page','1')))
    except ValueError: page=1
    total=db.execute('SELECT COUNT(*) AS total FROM ('+query+') AS counted',params).fetchone()['total']
    pages=max(1,math.ceil(total/10));page=min(page,pages)
    rows=db.execute('SELECT * FROM ('+query+') AS page_items ORDER BY id DESC LIMIT ? OFFSET ?',tuple(params)+(10,(page-1)*10)).fetchall()
    links={}
    for direction,number in [('previous',page-1),('next',page+1)]:
        links[direction]=url_for(request.endpoint,**dict(request.args.to_dict(),page=number)) if 1<=number<=pages else None
    return rows, {'page':page,'pages':pages,'total':total,**links}

def display_repairs(rows):
    result=[]
    for row in rows:
        data=dict(row)
        if data.get('cancelled_id'):data['status']='cancelled'
        result.append(data)
    return result
