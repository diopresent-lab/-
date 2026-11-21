import os, sys, subprocess
from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
FPS, DUR = 30, 15.0
FR = "/tmp/claude-0/-home-user--/d4ee4bea-1114-50e4-8f6e-4bbf4a2d80a7/scratchpad/reel/frames"
os.makedirs(FR, exist_ok=True)

HTML = r"""
<html><head><meta charset='utf-8'><style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:1080px;height:1920px;background:#121212;color:#F5F5F0;font-family:'Noto Sans CJK KR';word-break:keep-all;overflow:hidden}
.s{position:absolute;left:0;right:0;text-align:center;opacity:0}
.big{font-size:104px;font-weight:900;line-height:1.18}
.mid{font-size:70px;font-weight:800;line-height:1.3}
.acc{color:#C6F432}
.sm{font-size:40px;color:#B8B8B8;font-weight:500}
svg{position:absolute;left:0;top:0}
.tag{position:absolute;top:250px;left:0;right:0;text-align:center;font-size:30px;letter-spacing:.12em;color:#9A9A9A;font-weight:700}
</style></head><body>
<div class='tag'>DIO PRESENT · 건축과 음악 사이</div>
<svg width='1080' height='1920' id='g'></svg>
<div class='s big' id='t1' style='top:560px'>낮에는<br><span class='acc'>도면</span>을 그리고</div>
<div class='s big' id='t2' style='top:560px'>밤에는<br><span class='acc'>노래</span>를 짓습니다</div>
<div class='s mid' id='t3' style='top:520px'>설계하듯<br>곡을 짓는 건축사</div>
<div class='s mid' id='t4' style='top:470px;line-height:1.55'>기초 = <span class='acc'>비트</span><br>구조 = <span class='acc'>멜로디</span><br>마감 = <span class='acc'>가사</span></div>
<div class='s' id='t5' style='top:500px'><div class='big'>건축과 음악 사이</div>
 <div class='mid' style='margin-top:50px'>다음 곡, <span class='acc'>먼저</span> 들어볼래요?</div>
 <div class='sm' style='margin-top:40px'>팔로우 → @diopresent.official</div></div>
<script>
const g=document.getElementById('g');
const ease=x=>x<0?0:x>1?1:1-Math.pow(1-x,3);
function fade(id,t,a,b){const e=document.getElementById(id);let o=0;
 if(t>=a&&t<b){o=Math.min(ease((t-a)/0.35),ease((b-t)/0.3));}
 if(b>=15&&t>=a)o=ease((t-a)/0.35);
 e.style.opacity=o;e.style.transform=`translateY(${(1-ease((t-a)/0.35))*40}px)`;}
function draw(t){
 let s='';
 const L='stroke="#6E6E6E" stroke-width="3" fill="none"',A='stroke="#C6F432" stroke-width="5" fill="none"';
 // phase 1 (0-4s): blueprint grid draws in, from bottom
 const p=Math.min(1,t/1.6);
 const X0=140,X1=940,Y0=1080,Y1=1560;
 if(t<8){
  const k=t<4?1:Math.max(0,1-(t-4)/1.2); // grid fades as it morphs
  s+=`<g opacity="${k}">`;
  for(let i=0;i<=8;i++){const x=X0+(X1-X0)*i/8;s+=`<line x1="${x}" y1="${Y1}" x2="${x}" y2="${Y1-(Y1-Y0)*p}" ${L}/>`;}
  for(let j=0;j<=4;j++){const y=Y1-(Y1-Y0)*j/4;const w=(X1-X0)*ease((p*5-j)/1);if(w>0)s+=`<line x1="${X0}" y1="${y}" x2="${X0+w}" y2="${y}" ${L}/>`;}
  s+=`<line x1="80" y1="${Y1}" x2="1000" y2="${Y1}" ${A}/></g>`;
 }
 // phase 2 (3.5s+): columns become equalizer bars
 if(t>=3.5){
  const m=ease((t-3.5)/1.2);
  for(let i=0;i<16;i++){
   const x=X0+i*50+10;
   const h=(60+220*Math.abs(Math.sin(t*3.1+i*0.9))*Math.abs(Math.sin(i*1.7+1)))*m;
   s+=`<rect x="${x}" y="${Y1-h}" width="30" height="${h}" fill="${i%4==1?'#C6F432':'#5A5A5A'}"/>`;
  }
  s+=`<line x1="80" y1="${Y1}" x2="1000" y2="${Y1}" ${A}/>`;
 }
 g.innerHTML=s;
 fade('t1',t,0,2.3);fade('t2',t,2.3,4.6);fade('t3',t,4.6,7.6);fade('t4',t,7.6,11.2);fade('t5',t,11.2,15);
 if(t<0.05)document.getElementById('t1').style.opacity=1; // first frame never blank
}
</script></body></html>
"""

n = int(FPS * DUR)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920})
    pg.set_content(HTML); pg.wait_for_timeout(500)
    for i in range(n):
        pg.evaluate(f"draw({i / FPS})")
        pg.screenshot(path=f"{FR}/f{i:04d}.png")
    b.close()
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{FR}/f%04d.png",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", OUT], check=True)
print("done", OUT)
