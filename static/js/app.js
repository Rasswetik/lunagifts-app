// ============ LUNA GIFTS — SHARED APP.JS ============
let tg = null;
let currentUser = null;
let authKey = null;
let authPollInterval = null;

// ============ LOADING SCREEN ============
let _loadEl = null, _loadBar = null, _loadPct = null, _loadStatus = null;
let _loadProgress = 0;

function _initLoadingUI(){
    _loadEl = document.getElementById('loadingScreen');
    _loadBar = document.getElementById('loadProgressBar');
    _loadPct = document.getElementById('loadPercent');
    _loadStatus = document.getElementById('loadStatus');
}

function setLoadProgress(pct, status){
    _loadProgress = Math.min(100, Math.max(_loadProgress, pct));
    if(_loadBar) _loadBar.style.width = _loadProgress + '%';
    if(_loadPct) _loadPct.textContent = Math.round(_loadProgress) + '%';
    if(_loadStatus && status) _loadStatus.textContent = status;
}

function dismissLoading(){
    if(!_loadEl) return;
    setLoadProgress(100, 'Готово');
    setTimeout(()=>{
        _loadEl.classList.add('fade-out');
        setTimeout(()=>_loadEl.remove(), 500);
    }, 300);
}

(function(){ _initLoadingUI(); })();

// ============ APP INIT ============
async function initApp(){
    setLoadProgress(10, 'Подключение...');
    if (typeof Telegram !== 'undefined' && Telegram.WebApp){
        tg = Telegram.WebApp;
        tg.ready(); tg.expand();
        tg.setHeaderColor('#0a0e17');
        tg.setBackgroundColor('#0a0e17');
        setLoadProgress(20, 'Telegram OK');
        const init = tg.initDataUnsafe;
        if (init && init.user){
            setLoadProgress(30, 'Загрузка данных...');
            const u = init.user;
            const res = await fetch('/api/init',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:u.id,username:u.username||'',first_name:u.first_name||'',last_name:u.last_name||'',photo_url:u.photo_url||''})});
            currentUser = await res.json();
            setLoadProgress(60, 'Данные загружены');
            updateUI(); return;
        }
    }
    setLoadProgress(20, 'Проверка сессии...');
    const saved = localStorage.getItem('luna_user');
    if (saved){
        try{
            const p = JSON.parse(saved);
            if (p && p.telegram_id){
                setLoadProgress(40, 'Обновление баланса...');
                const r = await fetch('/api/balance/'+p.telegram_id);
                if (r.ok){ const d = await r.json(); p.balance = d.balance; if(d.is_admin!==undefined) p.is_admin=d.is_admin; localStorage.setItem('luna_user',JSON.stringify(p)); currentUser = p; setLoadProgress(60, 'Данные загружены'); updateUI(); return; }
            }
        }catch(e){}
        localStorage.removeItem('luna_user');
    }
    setLoadProgress(60, 'Авторизация...');
    showAuthModal();
}

// ============ AUTH ============
async function showAuthModal(){
    try{
        const res = await fetch('/api/auth/generate',{method:'POST'});
        const data = await res.json();
        authKey = data.key;
    }catch(e){ return; }
    const ov = document.createElement('div');
    ov.className = 'modal-overlay active';
    ov.id = 'authModal';
    ov.style.alignItems = 'center';
    ov.innerHTML = '<div class="modal" style="border-radius:24px;max-width:380px;text-align:center;padding:30px 24px;">'
        +'<img src="/static/img/lock.png" style="width:64px;height:64px;margin:0 auto 16px;filter:drop-shadow(0 6px 18px rgba(0,0,0,.4));" alt="">'
        +'<div style="font-size:20px;font-weight:800;margin-bottom:6px;">Авторизация</div>'
        +'<div style="font-size:13px;color:var(--text-secondary);margin-bottom:20px;line-height:1.5;">Отправьте команду боту<br><a href="https://t.me/lunagifts_robot" target="_blank" style="color:var(--accent);font-weight:600;">@lunagifts_robot</a></div>'
        +'<div style="background:var(--bg-card);border:1px solid rgba(107,138,255,.3);border-radius:14px;padding:16px;margin-bottom:16px;">'
        +'<div style="font-size:11px;color:var(--text-secondary);margin-bottom:6px;text-transform:uppercase;letter-spacing:1px;">Введите в боте:</div>'
        +'<div style="font-size:20px;font-weight:800;color:var(--accent);letter-spacing:3px;font-family:monospace;" id="authKeyDisplay">/auth '+authKey+'</div></div>'
        +'<button onclick="copyAuthKey()" style="width:100%;padding:12px;border:none;border-radius:12px;background:linear-gradient(135deg,var(--accent),#4a6bd4);color:#fff;font-size:14px;font-weight:700;cursor:pointer;margin-bottom:12px;" id="copyAuthBtn">Скопировать команду</button>'
        +'<div style="display:flex;align-items:center;justify-content:center;gap:8px;color:var(--text-secondary);font-size:13px;" id="authStatus"><img src="/static/img/loading.gif" alt="" style="width:16px;height:16px;"><span>Ожидание авторизации...</span></div>'
        +'</div>';
    document.body.appendChild(ov);
    startAuthPolling();
}

function copyAuthKey(){
    const text = '/auth ' + authKey;
    navigator.clipboard.writeText(text).then(()=>{
        const btn = document.getElementById('copyAuthBtn');
        btn.textContent='Скопировано!'; btn.style.background='linear-gradient(135deg,#2EC76E,#26A85D)';
        setTimeout(()=>{ btn.textContent='Скопировать команду'; btn.style.background='linear-gradient(135deg,var(--accent),#4a6bd4)'; },2000);
    }).catch(()=>{
        const el=document.createElement('textarea');el.value=text;document.body.appendChild(el);el.select();document.execCommand('copy');document.body.removeChild(el);
    });
}

function startAuthPolling(){
    if (authPollInterval) clearInterval(authPollInterval);
    authPollInterval = setInterval(async()=>{
        if (!authKey) return;
        try{
            const res = await fetch('/api/auth/check/'+authKey);
            const data = await res.json();
            if (data.status==='confirmed' && data.user){
                clearInterval(authPollInterval); authPollInterval=null;
                currentUser = data.user;
                localStorage.setItem('luna_user',JSON.stringify(currentUser));
                const m=document.getElementById('authModal'); if(m) m.remove();
                document.body.style.overflow='';
                updateUI();
                showNotification('Авторизация успешна!','success');
                // Reload page so page-specific init (e.g. admin panel) runs with currentUser
                setTimeout(()=>location.reload(), 800);
            }
        }catch(e){}
    },2000);
}

// ============ UI ============
function updateUI(){
    if (!currentUser) return;
    document.querySelectorAll('.user-avatar,.inventory-avatar').forEach(el=>{
        el.src = currentUser.photo_url ? currentUser.photo_url : generateAvatar(currentUser.first_name||currentUser.username);
    });
    document.querySelectorAll('.user-name,.inventory-name').forEach(el=>{
        el.textContent = currentUser.first_name||currentUser.username||'User';
    });
    document.querySelectorAll('.balance-amount').forEach(el=>{
        el.textContent = formatBalance(currentUser.balance);
    });
    // Update avatar wallet overlay
    updateAvatarWallet();
    // Fetch online count
    fetchOnlineCount();
}

function formatBalance(b){
    if(b>=1000000)return(b/1000000).toFixed(1)+'M';
    if(b>=1000)return(b/1000).toFixed(1)+'K';
    return Math.floor(b).toString();
}

function imgSrc(p){ return !p?'/static/img/star.png':p.startsWith('/')?p:'/'+p; }

function getNftBg(slug,count){
    if(!slug)return'';
    const n=Math.floor(Math.random()*(count||1000))+1;
    return 'https://nft.fragment.com/gift/'+slug+'-'+n+'.medium.jpg';
}

let _nftRotating=false;
function startNftRotation(){
    setInterval(()=>{
        if(_nftRotating)return;
        const bds=document.querySelectorAll('.gift-backdrop[data-slug]');
        if(!bds.length)return;
        _nftRotating=true;
        let pending=bds.length;
        function done(){if(--pending<=0)_nftRotating=false;}
        bds.forEach(img=>{
            const url=getNftBg(img.dataset.slug,parseInt(img.dataset.count)||1000);
            const pre=new Image();
            pre.onload=()=>{img.style.transition='opacity .6s';img.style.opacity='0';setTimeout(()=>{img.src=url;requestAnimationFrame(()=>{img.style.opacity='.55';setTimeout(done,600);});},600);};
            pre.onerror=()=>{img.style.opacity='.55';done();};
            pre.src=url;
        });
    },5000);
}

function generateAvatar(name){
    const cols=['#6B8AFF','#2EC76E','#E6675E','#FFD74A','#9B59B6','#E67E22'];
    const l=(name||'U').charAt(0).toUpperCase();
    const c=cols[l.charCodeAt(0)%cols.length];
    const cv=document.createElement('canvas');cv.width=100;cv.height=100;
    const ctx=cv.getContext('2d');
    ctx.fillStyle=c;ctx.beginPath();ctx.roundRect(0,0,100,100,20);ctx.fill();
    ctx.fillStyle='white';ctx.font='bold 48px -apple-system,sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(l,50,52);
    return cv.toDataURL();
}

function showNotification(msg,type='success'){
    const ex=document.querySelector('.notification');if(ex)ex.remove();
    const n=document.createElement('div');n.className='notification '+type;n.textContent=msg;
    document.body.appendChild(n);
    if(tg)try{tg.HapticFeedback.impactOccurred(type==='success'?'light':'heavy');}catch(e){}
    setTimeout(()=>n.remove(),2500);
}

function openModal(id){const m=document.getElementById(id);if(m){m.classList.add('active');document.body.style.overflow='hidden';}}
function closeModal(id){const m=document.getElementById(id);if(m){m.classList.remove('active');document.body.style.overflow='';}}
document.addEventListener('click',e=>{if(e.target.classList.contains('modal-overlay')&&e.target.id!=='authModal'){e.target.classList.remove('active');document.body.style.overflow='';}});

async function refreshBalance(){
    if(!currentUser)return;
    try{
        const r=await fetch('/api/balance/'+currentUser.telegram_id);
        const d=await r.json();
        if(d.balance!==undefined){currentUser.balance=d.balance;document.querySelectorAll('.balance-amount').forEach(el=>{el.textContent=formatBalance(currentUser.balance);});localStorage.setItem('luna_user',JSON.stringify(currentUser));}
    }catch(e){}
}

function logout(){localStorage.removeItem('luna_user');currentUser=null;location.reload();}

// ============ TOPUP (shared — injected modals) ============
let selectedTopupAmount = 0;
let _topupMode = ''; // 'stars' or 'ton'

function injectTopupModals(){
    if(document.getElementById('topupModal'))return;
    const html = ''
    +'<div class="modal-overlay" id="topupModal"><div class="modal">'
    +'<div class="sheet-handle"></div>'
    +'<div style="font-size:18px;font-weight:800;margin-bottom:16px;">Пополнение</div>'
    +'<div class="topup-row disabled">'
    +'<img class="topup-row-icon" src="/static/img/gift.png" alt="">'
    +'<div class="topup-row-info"><div class="topup-row-title">Депозит подарками</div><div class="topup-row-desc">Появится в инвенторе LunaGifts</div></div>'
    +'<span class="topup-row-badge">Скоро</span></div>'
    +'<div class="topup-row" onclick="openTopupSheet(\'ton\')">'
    +'<img class="topup-row-icon" src="/static/img/ton.png" alt="" onerror="this.src=\'/static/img/star.png\'">'
    +'<div class="topup-row-info"><div class="topup-row-title">Toncoin</div><div class="topup-row-desc">Без комиссии</div></div>'
    +'<span class="topup-row-badge">от 0.2</span></div>'
    +'<div class="topup-row" onclick="openTopupSheet(\'stars\')">'
    +'<img class="topup-row-icon" src="/static/img/star.png" alt="">'
    +'<div class="topup-row-info"><div class="topup-row-title">Telegram Stars</div><div class="topup-row-desc">Без комиссии</div></div>'
    +'<span class="topup-row-badge">от 1</span></div>'
    +'</div></div>'

    +'<div class="bottom-sheet-overlay" id="topupSheet" onclick="if(event.target===this)closeTopupSheet();">'
    +'<div class="bottom-sheet">'
    +'<div class="sheet-handle"></div>'
    +'<div class="sheet-title" id="topupSheetTitle">Введите сумму</div>'
    +'<div class="sheet-input-wrap"><input type="number" id="topupSheetAmount" placeholder="0" inputmode="decimal" oninput="onTopupSheetInput()"></div>'
    +'<div class="sheet-min-hint" id="topupSheetHint"></div>'
    +'<button class="sheet-continue-btn inactive" id="topupSheetBtn" onclick="continueTopup()" disabled>Продолжить</button>'
    +'</div></div>'

    // Legacy modals kept for TON connect flow
    +'<div class="modal-overlay" id="tonTopupModal"><div class="modal">'
    +'<button class="modal-close" onclick="closeModal(\'tonTopupModal\')"><img src="/static/img/exit.png" alt="✕"></button>'
    +'<div class="section-header" style="margin-top:10px;"><h2><img class="section-icon" src="/static/img/ton.png" alt="" onerror="this.src=\'/static/img/star.png\'"> TON Connect</h2><p>Пополняйте баланс через TON</p></div>'
    +'<div style="text-align:center;padding:12px 0;">'
    +'<div style="font-size:14px;color:var(--text-secondary);margin-bottom:12px;">1 TON = 100 ⭐</div>'
    +'<div id="tonWalletStatus" style="font-size:14px;color:var(--text-secondary);margin-bottom:16px;">Кошелёк не подключён</div>'
    +'<div id="tonConnectedUI" style="display:none;"><div style="margin-bottom:12px;"><input type="number" id="tonAmount" placeholder="Сумма в TON" min="0.1" step="0.1" style="width:100%;padding:12px 14px;border-radius:14px;border:1px solid var(--border);background:var(--bg-card);color:var(--text);font-size:15px;font-weight:600;" oninput="updateTonPreview()"></div><div id="tonPreview" style="font-size:13px;color:var(--gold);margin-bottom:12px;"></div><button class="topup-confirm-btn" onclick="sendTonPayment()" id="tonPayBtn">Оплатить</button></div>'
    +'<button class="topup-confirm-btn" onclick="connectTonWallet()" id="tonConnectBtn">Подключить TON Wallet</button>'
    +'<button class="topup-confirm-btn" onclick="disconnectTonWallet()" id="tonDisconnectBtn" style="display:none;background:linear-gradient(135deg,#E64C4C,#D43A3A);margin-top:8px;">Отключить кошелёк</button>'
    +'</div></div></div>';
    document.body.insertAdjacentHTML('beforeend', html);
}

function openTopupSheet(mode){
    _topupMode=mode;selectedTopupAmount=0;
    closeModal('topupModal');
    injectTopupModals();
    const input=document.getElementById('topupSheetAmount');if(input)input.value='';
    const title=document.getElementById('topupSheetTitle');
    const hint=document.getElementById('topupSheetHint');
    const btn=document.getElementById('topupSheetBtn');
    if(mode==='ton'){
        if(title)title.textContent='Сумма в TON';
        if(hint)hint.textContent='Минимум 0.2 TON · 1 TON = 100 ⭐';
        if(input)input.placeholder='0.00';input.step='0.1';input.min='0.2';
    }else{
        if(title)title.textContent='Сумма в Stars';
        if(hint)hint.textContent='Минимум 1 ⭐';
        if(input)input.placeholder='0';input.step='1';input.min='1';
    }
    if(btn){btn.disabled=true;btn.className='sheet-continue-btn inactive';btn.textContent='Продолжить';}
    const sheet=document.getElementById('topupSheet');
    if(sheet)sheet.classList.add('active');
}

function closeTopupSheet(){
    const sheet=document.getElementById('topupSheet');
    if(sheet)sheet.classList.remove('active');
}

function onTopupSheetInput(){
    const input=document.getElementById('topupSheetAmount');
    const btn=document.getElementById('topupSheetBtn');
    const hint=document.getElementById('topupSheetHint');
    const val=parseFloat(input.value);
    if(_topupMode==='ton'){
        const ok=val>=0.2;
        if(btn){btn.disabled=!ok;btn.className='sheet-continue-btn '+(ok?'active':'inactive');btn.textContent=ok?'Пополнить '+Math.floor(val*100)+' ⭐':'Продолжить';}
        if(hint)hint.textContent=ok?'Вы получите '+Math.floor(val*100)+' ⭐':'Минимум 0.2 TON';
        if(hint)hint.style.color=ok?'var(--gold)':'var(--text-muted)';
        selectedTopupAmount=ok?val:0;
    }else{
        const ok=val>=1;
        if(btn){btn.disabled=!ok;btn.className='sheet-continue-btn '+(ok?'active':'inactive');btn.textContent=ok?'Пополнить '+Math.floor(val)+' ⭐':'Продолжить';}
        if(hint)hint.textContent=ok?'':'Минимум 1 ⭐';
        if(hint)hint.style.color='var(--text-muted)';
        selectedTopupAmount=ok?Math.floor(val):0;
    }
}

function continueTopup(){
    if(!selectedTopupAmount)return;
    closeTopupSheet();
    if(_topupMode==='ton'){
        injectTopupModals();
        // Check if wallet connected
        if(tonConnectUI&&tonConnectUI.connected){
            document.getElementById('tonAmount').value=selectedTopupAmount;
            updateTonPreview();
            openModal('tonTopupModal');
        }else{
            openModal('tonTopupModal');
        }
    }else{
        // Stars flow
        if(!currentUser){showNotification('Авторизуйтесь','error');return;}
        if(!tg||!tg.initDataUnsafe||!tg.initDataUnsafe.user){showNotification('Оплата Stars доступна только в Telegram Mini App','error');return;}
        confirmStarsTopupDirect(selectedTopupAmount);
    }
}

async function confirmStarsTopupDirect(amount){
    if(!currentUser||!amount)return;
    showNotification('Создаём счёт...','success');
    try{
        const res=await fetch('/api/topup/create-invoice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUser.telegram_id,amount:amount})});
        const data=await res.json();
        if(!data.success||!data.invoice_url){showNotification(data.error||'Ошибка','error');return;}
        tg.openInvoice(data.invoice_url,function(status){
            if(status==='paid'){setTimeout(async()=>{await refreshBalance();showNotification('+'+amount+' ⭐ зачислено!','success');selectedTopupAmount=0;},1000);}
            else if(status==='cancelled')showNotification('Оплата отменена','error');
        });
    }catch(e){showNotification('Ошибка соединения','error');}
}

function showStarsTopup(){
    injectTopupModals();
    openTopupSheet('stars');
}

function selectTopupAmount(amount,el){
    selectedTopupAmount=amount;
}

function onCustomAmountInput(el){
    // Legacy — kept for compatibility
    const val=parseInt(el.value);
    if(val>0) selectedTopupAmount=Math.min(val,100000);
    else selectedTopupAmount=0;
}

async function confirmStarsTopup(){
    if(!currentUser||!selectedTopupAmount)return;
    confirmStarsTopupDirect(selectedTopupAmount);
}

// ============ TON CONNECT ============
let tonConnectUI=null;let _tonInitAttempts=0;
const TON_TO_STARS=100;
const TON_RECEIVER='UQCHqlS8KSD3ZOF-OwV5efg2ST60u2JTnGEXeViQLU9g5v3i';

function initTonConnect(){
    if(tonConnectUI)return;
    try{
        const Cls=window.TON_CONNECT_UI?.TonConnectUI||window.TonConnectUI;
        if(!Cls){_tonInitAttempts++;if(_tonInitAttempts<10)setTimeout(initTonConnect,500);return;}
        tonConnectUI=new Cls({manifestUrl:window.location.origin+'/tonconnect-manifest.json'});
        tonConnectUI.onStatusChange(w=>updateTonUI(w));
        if(tonConnectUI.connected)updateTonUI(tonConnectUI.wallet);
    }catch(e){console.error('TON init:',e);}
}

function updateTonUI(wallet){
    const status=document.getElementById('tonWalletStatus');
    const connectBtn=document.getElementById('tonConnectBtn');
    const disconnectBtn=document.getElementById('tonDisconnectBtn');
    const connUI=document.getElementById('tonConnectedUI');
    if(wallet){
        let addr=wallet.account.address;
        try{const fn=window.TON_CONNECT_UI?.toUserFriendlyAddress||window.toUserFriendlyAddress;if(fn)addr=fn(addr,wallet.account.chain==='-239');}catch(e){}
        const short=addr.slice(0,6)+'...'+addr.slice(-4);
        if(status)status.innerHTML='Подключён: <span style="color:var(--green);font-weight:700;">'+short+'</span>';
        if(connectBtn)connectBtn.style.display='none';
        if(disconnectBtn)disconnectBtn.style.display='block';
        if(connUI)connUI.style.display='block';
    }else{
        if(status)status.textContent='Кошелёк не подключён';
        if(connectBtn)connectBtn.style.display='block';
        if(disconnectBtn)disconnectBtn.style.display='none';
        if(connUI)connUI.style.display='none';
    }
}

function updateTonPreview(){
    const input=document.getElementById('tonAmount');const preview=document.getElementById('tonPreview');
    const val=parseFloat(input.value);
    if(val>0&&preview)preview.textContent='Вы получите: '+Math.floor(val*TON_TO_STARS)+' ⭐';
    else if(preview)preview.textContent='';
}

async function connectTonWallet(){
    if(!tonConnectUI){initTonConnect();await new Promise(r=>setTimeout(r,600));}
    if(!tonConnectUI){showNotification('TON Connect не загружен','error');return;}
    try{closeModal('tonTopupModal');closeModal('topupModal');await tonConnectUI.openModal();}
    catch(e){showNotification('Ошибка подключения кошелька','error');}
}

async function disconnectTonWallet(){
    if(tonConnectUI)try{await tonConnectUI.disconnect();updateTonUI(null);showNotification('Кошелёк отключён','success');}catch(e){}
}

async function sendTonPayment(){
    if(!tonConnectUI||!tonConnectUI.connected){showNotification('Сначала подключите кошелёк','error');return;}
    if(!currentUser)return;
    const input=document.getElementById('tonAmount');
    const tonVal=parseFloat(input.value);
    if(!tonVal||tonVal<0.1){showNotification('Минимум 0.1 TON','error');return;}
    const starsAmount=Math.floor(tonVal*TON_TO_STARS);
    const nanotons=Math.floor(tonVal*1e9).toString();
    const btn=document.getElementById('tonPayBtn');
    if(btn){btn.disabled=true;btn.textContent='Отправка...';}
    try{
        await tonConnectUI.sendTransaction({validUntil:Math.floor(Date.now()/1000)+600,messages:[{address:TON_RECEIVER,amount:nanotons,payload:''}]});
        showNotification('Транзакция отправлена','success');
        const res=await fetch('/api/topup/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUser.telegram_id,amount:starsAmount})});
        const data=await res.json();
        if(data.success){currentUser.balance=data.new_balance;localStorage.setItem('luna_user',JSON.stringify(currentUser));updateUI();closeModal('tonTopupModal');showNotification('+'+starsAmount+' ⭐ зачислено!','success');input.value='';}
    }catch(e){
        if(e.message&&(e.message.includes('User rejected')||e.message.includes('Interrupted')))showNotification('Транзакция отменена','error');
        else showNotification('Ошибка транзакции','error');
    }
    if(btn){btn.disabled=false;btn.textContent='Оплатить';}
}

function showTonTopup(){injectTopupModals();closeModal('topupModal');openModal('tonTopupModal');}

// ============ BALANCE ACTION + WITHDRAWAL ============
let withdrawGifts=[];let withdrawSelected={};let withdrawAmount=0;
const MIN_WITHDRAW_AMOUNT=15;

function openBalanceAction(){
    injectWithdrawModals();
    openModal('balanceActionModal');
}

function injectWithdrawModals(){
    injectTopupModals();
    if(document.getElementById('balanceActionModal'))return;
    const html=''
    +'<div class="modal-overlay" id="balanceActionModal"><div class="modal">'
    +'<button class="modal-close" onclick="closeModal(\'balanceActionModal\')"><img src="/static/img/exit.png" alt="✕"></button>'
    +'<div class="section-header" style="margin-top:10px;"><h2>Баланс</h2><p>Выберите действие</p></div>'
    +'<div class="topup-methods">'
    +'<div class="topup-method" onclick="closeModal(\'balanceActionModal\');openModal(\'topupModal\');"><img src="/static/img/plus.png" alt="+"><span>Пополнить</span></div>'
    +'<div class="topup-method" onclick="closeModal(\'balanceActionModal\');openWithdrawModal();"><img src="/static/img/star.png" alt="★"><span>Вывод Stars</span></div>'
    +'</div></div></div>'

    +'<div class="modal-overlay" id="withdrawModal"><div class="modal" style="max-height:85vh;overflow-y:auto;">'
    +'<button class="modal-close" onclick="closeModal(\'withdrawModal\')"><img src="/static/img/exit.png" alt="✕"></button>'
    +'<div class="section-header" style="margin-top:10px;"><h2><img class="section-icon" src="/static/img/star.png" alt=""> Вывод Stars</h2><p>Минимум '+MIN_WITHDRAW_AMOUNT+' ⭐</p></div>'
    +'<div id="withdrawStep1">'
    +'<div style="font-size:14px;color:var(--text-secondary);margin-bottom:8px;">Ваш баланс: <span id="withdrawBalance" style="color:var(--gold);font-weight:700;">0</span> ⭐</div>'
    +'<div id="withdrawRelayBalance" style="display:none;font-size:12px;color:var(--green);margin-bottom:10px;"></div>'
    +'<div style="margin-bottom:14px;"><input type="number" id="withdrawAmountInput" placeholder="Сумма вывода ⭐" min="'+MIN_WITHDRAW_AMOUNT+'" style="width:100%;padding:12px 14px;border-radius:14px;border:1px solid var(--border);background:var(--bg-card);color:var(--text);font-size:16px;font-weight:700;" oninput="onWithdrawAmountInput()"></div>'
    +'<div id="withdrawGiftPicker" style="display:none;">'
    +'<div style="font-size:14px;font-weight:700;margin-bottom:10px;">Выберите подарки:</div>'
    +'<div id="withdrawGiftGrid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;"></div>'
    +'<div id="withdrawSelectedInfo" style="font-size:13px;color:var(--text-secondary);margin-bottom:14px;text-align:center;"></div>'
    +'</div>'
    +'<button id="withdrawConfirmBtn" onclick="confirmWithdraw()" disabled style="width:100%;padding:14px;border:none;border-radius:16px;background:linear-gradient(135deg,#6B8AFF,#8B5CF6,#6B8AFF,#A78BFA);background-size:200% auto;animation:btnShimmer 3s linear infinite;color:#fff;font-size:15px;font-weight:800;cursor:pointer;opacity:.5;transition:opacity .3s;">Вывести</button>'
    +'</div>'
    +'<div id="withdrawStep2" style="display:none;text-align:center;padding:30px 0;"><img src="/static/img/loading.gif" alt="" style="width:40px;height:40px;margin:0 auto 16px;"><p style="color:var(--text-secondary);font-size:14px;">Отправляем подарки...</p></div>'
    +'<div id="withdrawStep3" style="display:none;text-align:center;padding:20px 0;"><div id="withdrawResultIcon" style="font-size:48px;margin-bottom:12px;"></div><div id="withdrawResultMsg" style="font-size:16px;font-weight:700;margin-bottom:16px;line-height:1.5;"></div><button onclick="closeModal(\'withdrawModal\')" style="padding:12px 32px;border:none;border-radius:14px;background:linear-gradient(135deg,var(--accent),#4a6bd4);color:#fff;font-size:15px;font-weight:700;cursor:pointer;">Закрыть</button></div>'
    +'</div></div>';
    document.body.insertAdjacentHTML('beforeend',html);
}

async function openWithdrawModal(){
    injectWithdrawModals();
    withdrawSelected={};withdrawAmount=0;
    const inp=document.getElementById('withdrawAmountInput');if(inp)inp.value='';
    document.getElementById('withdrawStep1').style.display='block';
    document.getElementById('withdrawStep2').style.display='none';
    document.getElementById('withdrawStep3').style.display='none';
    document.getElementById('withdrawGiftPicker').style.display='none';
    const btn=document.getElementById('withdrawConfirmBtn');if(btn){btn.disabled=true;btn.style.opacity='.5';}
    if(currentUser)document.getElementById('withdrawBalance').textContent=formatBalance(currentUser.balance);
    openModal('withdrawModal');
    try{
        const res=await fetch('/api/withdraw/gifts');const data=await res.json();
        withdrawGifts=data.gifts||[];
        // Relay balance info hidden
        const balEl=document.getElementById('withdrawRelayBalance');
        if(balEl) balEl.style.display='none';
        if(!withdrawGifts.length){
            document.getElementById('withdrawGiftPicker').style.display='block';
            document.getElementById('withdrawGiftGrid').innerHTML='<p style="color:var(--text-secondary);grid-column:1/-1;text-align:center;font-size:13px;">Подарки не загружены. Проверьте подключение Telethon в админке.</p>';
        }
    }catch(e){withdrawGifts=[];}
}

function onWithdrawAmountInput(){
    const val=parseInt(document.getElementById('withdrawAmountInput').value)||0;
    withdrawAmount=val;withdrawSelected={};
    if(val>=MIN_WITHDRAW_AMOUNT&&withdrawGifts.length>0){document.getElementById('withdrawGiftPicker').style.display='block';renderWithdrawGifts();updateWithdrawInfo();}
    else{document.getElementById('withdrawGiftPicker').style.display='none';}
    updateWithdrawBtn();
}

function renderWithdrawGifts(){
    const grid=document.getElementById('withdrawGiftGrid');
    if(!withdrawGifts.length){grid.innerHTML='<p style="color:var(--text-secondary);grid-column:1/-1;text-align:center;font-size:13px;">Нет подарков для вывода</p>';return;}
    grid.innerHTML=withdrawGifts.filter(g=>g.available!==false).map(g=>{
        const count=withdrawSelected[g.id]||0;
        const sel=count>0;
        const bg=g.bg_color||'#6b8aff';
        const thumbSrc=g.thumb_b64?'data:'+(g.thumb_mime||'image/webp')+';base64,'+g.thumb_b64:(g.image||'/static/img/star.png');
        return '<div onclick="toggleWithdrawGift('+g.id+','+g.star_count+')" style="background:'+(sel?'linear-gradient(135deg,'+bg+'40,'+bg+'20)':'var(--bg-card)')+';border:2px solid '+(sel?bg:'var(--border)')+';border-radius:14px;padding:12px 6px;text-align:center;cursor:pointer;transition:all .25s;position:relative;'+(sel?'box-shadow:0 0 20px '+bg+'30;transform:scale(1.03);':'')+'">'
        +(count>0?'<div style="position:absolute;top:-6px;right:-6px;background:var(--accent);color:#fff;border-radius:50%;width:22px;height:22px;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;">'+count+'</div>':'')
        +'<img src="'+thumbSrc+'" alt="" style="width:48px;height:48px;object-fit:contain;margin:0 auto 6px;display:block;" onerror="this.src=\'/static/img/star.png\'">'
        +'<div style="font-size:13px;font-weight:800;color:var(--gold);">'+g.star_count+' ⭐</div>'
        +'<div style="font-size:11px;color:var(--text-secondary);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+(g.name||'Gift')+'</div></div>';
    }).join('');
}

function toggleWithdrawGift(giftId,starCount){
    const total=getWithdrawSelectedTotal();
    const qty=withdrawSelected[giftId]||0;
    if(total+starCount<=withdrawAmount)withdrawSelected[giftId]=qty+1;
    else if(qty>0)delete withdrawSelected[giftId];
    renderWithdrawGifts();updateWithdrawInfo();updateWithdrawBtn();
}

function getWithdrawSelectedTotal(){
    let t=0;for(const[id,qty]of Object.entries(withdrawSelected)){const g=withdrawGifts.find(x=>x.id==id);if(g)t+=g.star_count*qty;}return t;
}

function updateWithdrawInfo(){
    const info=document.getElementById('withdrawSelectedInfo');
    const total=getWithdrawSelectedTotal();
    if(total>0){const rem=withdrawAmount-total;info.innerHTML='Выбрано: <span style="color:var(--gold);font-weight:700;">'+total+' ⭐</span> из '+withdrawAmount+' ⭐'+(rem>0?' <span style="color:var(--text-muted);">(ещё '+rem+' ⭐)</span>':' ✅');}
    else info.innerHTML='<span style="color:var(--text-muted);">Нажмите на подарки чтобы выбрать</span>';
}

function updateWithdrawBtn(){
    const btn=document.getElementById('withdrawConfirmBtn');
    const total=getWithdrawSelectedTotal();
    const ok=total>0&&total<=withdrawAmount&&withdrawAmount>=MIN_WITHDRAW_AMOUNT&&currentUser&&currentUser.balance>=withdrawAmount;
    if(btn){btn.disabled=!ok;btn.style.opacity=ok?'1':'.5';btn.textContent=ok?'Вывести '+total+' ⭐':(withdrawAmount>=MIN_WITHDRAW_AMOUNT?'Выберите подарки':'Вывести');}
}

async function confirmWithdraw(){
    if(!currentUser)return;
    const total=getWithdrawSelectedTotal();
    if(total<MIN_WITHDRAW_AMOUNT||currentUser.balance<total)return;
    const gifts=[];
    for(const[id,qty]of Object.entries(withdrawSelected)){const g=withdrawGifts.find(x=>x.id==id);if(g)gifts.push({id:g.id,name:g.name,star_count:g.star_count,telegram_gift_id:g.telegram_gift_id||'',qty:qty});}
    document.getElementById('withdrawStep1').style.display='none';
    document.getElementById('withdrawStep2').style.display='block';
    try{
        const res=await fetch('/api/withdraw/request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUser.telegram_id,gifts:gifts})});
        const data=await res.json();
        document.getElementById('withdrawStep2').style.display='none';
        document.getElementById('withdrawStep3').style.display='block';
        if(data.success){
            if(data.new_balance!==undefined){currentUser.balance=data.new_balance;localStorage.setItem('luna_user',JSON.stringify(currentUser));updateUI();}
            const icons={completed:'✅',queued:'⏳',partial:'⚠️'};
            document.getElementById('withdrawResultIcon').textContent=icons[data.status]||'📋';
            document.getElementById('withdrawResultMsg').innerHTML=data.message||'Заявка создана!';
            showNotification(data.message||'Успешно!','success');
        }else{
            document.getElementById('withdrawResultIcon').textContent='❌';
            document.getElementById('withdrawResultMsg').textContent=data.error||'Ошибка';
            showNotification(data.error||'Ошибка','error');
        }
    }catch(e){
        document.getElementById('withdrawStep2').style.display='none';
        document.getElementById('withdrawStep3').style.display='block';
        document.getElementById('withdrawResultIcon').textContent='❌';
        document.getElementById('withdrawResultMsg').textContent='Ошибка соединения';
    }
}

// ============ INIT ============
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',()=>{startNftRotation();});}
else{startNftRotation();}

// ============ AVATAR WALLET OVERLAY ============
function updateAvatarWallet(){
    const overlay=document.getElementById('avatarWallet');
    if(!overlay)return;
    if(tonConnectUI&&tonConnectUI.connected&&tonConnectUI.wallet){
        let addr=tonConnectUI.wallet.account.address;
        try{const fn=window.TON_CONNECT_UI?.toUserFriendlyAddress||window.toUserFriendlyAddress;if(fn)addr=fn(addr,tonConnectUI.wallet.account.chain==='-239');}catch(e){}
        const short=addr.slice(0,4)+'\n'+addr.slice(-4);
        overlay.textContent=short;
        overlay.style.display='flex';
    }else{
        if(currentUser&&(currentUser.first_name||currentUser.username)){
            overlay.style.display='none';
        }else{
            overlay.style.display='none';
        }
    }
}

// ============ ONLINE COUNT ============
let _onlineFetched=false;
async function fetchOnlineCount(){
    if(_onlineFetched)return;_onlineFetched=true;
    try{
        const r=await fetch('/api/online');const d=await r.json();
        document.querySelectorAll('#onlineCount').forEach(el=>{el.textContent=d.count||0;});
    }catch(e){
        document.querySelectorAll('#onlineCount').forEach(el=>{el.textContent='—';});
    }
    setTimeout(()=>{_onlineFetched=false;},30000);
}
