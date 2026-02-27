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
        document.body.classList.add('is-tg-miniapp');
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

function imgSrc(p){ return !p?'/static/img/star.svg':p.startsWith('/')?p:'/'+p; }

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
    +'<div class="topup-row" onclick="showNotification(\'Отправьте подарок боту @lunagifts_robot\',\'info\')">'
    +'<img class="topup-row-icon" src="/static/img/gift.png" alt="">'
    +'<div class="topup-row-info"><div class="topup-row-title">Депозит подарками</div><div class="topup-row-desc">Отправьте подарок боту</div></div>'
    +'<span class="topup-row-badge">TopGift</span></div>'
    +'<div class="topup-row" onclick="openCryptoBotTopup()">'
    +'<img class="topup-row-icon" src="/static/img/star.svg" alt="">'
    +'<div class="topup-row-info"><div class="topup-row-title">USDT (CryptoBot)</div><div class="topup-row-desc">5% бонус звёздами</div></div>'
    +'<span class="topup-row-badge">от 1</span></div>'
    +'<div class="topup-row" onclick="openTopupSheet(\'ton\')">'
    +'<img class="topup-row-icon" src="/static/img/ton.svg" alt="" onerror="this.src=\'/static/img/star.svg\'">'
    +'<div class="topup-row-info"><div class="topup-row-title">Toncoin</div><div class="topup-row-desc">Без комиссии</div></div>'
    +'<span class="topup-row-badge">от 0.4</span></div>'
    +'<div class="topup-row" onclick="openTopupSheet(\'stars\')">'
    +'<img class="topup-row-icon" src="/static/img/star.svg" alt="">'
    +'<div class="topup-row-info"><div class="topup-row-title">Telegram Stars</div><div class="topup-row-desc">Без комиссии</div></div>'
    +'<span class="topup-row-badge">от 1</span></div>'
    +'<div class="topup-row" onclick="openCryptoBotTopup()">'
    +'<img class="topup-row-icon" src="/static/img/ton.svg" alt="" onerror="this.src=\'/static/img/star.svg\'">'
    +'<div class="topup-row-info"><div class="topup-row-title">Crypto Bot</div><div class="topup-row-desc">TON, USDT, BTC</div></div>'
    +'<span class="topup-row-badge">Crypto</span></div>'
    +'<button class="sheet-continue-btn active" style="margin-top:14px;width:100%;" onclick="closeModal(\'topupModal\')">Закрыть</button>'
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
    +'<div class="section-header" style="margin-top:10px;"><h2><img class="section-icon" src="/static/img/ton.svg" alt="" onerror="this.src=\'/static/img/star.svg\'"> TON Connect</h2><p>Пополняйте баланс через TON</p></div>'
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

// ============ CRYPTO BOT TOPUP ============
function openCryptoBotTopup(){
    closeModal('topupModal');
    showNotification('CryptoBot: отправьте /pay боту @CryptoBot','info');
    try{
        if(tg&&tg.openTelegramLink)tg.openTelegramLink('https://t.me/CryptoBot');
        else window.open('https://t.me/CryptoBot','_blank');
    }catch(e){window.open('https://t.me/CryptoBot','_blank');}
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
    +'<div class="topup-method" onclick="closeModal(\'balanceActionModal\');openWithdrawModal();"><img src="/static/img/star.svg" alt="★"><span>Вывод Stars</span></div>'
    +'</div></div></div>'

    +'<div class="modal-overlay" id="withdrawModal"><div class="modal" style="max-height:85vh;overflow-y:auto;">'
    +'<button class="modal-close" onclick="closeModal(\'withdrawModal\')"><img src="/static/img/exit.png" alt="✕"></button>'
    +'<div class="section-header" style="margin-top:10px;"><h2><img class="section-icon" src="/static/img/star.svg" alt=""> Вывод Stars</h2><p>Минимум '+MIN_WITHDRAW_AMOUNT+' ⭐</p></div>'
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
        const thumbSrc=g.thumb_b64?'data:'+(g.thumb_mime||'image/webp')+';base64,'+g.thumb_b64:(g.image||'/static/img/star.svg');
        return '<div onclick="toggleWithdrawGift('+g.id+','+g.star_count+')" style="background:'+(sel?'linear-gradient(135deg,'+bg+'40,'+bg+'20)':'var(--bg-card)')+';border:2px solid '+(sel?bg:'var(--border)')+';border-radius:14px;padding:12px 6px;text-align:center;cursor:pointer;transition:all .25s;position:relative;'+(sel?'box-shadow:0 0 20px '+bg+'30;transform:scale(1.03);':'')+'">'
        +(count>0?'<div style="position:absolute;top:-6px;right:-6px;background:var(--accent);color:#fff;border-radius:50%;width:22px;height:22px;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;">'+count+'</div>':'')
        +'<img src="'+thumbSrc+'" alt="" style="width:48px;height:48px;object-fit:contain;margin:0 auto 6px;display:block;" onerror="this.src=\'/static/img/star.svg\'">'
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
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',()=>{startNftRotation();injectDesktopNav();injectMobileHeader();upgradeNavIcons();initBtnRipple();});}
else{startNftRotation();injectDesktopNav();injectMobileHeader();upgradeNavIcons();initBtnRipple();}

// ============ BUTTON RIPPLE EFFECT ============
function initBtnRipple(){
    document.addEventListener('click',function(e){
        var btn=e.target.closest('.case-sheet-open-btn,.result-btn,.topup-pay-btn,.topup-nft-btn,.inv-action-btn,.popular-case-price-btn');
        if(!btn)return;
        btn.style.position=btn.style.position||'relative';
        btn.style.overflow='hidden';
        var ripple=document.createElement('span');
        ripple.className='btn-ripple';
        var rect=btn.getBoundingClientRect();
        var size=Math.max(rect.width,rect.height)*2;
        ripple.style.width=size+'px';
        ripple.style.height=size+'px';
        ripple.style.left=(e.clientX-rect.left-size/2)+'px';
        ripple.style.top=(e.clientY-rect.top-size/2)+'px';
        btn.appendChild(ripple);
        setTimeout(function(){ripple.remove();},600);
    });
}

// ============ SVG NAV ICONS (UpGift style) ============
const NAV_ICONS={
    'gift.png':{
        outline:'<svg width="21" height="20" viewBox="0 0 21 20" fill="white" fill-opacity="0.64" fill-rule="evenodd" clip-rule="evenodd"><path d="M15.5 5.625H17.1339C18.6478 5.625 19.875 6.85223 19.875 8.36609C19.875 8.62079 19.8395 8.87424 19.7695 9.11913L18.1521 14.7802C17.6921 16.3901 16.2207 17.5 14.5464 17.5H8H6.45363C4.77933 17.5 3.30788 16.3901 2.84791 14.7802L1.23047 9.11913C1.1605 8.87424 1.125 8.62079 1.125 8.36609C1.125 6.85223 2.35223 5.625 3.8661 5.625H5.5L5.5 3.75C5.5 2.36929 6.61929 1.25 8 1.25H13C14.3807 1.25 15.5 2.36929 15.5 3.75V5.625ZM7.375 5.625V3.75C7.375 3.40482 7.65482 3.125 8 3.125L13 3.125C13.3452 3.125 13.625 3.40482 13.625 3.75V5.625H8H7.375ZM14.5464 15.625H8H6.45363C5.61648 15.625 4.88075 15.07 4.65077 14.2651L3.03332 8.60403C3.01122 8.52665 3 8.44657 3 8.36609C3 7.88776 3.38776 7.5 3.8661 7.5H8H17.1339C17.6122 7.5 18 7.88776 18 8.36609C18 8.44657 17.9888 8.52665 17.9667 8.60403L16.3492 14.2651C16.1192 15.07 15.3835 15.625 14.5464 15.625ZM8.80886 14.0443C8.30115 14.1458 7.80725 13.8166 7.7057 13.3089L7.0807 10.1839C6.97916 9.67614 7.30843 9.18225 7.81614 9.0807C8.32385 8.97916 8.81775 9.30843 8.91929 9.81614L9.54429 12.9411C9.64583 13.4489 9.31657 13.9427 8.80886 14.0443ZM13.9193 10.1839C14.0208 9.67614 13.6916 9.18225 13.1839 9.0807C12.6761 8.97916 12.1822 9.30843 12.0807 9.81614L11.4557 12.9411C11.3542 13.4489 11.6834 13.9427 12.1911 14.0443C12.6989 14.1458 13.1927 13.8166 13.2943 13.3089L13.9193 10.1839Z"/></svg>',
        filled:'<svg width="20" height="20" viewBox="0 0 16 16" fill="white"><path d="M10.2041 1.01074C11.1457 1.1062 11.8938 1.85435 11.9893 2.7959L12 3V4.5H13.3066C14.5177 4.5 15.5 5.48227 15.5 6.69336C15.5 6.89679 15.4719 7.0993 15.416 7.29492L14.1221 11.8242C13.7541 13.1121 12.5767 13.9999 11.2373 14H4.7627L4.51367 13.9893C4.43572 13.9828 4.35863 13.9723 4.28223 13.96C4.23682 13.9526 4.19224 13.942 4.14746 13.9326C4.1149 13.9258 4.08201 13.921 4.0498 13.9131C4.00664 13.9025 3.96435 13.8894 3.92188 13.877C3.88988 13.8676 3.85775 13.859 3.82617 13.8486C3.78096 13.8338 3.73668 13.8168 3.69238 13.7998C3.66569 13.7896 3.63865 13.7805 3.6123 13.7695C3.56527 13.75 3.5195 13.7279 3.47363 13.7061C3.45047 13.695 3.42714 13.6845 3.4043 13.6729C3.35865 13.6496 3.31386 13.6251 3.26953 13.5996C3.24724 13.5868 3.22507 13.5739 3.20312 13.5605C3.16484 13.5372 3.12702 13.5133 3.08984 13.4883C3.06052 13.4686 3.03153 13.4485 3.00293 13.4277C2.96981 13.4037 2.93739 13.3789 2.90527 13.3535C2.87656 13.3309 2.84819 13.3079 2.82031 13.2842C2.79079 13.2591 2.76195 13.2333 2.7334 13.207C2.70135 13.1776 2.67042 13.147 2.63965 13.1162C2.61803 13.0945 2.59616 13.0731 2.5752 13.0508C2.54349 13.017 2.51258 12.9825 2.48242 12.9473C2.46126 12.9225 2.4403 12.8976 2.41992 12.8721C2.38916 12.8336 2.35997 12.794 2.33105 12.7539C2.3151 12.7318 2.29858 12.7101 2.2832 12.6875C2.25457 12.6455 2.22773 12.6022 2.20117 12.5586C2.18578 12.5333 2.16995 12.5082 2.15527 12.4824C2.13114 12.44 2.10905 12.3963 2.08691 12.3525C2.07348 12.3259 2.05955 12.2996 2.04688 12.2725C1.97985 12.1293 1.92242 11.9799 1.87793 11.8242L0.583984 7.29492L0.547852 7.14746C0.534092 7.08254 0.523439 7.01704 0.515625 6.95117C0.513414 6.93264 0.511503 6.91409 0.509766 6.89551C0.503534 6.82837 0.500015 6.76093 0.5 6.69336C0.5 6.56111 0.513698 6.43147 0.536133 6.30566C0.538278 6.29363 0.539652 6.28149 0.541992 6.26953C0.54877 6.2349 0.558019 6.20102 0.566406 6.16699C0.574215 6.1353 0.580674 6.1034 0.589844 6.07227C0.599682 6.03888 0.611683 6.00634 0.623047 5.97363C0.633516 5.94349 0.643543 5.91331 0.655273 5.88379C0.669426 5.84818 0.684259 5.81299 0.700195 5.77832C0.712132 5.75235 0.724394 5.72659 0.737305 5.70117C0.752904 5.67047 0.769152 5.6402 0.786133 5.61035C0.801391 5.58353 0.817642 5.55735 0.833984 5.53125C0.85462 5.4983 0.875154 5.46534 0.897461 5.43359C0.912292 5.41249 0.928788 5.39262 0.944336 5.37207C0.966199 5.34317 0.987506 5.31389 1.01074 5.28613C1.09421 5.18642 1.18642 5.09421 1.28613 5.01074C1.31389 4.98751 1.34317 4.9662 1.37207 4.94434C1.39262 4.92879 1.41248 4.91229 1.43359 4.89746C1.46534 4.87515 1.4983 4.85462 1.53125 4.83398C1.55735 4.81764 1.58353 4.80139 1.61035 4.78613C1.6402 4.76915 1.67047 4.7529 1.70117 4.7373C1.72659 4.72439 1.75235 4.71213 1.77832 4.7002C1.81299 4.68426 1.84818 4.66943 1.88379 4.65527C1.91331 4.64354 1.94349 4.63352 1.97363 4.62305C2.00634 4.61168 2.03888 4.59968 2.07227 4.58984C2.1034 4.58067 2.1353 4.57421 2.16699 4.56641C2.20102 4.55802 2.2349 4.54877 2.26953 4.54199C2.33499 4.52919 2.40135 4.51856 2.46875 4.51172L2.69336 4.5H4V3L4.01074 2.7959C4.1062 1.85435 4.85435 1.1062 5.7959 1.01074L6 1H10L10.2041 1.01074ZM5.85254 7.26465C5.47192 7.34097 5.21637 7.69299 5.25293 8.07129L5.26465 8.14746L5.76465 10.6475L5.7832 10.7217C5.89507 11.0849 6.26671 11.3115 6.64746 11.2354C7.02808 11.159 7.28363 10.807 7.24707 10.4287L7.23535 10.3525L6.73535 7.85254L6.7168 7.77832C6.60493 7.41506 6.23329 7.1885 5.85254 7.26465ZM10.1475 7.26465C9.74142 7.18344 9.34605 7.44658 9.26465 7.85254L8.76465 10.3525C8.68344 10.7586 8.94658 11.1539 9.35254 11.2354C9.75858 11.3166 10.1539 11.0534 10.2354 10.6475L10.7354 8.14746C10.8166 7.74142 10.5534 7.34605 10.1475 7.26465ZM6 2.5C5.72386 2.5 5.5 2.72386 5.5 3V4.5H10.5V3C10.5 2.72386 10.2761 2.5 10 2.5H6Z"/></svg>'
    },
    'quest.png':{
        outline:'<svg width="15" height="20" viewBox="0 0 15 20" fill="white" fill-opacity="0.64" fill-rule="evenodd" clip-rule="evenodd"><path d="M12.2956 1.875C12.7536 1.875 13.125 2.24635 13.125 2.70444C13.125 2.91078 13.0481 3.10971 12.9093 3.26239L12.466 3.75H2.53399L2.0907 3.26239C1.95191 3.10971 1.875 2.91078 1.875 2.70444C1.875 2.24635 2.24635 1.875 2.70444 1.875H12.2956ZM4.23853 5.625L6.89346 8.54542C7.01191 8.67572 7.17983 8.75 7.35592 8.75H7.5H7.64407C7.82016 8.75 7.98808 8.67572 8.10654 8.54542L10.7615 5.625H4.23853ZM5.05326 9.30858L1.875 5.8125V8.12756C1.875 8.27829 1.92947 8.42393 2.02837 8.53767L3.58888 10.3323C4.01707 9.91791 4.5109 9.57099 5.05326 9.30858ZM2.4546 11.8853L0.613486 9.76801C0.217875 9.31306 0 8.73046 0 8.12756V2.70444V2.5C0 1.11929 1.11929 0 2.5 0H2.70444H12.2956H12.5C13.8807 0 15 1.11929 15 2.5V2.70444V8.12756C15 8.73046 14.7821 9.31306 14.3865 9.76801L12.5454 11.8853C12.9165 12.6358 13.125 13.4811 13.125 14.375C13.125 17.4816 10.6066 20 7.5 20C4.3934 20 1.875 17.4816 1.875 14.375C1.875 13.4811 2.08353 12.6358 2.4546 11.8853ZM11.4111 10.3323C10.9829 9.91791 10.4891 9.57099 9.94674 9.30858L13.125 5.8125V8.12756C13.125 8.27829 13.0705 8.42393 12.9716 8.53767L11.4111 10.3323ZM11.25 14.375C11.25 16.4461 9.57106 18.125 7.5 18.125C5.42893 18.125 3.75 16.4461 3.75 14.375C3.75 12.3039 5.42893 10.625 7.5 10.625C9.57106 10.625 11.25 12.3039 11.25 14.375Z"/></svg>',
        filled:'<svg width="15" height="20" viewBox="0 0 15 20" fill="white"><path d="M13 0C14.1046 2.31931e-06 15 0.895432 15 2V8.31445L14.9922 8.49414C14.9546 8.91158 14.7858 9.30839 14.5088 9.62695L12.5439 11.8848C12.9153 12.6356 13.125 13.4807 13.125 14.375C13.125 17.4816 10.6066 20 7.5 20C4.3934 20 1.875 17.4816 1.875 14.375C1.875 13.4811 2.08406 12.6362 2.45508 11.8857L0.491211 9.62695C0.174722 9.26299 0 8.79677 0 8.31445V2C1.28853e-07 0.895431 0.895431 0 2 0H13ZM7.5 10.625C6.50544 10.625 5.55189 11.0204 4.84863 11.7236C4.14537 12.4269 3.75 13.3804 3.75 14.375C3.75 14.8928 4.16973 15.3125 4.6875 15.3125C5.20527 15.3125 5.625 14.8928 5.625 14.375C5.625 13.8777 5.8222 13.4005 6.17383 13.0488C6.52546 12.6972 7.00272 12.5 7.5 12.5C8.01776 12.5 8.4375 12.0803 8.4375 11.5625C8.4375 11.0447 8.01776 10.625 7.5 10.625ZM1.5 8.31445C1.5 8.43503 1.54392 8.55159 1.62305 8.64258L3.32715 10.6016C3.81092 10.0669 4.3966 9.62611 5.05273 9.30859L1.5 5.39941V8.31445ZM9.94531 9.30762C10.602 9.62511 11.1877 10.0666 11.6719 10.6016L13.377 8.64258C13.4561 8.55159 13.5 8.43503 13.5 8.31445V5.39941L9.94531 9.30762ZM6.63281 8.81543C6.91542 8.77171 7.20514 8.75 7.5 8.75C7.79453 8.75 8.0839 8.7718 8.36621 8.81543L11.4385 5.4375H3.56152L6.63281 8.81543ZM2.7041 1.5C2.03918 1.50018 1.50018 2.03918 1.5 2.7041C1.5 3.00373 1.61193 3.29294 1.81348 3.51465L2.19824 3.9375H12.8018L13.1865 3.51465C13.3881 3.29294 13.5 3.00373 13.5 2.7041C13.4998 2.0807 13.0261 1.56762 12.4189 1.50586L12.2959 1.5H2.7041Z"/></svg>'
    },
    'games.png':{
        outline:'<svg width="16" height="18" viewBox="0 0 15 18" fill="white" fill-opacity="0.65"><path d="M15 14.5C15 16.1569 13.6569 17.5 12 17.5L3 17.5C1.34315 17.5 2.47436e-07 16.1569 -6.33815e-07 14.5L-1.31134e-07 3C-5.87109e-08 1.34315 1.34315 2.24747e-06 3 -5.24537e-07L12 -1.31134e-07C13.6569 1.48108e-06 15 1.34315 15 3L15 14.5ZM10.8633 8.22266C9.32461 7.36784 8.23878 5.88028 7.89355 4.1543L7.8125 3.75L7.1875 3.75L7.10645 4.1543C6.76122 5.88028 5.67539 7.36784 4.13672 8.22266L3.75 8.4375L3.75 9.0625L4.13672 9.27734C5.67539 10.1322 6.76122 11.6197 7.10644 13.3457L7.1875 13.75L7.8125 13.75L7.89355 13.3457C8.23878 11.6197 9.32461 10.1322 10.8633 9.27734L11.25 9.0625L11.25 8.4375L10.8633 8.22266Z"/></svg>',
        filled:'<svg width="16" height="18" viewBox="0 0 15 18" fill="white" fill-opacity="1"><path d="M15 14.5C15 16.1569 13.6569 17.5 12 17.5L3 17.5C1.34315 17.5 2.47436e-07 16.1569 -6.33815e-07 14.5L-1.31134e-07 3C-5.87109e-08 1.34315 1.34315 2.24747e-06 3 -5.24537e-07L12 -1.31134e-07C13.6569 1.48108e-06 15 1.34315 15 3L15 14.5ZM10.8633 8.22266C9.32461 7.36784 8.23878 5.88028 7.89355 4.1543L7.8125 3.75L7.1875 3.75L7.10645 4.1543C6.76122 5.88028 5.67539 7.36784 4.13672 8.22266L3.75 8.4375L3.75 9.0625L4.13672 9.27734C5.67539 10.1322 6.76122 11.6197 7.10644 13.3457L7.1875 13.75L7.8125 13.75L7.89355 13.3457C8.23878 11.6197 9.32461 10.1322 10.8633 9.27734L11.25 9.0625L11.25 8.4375L10.8633 8.22266Z"/></svg>'
    },
    'ref.png':{
        outline:'<svg width="21" height="20" viewBox="0 0 21 20" fill="white" fill-opacity="0.64" fill-rule="evenodd" clip-rule="evenodd"><path d="M7.375 7.5C8.41053 7.5 9.25 6.66053 9.25 5.625C9.25 4.58947 8.41053 3.75 7.375 3.75C6.33946 3.75 5.5 4.58947 5.5 5.625C5.5 6.66053 6.33946 7.5 7.375 7.5ZM7.375 9.375C9.44606 9.375 11.125 7.69607 11.125 5.625C11.125 3.55393 9.44606 1.875 7.375 1.875C5.30393 1.875 3.625 3.55393 3.625 5.625C3.625 7.69607 5.30393 9.375 7.375 9.375ZM3.58906 12.9823C2.61779 13.6569 2.375 14.3106 2.375 14.6154C2.375 15.173 2.82702 15.625 3.38462 15.625H11.3654C11.923 15.625 12.375 15.173 12.375 14.6154C12.375 14.3106 12.1322 13.6569 11.1609 12.9823C10.2406 12.3432 8.89786 11.875 7.375 11.875C5.85214 11.875 4.50938 12.3432 3.58906 12.9823ZM0.5 14.6154C0.5 12.3077 3.59375 10 7.375 10C8.85111 10 10.2224 10.3517 11.3459 10.9177C12.3127 10.3572 13.5416 10 14.875 10C17.9687 10 20.5 11.9231 20.5 13.8461C20.5 15.1738 19.4238 16.25 18.0962 16.25H13.7425C13.2223 17.005 12.3516 17.5 11.3654 17.5H3.38462C1.79149 17.5 0.5 16.2085 0.5 14.6154ZM14.2389 14.375H18.0962C18.3882 14.375 18.625 14.1382 18.625 13.8461C18.625 13.7179 18.5048 13.2561 17.7649 12.7327C17.0718 12.2425 16.0463 11.875 14.875 11.875C14.2285 11.875 13.6265 11.9869 13.1002 12.1697C13.7579 12.8377 14.1678 13.6018 14.2389 14.375ZM16.125 6.25C16.125 6.94035 15.5654 7.5 14.875 7.5C14.1846 7.5 13.625 6.94035 13.625 6.25C13.625 5.55964 14.1846 5 14.875 5C15.5654 5 16.125 5.55964 16.125 6.25ZM18 6.25C18 7.97589 16.6009 9.375 14.875 9.375C13.1491 9.375 11.75 7.97589 11.75 6.25C11.75 4.52411 13.1491 3.125 14.875 3.125C16.6009 3.125 18 4.52411 18 6.25Z"/></svg>',
        filled:'<svg width="21" height="20" viewBox="0 0 21 20" fill="white"><path d="M7.375 10C11.1562 10 14.2499 12.3076 14.25 14.6152C14.25 16.2084 12.9584 17.5 11.3652 17.5H3.38477C1.79164 17.5 0.5 16.2084 0.5 14.6152C0.500129 12.3076 3.59383 10 7.375 10ZM14.875 10C17.9687 10 20.5 11.9236 20.5 13.8467C20.4997 15.1739 19.4239 16.2497 18.0967 16.25H15.1631C15.3792 15.7485 15.5 15.196 15.5 14.6152C15.4999 12.8954 14.3726 11.4076 12.9434 10.415C12.8892 10.3774 12.8329 10.3413 12.7773 10.3047C13.4263 10.1108 14.1346 10 14.875 10ZM7.375 1.875C9.44606 1.875 11.125 3.55393 11.125 5.625C11.125 7.69607 9.44606 9.375 7.375 9.375C5.30393 9.375 3.625 7.69607 3.625 5.625C3.625 3.55393 5.30393 1.875 7.375 1.875ZM14.876 3.125C16.6014 3.12553 18.001 4.52444 18.001 6.25C18.001 7.97556 16.6014 9.37447 14.876 9.375C13.1501 9.375 11.751 7.97589 11.751 6.25C11.751 4.52411 13.1501 3.125 14.876 3.125Z"/></svg>'
    },
    'profil.png':{
        outline:'<svg width="18" height="18" viewBox="0 0 18 18" fill="white" fill-opacity="0.64" fill-rule="evenodd" clip-rule="evenodd"><path d="M11.5 4.625C11.5 6.00571 10.3807 7.125 9 7.125C7.61929 7.125 6.5 6.00571 6.5 4.625C6.5 3.24429 7.61929 2.125 9 2.125C10.3807 2.125 11.5 3.24429 11.5 4.625ZM13.375 4.625C13.375 7.04124 11.4162 9 9 9C6.58375 9 4.625 7.04124 4.625 4.625C4.625 2.20875 6.58375 0.25 9 0.25C11.4162 0.25 13.375 2.20875 13.375 4.625ZM2.125 14.625C2.125 14.3693 2.40034 13.6139 3.77445 12.8016C5.0469 12.0494 6.89973 11.5 9 11.5C11.1003 11.5 12.9531 12.0494 14.2255 12.8016C15.5997 13.6139 15.875 14.3693 15.875 14.625C15.875 15.3154 15.3154 15.875 14.625 15.875H3.375C2.68464 15.875 2.125 15.3154 2.125 14.625ZM9 9.625C4.1875 9.625 0.25 12.125 0.25 14.625C0.25 16.3509 1.64911 17.75 3.375 17.75H14.625C16.3509 17.75 17.75 16.3509 17.75 14.625C17.75 12.125 13.8125 9.625 9 9.625Z"/></svg>',
        filled:'<svg width="20" height="20" viewBox="0 0 12 12" fill="white" fill-opacity="1"><path d="M6 6.375C8.8875 6.375 11.25 7.875 11.25 9.375C11.25 10.4105 10.4105 11.25 9.375 11.25H2.625C1.58947 11.25 0.750001 10.4105 0.75 9.375C0.75 7.875 3.1125 6.375 6 6.375ZM6 0.75C7.44975 0.750001 8.625 1.92525 8.625 3.375C8.625 4.82475 7.44975 6 6 6C4.55025 6 3.375 4.82475 3.375 3.375C3.375 1.92525 4.55025 0.75 6 0.75Z"/></svg>'
    },
    'cases.png':{
        outline:'<svg width="21" height="20" viewBox="0 0 21 20" fill="white" fill-opacity="0.64" fill-rule="evenodd" clip-rule="evenodd"><path d="M15.5 5.625H17.1339C18.6478 5.625 19.875 6.85223 19.875 8.36609C19.875 8.62079 19.8395 8.87424 19.7695 9.11913L18.1521 14.7802C17.6921 16.3901 16.2207 17.5 14.5464 17.5H8H6.45363C4.77933 17.5 3.30788 16.3901 2.84791 14.7802L1.23047 9.11913C1.1605 8.87424 1.125 8.62079 1.125 8.36609C1.125 6.85223 2.35223 5.625 3.8661 5.625H5.5L5.5 3.75C5.5 2.36929 6.61929 1.25 8 1.25H13C14.3807 1.25 15.5 2.36929 15.5 3.75V5.625ZM7.375 5.625V3.75C7.375 3.40482 7.65482 3.125 8 3.125L13 3.125C13.3452 3.125 13.625 3.40482 13.625 3.75V5.625H8H7.375ZM14.5464 15.625H8H6.45363C5.61648 15.625 4.88075 15.07 4.65077 14.2651L3.03332 8.60403C3.01122 8.52665 3 8.44657 3 8.36609C3 7.88776 3.38776 7.5 3.8661 7.5H8H17.1339C17.6122 7.5 18 7.88776 18 8.36609C18 8.44657 17.9888 8.52665 17.9667 8.60403L16.3492 14.2651C16.1192 15.07 15.3835 15.625 14.5464 15.625ZM8.80886 14.0443C8.30115 14.1458 7.80725 13.8166 7.7057 13.3089L7.0807 10.1839C6.97916 9.67614 7.30843 9.18225 7.81614 9.0807C8.32385 8.97916 8.81775 9.30843 8.91929 9.81614L9.54429 12.9411C9.64583 13.4489 9.31657 13.9427 8.80886 14.0443ZM13.9193 10.1839C14.0208 9.67614 13.6916 9.18225 13.1839 9.0807C12.6761 8.97916 12.1822 9.30843 12.0807 9.81614L11.4557 12.9411C11.3542 13.4489 11.6834 13.9427 12.1911 14.0443C12.6989 14.1458 13.1927 13.8166 13.2943 13.3089L13.9193 10.1839Z"/></svg>',
        filled:'<svg width="20" height="20" viewBox="0 0 16 16" fill="white"><path d="M10.2041 1.01074C11.1457 1.1062 11.8938 1.85435 11.9893 2.7959L12 3V4.5H13.3066C14.5177 4.5 15.5 5.48227 15.5 6.69336C15.5 6.89679 15.4719 7.0993 15.416 7.29492L14.1221 11.8242C13.7541 13.1121 12.5767 13.9999 11.2373 14H4.7627L4.51367 13.9893C4.43572 13.9828 4.35863 13.9723 4.28223 13.96C4.23682 13.9526 4.19224 13.942 4.14746 13.9326C4.1149 13.9258 4.08201 13.921 4.0498 13.9131C4.00664 13.9025 3.96435 13.8894 3.92188 13.877C3.88988 13.8676 3.85775 13.859 3.82617 13.8486C3.78096 13.8338 3.73668 13.8168 3.69238 13.7998C3.66569 13.7896 3.63865 13.7805 3.6123 13.7695C3.56527 13.75 3.5195 13.7279 3.47363 13.7061C3.45047 13.695 3.42714 13.6845 3.4043 13.6729C3.35865 13.6496 3.31386 13.6251 3.26953 13.5996C3.24724 13.5868 3.22507 13.5739 3.20312 13.5605C3.16484 13.5372 3.12702 13.5133 3.08984 13.4883C3.06052 13.4686 3.03153 13.4485 3.00293 13.4277C2.96981 13.4037 2.93739 13.3789 2.90527 13.3535C2.87656 13.3309 2.84819 13.3079 2.82031 13.2842C2.79079 13.2591 2.76195 13.2333 2.7334 13.207C2.70135 13.1776 2.67042 13.147 2.63965 13.1162C2.61803 13.0945 2.59616 13.0731 2.5752 13.0508C2.54349 13.017 2.51258 12.9825 2.48242 12.9473C2.46126 12.9225 2.4403 12.8976 2.41992 12.8721C2.38916 12.8336 2.35997 12.794 2.33105 12.7539C2.3151 12.7318 2.29858 12.7101 2.2832 12.6875C2.25457 12.6455 2.22773 12.6022 2.20117 12.5586C2.18578 12.5333 2.16995 12.5082 2.15527 12.4824C2.13114 12.44 2.10905 12.3963 2.08691 12.3525C2.07348 12.3259 2.05955 12.2996 2.04688 12.2725C1.97985 12.1293 1.92242 11.9799 1.87793 11.8242L0.583984 7.29492L0.547852 7.14746C0.534092 7.08254 0.523439 7.01704 0.515625 6.95117C0.513414 6.93264 0.511503 6.91409 0.509766 6.89551C0.503534 6.82837 0.500015 6.76093 0.5 6.69336C0.5 6.56111 0.513698 6.43147 0.536133 6.30566C0.538278 6.29363 0.539652 6.28149 0.541992 6.26953C0.54877 6.2349 0.558019 6.20102 0.566406 6.16699C0.574215 6.1353 0.580674 6.1034 0.589844 6.07227C0.599682 6.03888 0.611683 6.00634 0.623047 5.97363C0.633516 5.94349 0.643543 5.91331 0.655273 5.88379C0.669426 5.84818 0.684259 5.81299 0.700195 5.77832C0.712132 5.75235 0.724394 5.72659 0.737305 5.70117C0.752904 5.67047 0.769152 5.6402 0.786133 5.61035C0.801391 5.58353 0.817642 5.55735 0.833984 5.53125C0.85462 5.4983 0.875154 5.46534 0.897461 5.43359C0.912292 5.41249 0.928788 5.39262 0.944336 5.37207C0.966199 5.34317 0.987506 5.31389 1.01074 5.28613C1.09421 5.18642 1.18642 5.09421 1.28613 5.01074C1.31389 4.98751 1.34317 4.9662 1.37207 4.94434C1.39262 4.92879 1.41248 4.91229 1.43359 4.89746C1.46534 4.87515 1.4983 4.85462 1.53125 4.83398C1.55735 4.81764 1.58353 4.80139 1.61035 4.78613C1.6402 4.76915 1.67047 4.7529 1.70117 4.7373C1.72659 4.72439 1.75235 4.71213 1.77832 4.7002C1.81299 4.68426 1.84818 4.66943 1.88379 4.65527C1.91331 4.64354 1.94349 4.63352 1.97363 4.62305C2.00634 4.61168 2.03888 4.59968 2.07227 4.58984C2.1034 4.58067 2.1353 4.57421 2.16699 4.56641C2.20102 4.55802 2.2349 4.54877 2.26953 4.54199C2.33499 4.52919 2.40135 4.51856 2.46875 4.51172L2.69336 4.5H4V3L4.01074 2.7959C4.1062 1.85435 4.85435 1.1062 5.7959 1.01074L6 1H10L10.2041 1.01074ZM5.85254 7.26465C5.47192 7.34097 5.21637 7.69299 5.25293 8.07129L5.26465 8.14746L5.76465 10.6475L5.7832 10.7217C5.89507 11.0849 6.26671 11.3115 6.64746 11.2354C7.02808 11.159 7.28363 10.807 7.24707 10.4287L7.23535 10.3525L6.73535 7.85254L6.7168 7.77832C6.60493 7.41506 6.23329 7.1885 5.85254 7.26465ZM10.1475 7.26465C9.74142 7.18344 9.34605 7.44658 9.26465 7.85254L8.76465 10.3525C8.68344 10.7586 8.94658 11.1539 9.35254 11.2354C9.75858 11.3166 10.1539 11.0534 10.2354 10.6475L10.7354 8.14746C10.8166 7.74142 10.5534 7.34605 10.1475 7.26465ZM6 2.5C5.72386 2.5 5.5 2.72386 5.5 3V4.5H10.5V3C10.5 2.72386 10.2761 2.5 10 2.5H6Z"/></svg>'
    },
    'moon.png':{
        outline:'<svg width="16" height="18" viewBox="0 0 15 18" fill="white" fill-opacity="0.65"><path d="M15 14.5C15 16.1569 13.6569 17.5 12 17.5L3 17.5C1.34315 17.5 2.47436e-07 16.1569 -6.33815e-07 14.5L-1.31134e-07 3C-5.87109e-08 1.34315 1.34315 2.24747e-06 3 -5.24537e-07L12 -1.31134e-07C13.6569 1.48108e-06 15 1.34315 15 3L15 14.5ZM10.8633 8.22266C9.32461 7.36784 8.23878 5.88028 7.89355 4.1543L7.8125 3.75L7.1875 3.75L7.10645 4.1543C6.76122 5.88028 5.67539 7.36784 4.13672 8.22266L3.75 8.4375L3.75 9.0625L4.13672 9.27734C5.67539 10.1322 6.76122 11.6197 7.10644 13.3457L7.1875 13.75L7.8125 13.75L7.89355 13.3457C8.23878 11.6197 9.32461 10.1322 10.8633 9.27734L11.25 9.0625L11.25 8.4375L10.8633 8.22266Z"/></svg>',
        filled:'<svg width="16" height="18" viewBox="0 0 15 18" fill="white" fill-opacity="1"><path d="M15 14.5C15 16.1569 13.6569 17.5 12 17.5L3 17.5C1.34315 17.5 2.47436e-07 16.1569 -6.33815e-07 14.5L-1.31134e-07 3C-5.87109e-08 1.34315 1.34315 2.24747e-06 3 -5.24537e-07L12 -1.31134e-07C13.6569 1.48108e-06 15 1.34315 15 3L15 14.5ZM10.8633 8.22266C9.32461 7.36784 8.23878 5.88028 7.89355 4.1543L7.8125 3.75L7.1875 3.75L7.10645 4.1543C6.76122 5.88028 5.67539 7.36784 4.13672 8.22266L3.75 8.4375L3.75 9.0625L4.13672 9.27734C5.67539 10.1322 6.76122 11.6197 7.10644 13.3457L7.1875 13.75L7.8125 13.75L7.89355 13.3457C8.23878 11.6197 9.32461 10.1322 10.8633 9.27734L11.25 9.0625L11.25 8.4375L10.8633 8.22266Z"/></svg>'
    }
};

function upgradeNavIcons(){
    // Bottom nav icons
    document.querySelectorAll('.nav-item').forEach(function(item){
        var wrap=item.querySelector('.nav-icon');
        if(!wrap)return;
        var img=wrap.querySelector('img');
        if(!img)return;
        var src=img.getAttribute('src')||'';
        var filename=src.split('/').pop();
        var config=NAV_ICONS[filename];
        if(!config)return;
        var isActive=item.classList.contains('active');
        wrap.innerHTML=isActive?config.filled:config.outline;
        wrap.classList.add('nav-icon-svg');
        // Store config for dynamic switching
        wrap.setAttribute('data-icon-key',filename);
    });
    // Desktop nav links
    document.querySelectorAll('.desktop-nav-link').forEach(function(link){
        var img=link.querySelector('img');
        if(!img)return;
        var src=img.getAttribute('src')||'';
        var filename=src.split('/').pop();
        var config=NAV_ICONS[filename];
        if(!config)return;
        var isActive=link.classList.contains('active');
        var span=document.createElement('span');
        span.className='nav-icon-svg';
        span.setAttribute('data-icon-key',filename);
        span.innerHTML=isActive?config.filled:config.outline;
        img.replaceWith(span);
    });
}

// ============ UNIFIED MOBILE HEADER ============
function injectMobileHeader(){
    if(document.querySelector('.header-v2'))return;
    const container=document.querySelector('.container')||document.querySelector('.games-container')||document.querySelector('.topup-container')||document.querySelector('.ref-page');
    if(!container)return;
    // Hide old-style headers
    const oldH=container.querySelector('.header');if(oldH)oldH.style.display='none';
    const topupH=container.querySelector('.topup-header');if(topupH)topupH.style.display='none';
    const refBar=container.querySelector('.ref-top-bar');if(refBar)refBar.style.display='none';
    const hdr=document.createElement('div');
    hdr.className='header-v2';
    hdr.innerHTML='<div class="header-avatar-wrap" onclick="window.location.href=\'/inventory\'">'
        +'<img class="user-avatar" src="" alt="">'
        +'<div class="avatar-wallet-overlay" id="avatarWallet" style="display:none"></div></div>'
        +'<div class="balance-pill">'
        +'<div class="balance-section ton-balance" onclick="showTonTopup()">'
        +'<span class="balance-val" id="tonBalVal">0.00</span>'
        +'<img src="/static/img/ton.svg" alt="TON"></div>'
        +'<div class="balance-divider"></div>'
        +'<div class="balance-section star-balance" onclick="openBalanceAction()">'
        +'<span class="balance-val balance-amount" style="color:var(--gold)">0</span>'
        +'<img src="/static/img/star.svg" alt="⭐"></div></div>'
        +'<button class="balance-plus-btn" onclick="window.location.href=\'/topup\'">+</button>'
        +'<div class="online-badge" id="onlineBadge">'
        +'<span class="online-dot"></span>'
        +'<span class="online-count" id="onlineCount">...</span></div>';
    container.insertBefore(hdr,container.firstChild);
}

// ============ DESKTOP NAVIGATION ============
function injectDesktopNav(){
    if(document.getElementById('desktopNav'))return;
    const path=window.location.pathname;
    function navActive(p){
        if(p==='/cases'&&(path==='/'||path==='/cases'))return' active';
        if(p==='/games'&&path==='/games')return' active';
        if(p==='/scratch'&&path==='/scratch')return' active';
        if(p==='/market'&&path==='/market')return' active';
        if(p==='/referral'&&path==='/referral')return' active';
        if(p==='/inventory'&&path==='/inventory')return' active';
        if(p==='/topup'&&path==='/topup')return' active';
        return'';
    }
    const nav=document.createElement('nav');
    nav.className='desktop-nav';
    nav.id='desktopNav';
    nav.innerHTML='<div class="desktop-nav-inner">'
        +'<a class="desktop-nav-logo" href="/cases">'
        +'<img src="/static/img/logo.png" alt="Luna Gifts">'
        +'<span>Luna Gifts</span></a>'
        +'<div class="desktop-nav-links">'
        +'<a class="desktop-nav-link'+navActive('/cases')+'" href="/cases"><img src="/static/img/cases.png" alt="">КЕЙСЫ</a>'
        +'<a class="desktop-nav-link'+navActive('/games')+'" href="/games"><img src="/static/img/games.png" alt="">ИГРЫ</a>'
        +'<a class="desktop-nav-link'+navActive('/scratch')+'" href="/scratch"><img src="/static/img/moon.png" alt="">СКРЕТЧИ</a>'
        +'<a class="desktop-nav-link'+navActive('/market')+'" href="/market"><img src="/static/img/gift.png" alt="">МАРКЕТ</a>'
        +'<a class="desktop-nav-link'+navActive('/referral')+'" href="/referral"><img src="/static/img/ref.png" alt="">ДРУЗЬЯ</a>'
        +'</div>'
        +'<div class="desktop-nav-right">'
        +'<div class="desktop-nav-balance ton-bal" onclick="showTonTopup()">'
        +'<img src="/static/img/ton.svg" alt="TON"><span class="desktop-ton-val" id="desktopTonVal">0.00</span></div>'
        +'<div class="desktop-nav-balance star-bal" onclick="window.location.href=\'/topup\'">'
        +'<img src="/static/img/star.svg" alt="Stars"><span class="balance-amount desktop-star-val" id="desktopStarVal">0</span></div>'
        +'<button class="desktop-nav-plus" onclick="window.location.href=\'/topup\'">+</button>'
        +'<img class="desktop-nav-avatar user-avatar" id="desktopAvatar" src="" alt="" onclick="window.location.href=\'/inventory\'">'
        +'</div></div>';
    document.body.insertBefore(nav,document.body.firstChild);
}

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
