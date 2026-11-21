import os, sys, base64
from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
LOGO = sys.argv[2] if len(sys.argv) > 2 else ""
os.makedirs(OUT, exist_ok=True)
DATE = "11.20"
TOP = "ARCHI COMPETITION NEWS · " + DATE

if LOGO and os.path.exists(LOGO):
    b64 = base64.b64encode(open(LOGO, "rb").read()).decode()
    LOGO_HTML = f'<img class="logo" src="data:image/png;base64,{b64}">'
else:  # temporary text wordmark until the real logo file is provided
    LOGO_HTML = ('<div class="logo txt"><b>DIO</b> <b>PRESENT</b> <span class="ar">Architects</span>'
                 ' <span class="ent">&amp;Ent.</span></div>')

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{width:1080px;height:1350px;background:#121212;color:#F5F5F0;font-family:'Noto Sans CJK KR',sans-serif;word-break:keep-all;overflow:hidden}
.root{position:relative;width:1080px;height:1350px;padding:150px 88px 165px;display:flex;flex-direction:column;justify-content:flex-end;gap:44px}
.bg{position:absolute;left:0;top:0;width:1080px;height:1350px;z-index:0}
.root>*:not(.bg){position:relative;z-index:1}
.topline{position:absolute!important;top:150px;left:88px;right:88px;display:flex;justify-content:space-between;font-size:24px;font-weight:700;letter-spacing:.08em;color:#B8B8B8}
.topline .n{color:#C6F432}
.chip{align-self:flex-start;border:2px solid #C6F432;color:#C6F432;border-radius:999px;padding:8px 24px;font-size:24px;font-weight:700;letter-spacing:.04em}
h1{font-size:84px;font-weight:900;line-height:1.15;letter-spacing:-.01em;margin-top:-20px}
.lead{font-size:33px;color:#B8B8B8;line-height:1.45;font-weight:500;margin-top:-16px}
hr{border:0;border-top:2px solid #333;margin:-8px 0 -12px}
ul{list-style:none;display:flex;flex-direction:column;gap:18px}
li{font-size:32px;line-height:1.35;display:flex;gap:22px;align-items:flex-start;font-weight:500}
li:before{content:'';flex:0 0 14px;height:14px;background:#C6F432;margin-top:16px}
.foot{display:flex;flex-direction:column;gap:14px}
.src{font-size:22px;color:#9A9A9A}
.logo{height:28px;align-self:flex-end}
.logo.txt{height:auto;font-size:26px;line-height:28px;letter-spacing:.02em;color:#F5F5F0;font-weight:700}
.logo.txt .ar{font-weight:400}
.logo.txt .ent{color:#DD743C;font-weight:500}
.cover h1.big{font-size:112px;line-height:1.12;margin:0}
.cover .acc{color:#C6F432}
.cover .sub{font-size:33px;color:#B8B8B8;margin-top:-10px}
.toc{display:flex;flex-direction:column;gap:14px;font-size:27px}
.toc div{display:flex;gap:22px}.toc span{color:#C6F432;font-weight:700}
"""

L = 'stroke="#6E6E6E" stroke-width="2" fill="none"'
A = 'stroke="#C6F432" stroke-width="3" fill="none"'
def svg(inner):
    return (f'<svg class="bg" viewBox="0 0 1080 1350" xmlns="http://www.w3.org/2000/svg">'
            f'<g transform="translate(533,205) scale(.45)" opacity=".75">{inner}</g></svg>')

def grid(x, y, w, h, cols, rows):
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {L}/>'
    for c in range(1, cols): s += f'<line x1="{x+w*c/cols}" y1="{y}" x2="{x+w*c/cols}" y2="{y+h}" {L}/>'
    for r in range(1, rows): s += f'<line x1="{x}" y1="{y+h*r/rows}" x2="{x+w}" y2="{y+h*r/rows}" {L}/>'
    return s

# backgrounds (abstract line drawings; y is relative to 150px offset)
BG = {}
BG["cover"] = svg(grid(120,180,150,240,3,6)+grid(300,90,190,330,4,8)+grid(520,230,130,190,2,5)
    +grid(680,40,170,380,3,10)+f'<line x1="60" y1="420" x2="1020" y2="420" {A}/>'
    +f'<rect x="680" y="40" width="170" height="38" fill="#C6F432" opacity=".35"/>')
BG["01"] = svg(grid(200,90,680,330,10,7)+f'<line x1="120" y1="420" x2="960" y2="420" {A}/>'
    +f'<rect x="472" y="326" width="136" height="94" {A}/>')
p=""
for i in range(5):
    y=110+i*62; p+=f'<line x1="180" y1="{y}" x2="900" y2="{y}" {L}/>'
    for j in range(8): p+=f'<rect x="{220+j*82}" y="{y+18}" width="56" height="30" rx="8" {L}/>'
p+=f'<polyline points="900,420 980,358 900,296 980,234 900,172" {A}/><line x1="120" y1="420" x2="1000" y2="420" {A}/>'
BG["02"]=svg(p)
p=""
for i,y in enumerate([80,200,320]):
    p+=f'<rect x="150" y="{y}" width="230" height="80" rx="6" {L}/><line x1="190" y1="{y+30}" x2="340" y2="{y+30}" {L}/><line x1="190" y1="{y+52}" x2="300" y2="{y+52}" {L}/>'
    p+=f'<line x1="380" y1="{y+40}" x2="610" y2="240" {L}/>'
p+=f'<circle cx="700" cy="240" r="95" {A}/><text x="700" y="254" text-anchor="middle" fill="#C6F432" font-size="40" font-weight="700" font-family="Noto Sans CJK KR">HUB</text>'
BG["03"]=svg(p)
p=f'<rect x="250" y="250" width="580" height="120" {L}/><line x1="230" y1="250" x2="850" y2="250" {A}/>'
for x,h in [(150,330),(330,400),(520,380),(700,410),(900,320)]:
    p+=f'<line x1="{x}" y1="{420}" x2="{x}" y2="{420-h}" {L}/><circle cx="{x}" cy="{420-h+20}" r="{46}" {L}/>'
p+=f'<line x1="80" y1="420" x2="1000" y2="420" {A}/>'
BG["04"]=svg(p)
p=(grid(170,170,140,250,2,5)+grid(470,60,140,360,2,8)+grid(770,220,140,200,2,4)
   +f'<polygon points="540,0 552,30 584,30 558,48 568,78 540,60 512,78 522,48 496,30 528,30" {A}/>'
   +f'<line x1="80" y1="420" x2="1000" y2="420" {A}/>')
BG["05"]=svg(p)

CARDS = [
 ("01","정읍지식산업센터","KOREA · 당선작","정읍 지식산업센터<br>설계공모<br>당선작 선정",
  "신정동 공공임대형 지식산업센터의<br>설계 밑그림이 나왔다.",
  ["11월 18일 심사, 19일 결과 발표","당선작 1점·입상작 4점 선정","총사업비 365억 원, 2029년 준공 목표"],
  "천지일보·웹이코노미"),
 ("02","학성새벽시장","KOREA · 당선작","학성새벽시장<br>주차전용건물<br>설계안 확정",
  "울산 중구 전통시장 주차난 해소를 위한<br>공영 주차전용건물 설계공모 결과.",
  ["제출작 15개 중 공동 응모작 당선","디오엠에이 + 다담건축사사무소","2027년 7월 착공, 2028년 5월 준공 계획"],
  "웹이코노미·서울세계타임즈"),
 ("03","설계공모제도","KOREA · 제도","공공건축 공모<br>2027년부터<br>건축HUB로",
  "한국부동산원이 발주기관 실무자 대상<br>설계공모 제도 개정 설명회를 열었다.",
  ["11월 6일 서울 건설회관에서 설명회","공고·결과 등록, 건축HUB로 일원화","심사위원 후보군·심사 이력 관리 강화"],
  "대한경제"),
 ("04","디진어워즈","GLOBAL · 영국","디진 어워즈<br>올해의 건축은<br>숲속 사우나",
  "나무가 지붕을 뚫고 올라온 일본 가나가와의<br>사우나가 최고상을 받았다.",
  ["11월 18일 런던에서 수상작 발표","건축 부문 19개 카테고리 수상작 공개","Daichi Silent River Tree Sauna 2관왕"],
  "Dezeen"),
 ("05","WAF2026","GLOBAL · 미국","세계건축축제<br>WAF 2026<br>최종 승부",
  "미국 포트로더데일에서 사흘간<br>라이브 심사가 이어지고 있다.",
  ["11월 18~20일 포트로더데일 개최","630개 출품작 중 416개 최종 후보","첫날 23개 부문 수상, 20일 대상 발표"],
  "ArchDaily·Bustler"),
]

def page(body, bg):
    return f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body><div class='root'>{BG[bg]}{body}</div></body></html>"

pages = []
toc = "".join(f"<div><span>{c[0]}</span>{c[3].replace('<br>',' ')}</div>" for c in CARDS)
cover = (f"<div class='topline'><span>{TOP}</span><span class='n'>11월 셋째 주</span></div>"
         f"<div class='cover' style='display:flex;flex-direction:column;gap:44px'>"
         f"<h1 class='big'>오늘의<br><span class='acc'>건축설계공모</span><br>뉴스</h1>"
         f"<div class='sub'>국내 당선작·제도 변화부터 해외 건축상까지</div>"
         f"<div class='toc'>{toc}</div></div><div class='foot'>{LOGO_HTML}</div>")
pages.append(("00_표지", page(cover, "cover")))
for n,name,chip,h,lead,facts,src in CARDS:
    body = (f"<div class='topline'><span>{TOP}</span><span class='n'>{n} / 05</span></div>"
            f"<div class='chip'>{chip}</div><h1>{h}</h1><div class='lead'>{lead}</div><hr>"
            f"<ul>{''.join(f'<li>{f}</li>' for f in facts)}</ul>"
            f"<div class='foot'><div class='src'>출처: {src}</div>{LOGO_HTML}</div>")
    pages.append((f"{n}_{name}", page(body, n)))

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width":1080,"height":1350})
    for fn, html in pages:
        pg.set_content(html); pg.wait_for_timeout(300)
        # report content bounds to check the 135-1215 safe area
        box = pg.evaluate("""()=>{let t=1e9,bt=0;document.querySelectorAll('.root>*:not(.bg)').forEach(e=>{const r=e.getBoundingClientRect();t=Math.min(t,r.top);bt=Math.max(bt,r.bottom)});return [t,bt]}""")
        pg.screenshot(path=f"{OUT}/{fn}.png")
        print(fn, "content y:", [round(v) for v in box])
    b.close()
