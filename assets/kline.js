(function(){
  var UP='#ff5470', DOWN='#2fd4a6', GRID='rgba(154,166,201,.14)', TXT='#6b7aa6';
  var EM_KLINE='https://push2his.eastmoney.com/api/qt/stock/kline/get?ut=fa5fd1943c7b386f172d6893dbfba10b&klt=101&fqt=1&lmt=60&end=20500101&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57&secid=',
      EM_FFLOW='https://push2his.eastmoney.com/api/qt/stock/fflow/kline/get?ut=fa5fd1943c7b386f172d6893dbfba10b&secid=1.000001&secid2=0.399001&klt=101&fqt=1&lmt=30&end=20500101&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63&cb=__CB__';
  var mask=document.createElement('div'); mask.id='kmask';
  mask.innerHTML='<div class="kmodal"><div class="khead"><div><div class="ktitle"></div><div class="kref"></div></div><button class="kclose" title="关闭">✕</button></div><div class="kbody"></div></div>';
  document.body.appendChild(mask);
  var mTitle=mask.querySelector('.ktitle'), mRef=mask.querySelector('.kref'), mBody=mask.querySelector('.kbody');
  function closeModal(){ mask.classList.remove('show'); document.body.style.overflow=''; }
  mask.addEventListener('click', function(e){ if(e.target===mask) closeModal(); });
  mask.querySelector('.kclose').addEventListener('click', closeModal);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeModal(); });

  function loadScript(url, vn, cb, timeout){
    var done=false, s=document.createElement('script');
    var timer=setTimeout(function(){ if(!done){ done=true; fin(); cb(null); } }, timeout||9000);
    function fin(){ clearTimeout(timer); try{ delete window[vn]; }catch(e){ window[vn]=undefined; } if(s.parentNode) s.parentNode.removeChild(s); }
    s.onload=function(){ if(done) return; done=true; var raw=window[vn]; fin(); cb(raw); };
    s.onerror=function(){ if(!done) return; done=true; fin(); cb(null); };
    s.src=url; document.head.appendChild(s);
  }
  function loadEM(url, cb, timeout){
    var fn='emcb'+Date.now()+Math.floor(Math.random()*1e5);
    var done=false, s=document.createElement('script');
    var timer=setTimeout(function(){ if(!done){ done=true; fin(); cb(null); } }, timeout||4000);
    function fin(){ clearTimeout(timer); try{ delete window[fn]; }catch(e){ window[fn]=undefined; } if(s.parentNode) s.parentNode.removeChild(s); }
    window[fn]=function(d){ if(done) return; done=true; fin(); cb(d); };
    s.onerror=function(){ if(!done) return; done=true; fin(); cb(null); };
    s.src=url.replace('__CB__', fn); document.head.appendChild(s);
  }
  function parseTx(raw, code){
    if(!raw || raw.code!==0 || !raw.data) return null;
    var node=raw.data[code]; if(!node) return null;
    var days=node.day || node.qfqday; if(!days || !days.length) return null;
    return days.slice(-60).map(function(a){ return {d:a[0],o:+a[1],c:+a[2],h:+a[3],l:+a[4],v:+a[5]||0}; });
  }
  function parseSina(raw){
    if(!raw || !raw.length) return null;
    return raw.slice(-60).map(function(a){ return {d:a.date,o:+a.open,c:+a.close,h:+a.high,l:+a.low,v:+a.volume||0}; });
  }
  function parseEM(raw){
    if(!raw || !raw.data || !raw.data.klines || !raw.data.klines.length) return null;
    return raw.data.klines.slice(-60).map(function(s){ var a=s.split(','); return {d:a[0],o:+a[1],c:+a[2],h:+a[3],l:+a[4],v:+a[5]||0}; });
  }

  function drawK(bars){
    var n=bars.length, W=680, H=400, padL=12, padR=58, top=44, kBot=288, volT=308, volB=384, bot=398;
    var iw=W-padL-padR, cw=iw/n, bw=Math.max(2, cw*0.62);
    var pmin=Infinity, pmax=-Infinity, vmax=0, i, b;
    for(i=0;i<n;i++){ b=bars[i]; if(b.l<pmin) pmin=b.l; if(b.h>pmax) pmax=b.h; if(b.v>vmax) vmax=b.v; }
    var padP=(pmax-pmin)*0.04||1; pmin-=padP; pmax+=padP;
    function Y(p){ return top+(pmax-p)/(pmax-pmin)*(kBot-top); }
    function ma(k){ var out=[]; for(i=0;i<n;i++){ if(i<k-1){ out.push(null); continue; } var s=0; for(var j=i-k+1;j<=i;j++) s+=bars[j].c; out.push(s/k); } return out; }
    var ma5=ma(5), ma10=ma(10);
    var last=bars[n-1].c, first=bars[0].c, chg=(last/first-1)*100, ccol=chg>=0?UP:DOWN;
    var g='';
    for(i=0;i<=4;i++){ var py=top+(kBot-top)*i/4, pv=pmax-(pmax-pmin)*i/4;
      g+='<line x1="'+padL+'" y1="'+py+'" x2="'+(W-padR)+'" y2="'+py+'" stroke="'+GRID+'" stroke-width="1"/>';
      g+='<text x="'+(W-padR+6)+'" y="'+(py+3.5)+'" fill="'+TXT+'" font-size="10.5" text-anchor="start">'+pv.toFixed(pv>1000?0:2)+'</text>';
    }
    for(i=0;i<n;i++){ b=bars[i]; var cx=padL+cw*(i+0.5), up=b.c>=b.o, col=up?UP:DOWN;
      g+='<line x1="'+cx+'" y1="'+Y(b.h)+'" x2="'+cx+'" y2="'+Y(b.l)+'" stroke="'+col+'" stroke-width="1"/>';
      var yo=Y(b.o), yc=Y(b.c), rh=Math.max(1,Math.abs(yc-yo));
      g+='<rect x="'+(cx-bw/2)+'" y="'+Math.min(yo,yc)+'" width="'+bw+'" height="'+rh+'" fill="'+col+'" fill-opacity="1"/>';
      var vh=vmax>0?b.v/vmax*(volB-volT):0;
      g+='<rect x="'+(cx-bw/2)+'" y="'+(volB-vh)+'" width="'+bw+'" height="'+Math.max(1,vh)+'" fill="'+col+'" fill-opacity="0.42"/>';
    }
    function maPath(arr, col){
      var d='', k;
      for(k=0;k<n;k++){ if(arr[k]==null) continue; var x=padL+cw*(k+0.5), y=Y(arr[k]); d+=(d?' L':'M')+x.toFixed(1)+' '+y.toFixed(1); }
      return d?'<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="1.3" stroke-opacity="0.9"/>':'';
    }
    g+=maPath(ma5,'#f5c451'); g+=maPath(ma10,'#a78bfa');
    g+='<text x="'+padL+'" y="'+(bot-2)+'" fill="'+TXT+'" font-size="10.5">'+bars[0].d+'</text>';
    g+='<text x="'+(W-padR)+'" y="'+(bot-2)+'" fill="'+TXT+'" font-size="10.5" text-anchor="end">'+bars[n-1].d+'</text>';
    g+='<text x="'+padL+'" y="'+(top-18)+'" fill="'+ccol+'" font-size="12.5" font-weight="700">近'+n+'日 '+(chg>=0?'+':'')+chg.toFixed(2)+'% · 最新 '+last+'</text>';
    g+='<text x="'+padL+'" y="'+(volT-6)+'" fill="'+TXT+'" font-size="9.5">成交量</text>';
    return '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet"><rect x="0" y="0" width="'+W+'" height="'+H+'" fill="transparent"/>'+g+'</svg>';
  }

  function openModal(el){
    var name=el.getAttribute('data-name')||el.textContent.trim().slice(0,8);
    var code=el.getAttribute('data-code')||'';
    var src=el.getAttribute('data-src')||'tx';
    var ref=el.getAttribute('data-ref')||'';
    var bk=el.getAttribute('data-bk')||'';
    mTitle.textContent=name+' · 近60日K线';
    mRef.textContent='加载中…';
    mBody.innerHTML='<div class="kloading"><div class="kspin"></div><br>K线加载中…</div>';
    mask.classList.add('show'); document.body.style.overflow='hidden';
    function show(bars, srcTxt){
      if(bars){ mRef.innerHTML=srcTxt; mBody.innerHTML=drawK(bars); }
      else mBody.innerHTML='<div class="kfail">⚠ K线数据获取失败，请稍后重试</div>';
    }
    function tryTx(){
      var vn='kq'+Date.now()+Math.floor(Math.random()*1e5);
      loadScript('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?_var='+vn+'&param='+encodeURIComponent(code)+',day,,,60,qfq', vn, function(raw){
        show(parseTx(raw, code), (ref?('参考指数 <b>'+ref+'</b> · '):'')+'腾讯行情 · 仅供参考');
      });
    }
    function trySina(){
      var vn='kq'+Date.now()+Math.floor(Math.random()*1e5);
      loadScript('https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20'+vn+'=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol='+encodeURIComponent(code), vn, function(raw){
        show(parseSina(raw), '新浪期货 · 仅供参考');
      });
    }
    if(bk){
      loadEM(EM_KLINE+encodeURIComponent('90.'+bk)+'&cb=__CB__', function(d){
        var bars=parseEM(d);
        if(bars) show(bars, '东方财富 · '+name+'板块K线 · 实时');
        else tryTx();
      });
    } else if(src==='sina'){ trySina(); } else { tryTx(); }
  }

  function loadMainFlow(){
    var eVal=document.querySelector('.mf-value'), e5=document.querySelector('.mf-d5'), e20=document.querySelector('.mf-d20');
    if(!eVal && !e5 && !e20) return;
    loadEM(EM_FFLOW, function(d){
      if(!d || !d.data || !d.data.klines || d.data.klines.length<5) return;
      var rows=d.data.klines.map(function(s){ var a=s.split(','); return {d:a[0], v:parseFloat(a[1])||0}; });
      var latest=rows[rows.length-1];
      function fmt(v){ return (v>=0?'+':'')+(v/1e8).toFixed(2)+'亿'; }
      function setTxt(el, v){ if(!el) return; el.textContent=fmt(v); el.style.color=v>=0?UP:DOWN; }
      if(eVal) setTxt(eVal, latest.v);
      if(e5) setTxt(e5, rows.slice(-5).reduce(function(a,b){return a+b.v;},0));
      if(e20 && rows.length>=20) setTxt(e20, rows.slice(-20).reduce(function(a,b){return a+b.v;},0));
    }, 8000);
  }

  function bindK(){ document.querySelectorAll('.klk,.klk-row').forEach(function(el){ if(!el._kbound){ el._kbound=1; el.addEventListener('click', function(){ openModal(el); }); } }); }
  function onReady(fn){ if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', fn); else fn(); }
  onReady(bindK); onReady(loadMainFlow);
})();
