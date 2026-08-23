/* 自动检测服务端新数据并提示/刷新（解决浏览器缓存导致看不到更新的问题）
   __CURRENT_UPDATE__ 为运行时注入的 JS 变量（见 auto_update.py 的 html_doc 模板） */
(function(){
  function checkUpdate(){
    fetch('data.json?_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json();}).then(function(d){
      var latest=d.lastUpdate||'';
      if(latest && latest!==__CURRENT_UPDATE__){
        var t=document.getElementById('update-toast');
        if(t){t.style.display='block';t.onclick=function(){location.reload(true);};setTimeout(function(){location.reload(true);},4000);}
      }
    }).catch(function(e){});
  }
  checkUpdate();setInterval(checkUpdate,60000);
})();
