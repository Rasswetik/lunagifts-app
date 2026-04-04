/* ═══════════════════════════════════════════
   CRASH GAME — Luna Gifts
   Client-side logic
   ═══════════════════════════════════════════ */

/* ─── Gift data for conveyor (sorted cheapest→expensive) ─── */
let CRASH_GIFTS = [];
let sortedGifts = [];
const CRASH_GIFT_MIN = 50;

/* ─── State ─── */
let betTab = 'gift';
let selectedGift = null;
let gameState = { status: 'waiting', multiplier: 1.00, game_id: 0, hash: '', countdown: 0, start_time: 0, server_time: 0 };
let prevGameId = 0;
let myBet = null;
let displayMult = 1.00;
let serverMult = 1.00;
let statusPollTimer = null;
let betsPollTimer = null;
let historyTimer = null;
let rafId = null;
let crashDone = false;
let lastPollTime = 0;
let pingMs = 0;
let userInventory = [];
let countdownTarget = 0;
let flyStartLocal = 0;   // local timestamp when flying started
let flyStartServer = 0;  // server start_time of current flight
let timeOffset = 0;      // server_time - local_time
let lastBetAmount = 0;   // preserved after cashout for carousel continuity
let lastCountdownSec = -1; // for countdown vibration

/* ─── Load gifts data ─── */
async function loadCrashGifts() {
    try {
        const r = await fetch('/api/gifts');
        const data = await r.json();
        const all = (data.gifts || data || []);
        // NFT gifts (have slug, no telegram_gift_id) + crash_eligible gifts
        CRASH_GIFTS = all.filter(g => g.value && g.value >= CRASH_GIFT_MIN && (g.crash_eligible || (g.slug && !g.telegram_gift_id)));
        // Build +10% progression chain
        const eligible = [...CRASH_GIFTS].sort((a, b) => a.value - b.value);
        sortedGifts = [];
        if (eligible.length) {
            let threshold = CRASH_GIFT_MIN;
            for (const g of eligible) {
                if (g.value >= threshold) {
                    // Use local image first, fallback to NFT image
                    g._conveyorImg = g.image || ('/static/img/nft/' + g.slug + '.jpg');
                    sortedGifts.push(g);
                    threshold = Math.ceil(g.value * 1.10);
                }
            }
        }
    } catch (e) {
        console.error('Failed to load gifts:', e);
    }
}

/* ─── Load user inventory for gift betting ─── */
async function loadUserInventory() {
    if (!currentUser) return;
    try {
        const r = await fetch('/api/inventory/' + currentUser.telegram_id);
        const data = await r.json();
        userInventory = (Array.isArray(data) ? data : data.items || []).filter(i => (i.item_type || i.type) === 'gift');
    } catch (e) {
        userInventory = [];
    }
}

/* ─── Build gift carousel (3 visible: left + center + right) ─── */
let carouselIdx = 0;
let carouselAnimating = false;

function buildConveyor() {
    const container = document.getElementById('giftsCarousel');
    if (!sortedGifts.length) return;
    container.innerHTML = '';
    carouselIdx = 0;
    renderCarouselSlides();
}

/* Jump carousel to the correct gift for a given bet amount (no animation) */
function initCarouselForBet(betAmount) {
    if (!sortedGifts.length || !betAmount) return;
    const currentValue = betAmount * 1.0; // at mult=1.0
    let targetIdx = 0;
    for (let i = 0; i < sortedGifts.length; i++) {
        if (currentValue >= sortedGifts[i].value) targetIdx = i + 1;
        else break;
    }
    if (targetIdx >= sortedGifts.length) targetIdx = sortedGifts.length - 1;
    carouselIdx = targetIdx;
    carouselAnimating = false;
    renderCarouselSlides();
    // Reset all fills to empty
    document.querySelectorAll('.crash-gift-slide').forEach(slide => {
        slide.classList.remove('completed');
        const fmImg = slide.querySelector('.gift-fill-mask img');
        if (fmImg) fmImg.style.clipPath = 'inset(100% 0 0 0)';
    });
    // Mark gifts before center as completed
    document.querySelectorAll('.crash-gift-slide.left').forEach(slide => {
        slide.classList.add('completed');
        const fmImg = slide.querySelector('.gift-fill-mask img');
        if (fmImg) fmImg.style.clipPath = 'inset(0 0 0 0)';
    });
    // Apply initial partial fill to center based on bet amount
    const centerSlide = document.querySelector('.crash-gift-slide.center');
    if (centerSlide && sortedGifts[carouselIdx]) {
        const val = sortedGifts[carouselIdx].value;
        const prevVal = carouselIdx > 0 ? sortedGifts[carouselIdx - 1].value : 0;
        const betValue = betAmount * 1.0;
        if (betValue >= val) {
            centerSlide.classList.add('completed');
            const fmImg = centerSlide.querySelector('.gift-fill-mask img');
            if (fmImg) fmImg.style.clipPath = 'inset(0 0 0 0)';
        } else {
            const range = val - prevVal;
            const fillPct = range > 0 ? Math.min(1, Math.max(0, (betValue - prevVal) / range)) : 0;
            const fmImg = centerSlide.querySelector('.gift-fill-mask img');
            if (fmImg) fmImg.style.clipPath = 'inset(' + ((1 - fillPct) * 100) + '% 0 0 0)';
        }
    }
}

function renderCarouselSlides() {
    const container = document.getElementById('giftsCarousel');
    if (!container || !sortedGifts.length) return;
    container.innerHTML = '';

    function makeSlide(g, cls, idx) {
        const slide = document.createElement('div');
        slide.className = 'crash-gift-slide ' + cls;
        if (idx !== undefined) {
            slide.dataset.idx = idx;
            slide.dataset.value = g.value;
        }
        slide.innerHTML = `
            <div class="gift-img-wrap">
                <img class="gift-img-gray" src="${g._conveyorImg || g.image}" alt="${g.name}"
                     onerror="this.src='${g.image}'">
                <div class="gift-fill-mask">
                    <img src="${g._conveyorImg || g.image}" alt=""
                         onerror="this.src='${g.image}'">
                </div>
            </div>
        `;
        container.appendChild(slide);
        return slide;
    }

    // Left: show bet gift image if gift bet, otherwise previous completed gift
    if (carouselIdx > 0) {
        const betGiftImg = myBet && myBet.type === 'gift' && myBet.gift && myBet.gift.image;
        if (betGiftImg) {
            const g = sortedGifts[carouselIdx - 1];
            const slide = document.createElement('div');
            slide.className = 'crash-gift-slide left completed';
            slide.dataset.idx = carouselIdx - 1;
            slide.dataset.value = g.value;
            slide.innerHTML = `
                <div class="gift-img-wrap">
                    <img class="gift-img-gray" src="${betGiftImg}" alt=""
                         onerror="this.src='${g._conveyorImg || g.image}'">
                    <div class="gift-fill-mask">
                        <img src="${betGiftImg}" alt=""
                             onerror="this.src='${g._conveyorImg || g.image}'"
                             style="clip-path:inset(0 0 0 0)">
                    </div>
                </div>
            `;
            container.appendChild(slide);
        } else {
            const s = makeSlide(sortedGifts[carouselIdx - 1], 'left', carouselIdx - 1);
            s.classList.add('completed');
            const fmImg = s.querySelector('.gift-fill-mask img');
            if (fmImg) fmImg.style.clipPath = 'inset(0 0 0 0)';
        }
    }

    // Center: currently filling gift
    if (carouselIdx < sortedGifts.length) {
        makeSlide(sortedGifts[carouselIdx], 'center', carouselIdx);
    }

    // Right: next gift in chain
    if (carouselIdx + 1 < sortedGifts.length) {
        makeSlide(sortedGifts[carouselIdx + 1], 'right', carouselIdx + 1);
    }
}

/* ─── Update carousel based on multiplier ─── */
function updateConveyor(mult) {
    if (!sortedGifts.length) return;
    const betAmount = lastBetAmount || (myBet ? myBet.amount : 100);
    const currentValue = betAmount * mult;

    // Find last fully-earned gift
    let completedIdx = -1;
    for (let i = 0; i < sortedGifts.length; i++) {
        if (currentValue >= sortedGifts[i].value) completedIdx = i;
        else break;
    }

    // Active (filling) gift is one after the last completed
    let activeIdx = completedIdx + 1;
    if (activeIdx >= sortedGifts.length) activeIdx = sortedGifts.length - 1;

    // If active moved past current center, animate slide left
    if (activeIdx > carouselIdx && !carouselAnimating) {
        carouselAnimating = true;
        const container = document.getElementById('giftsCarousel');
        const oldLeft = document.querySelector('.crash-gift-slide.left');
        const oldCenter = document.querySelector('.crash-gift-slide.center');
        const oldRight = document.querySelector('.crash-gift-slide.right');

        // Old left slides out and gets removed after transition
        if (oldLeft) {
            oldLeft.classList.remove('left');
            oldLeft.classList.add('leaving-left');
            oldLeft.addEventListener('transitionend', () => oldLeft.remove(), {once:true});
            setTimeout(() => { if (oldLeft.parentNode) oldLeft.remove(); }, 700);
        }

        // Old center → left (completed)
        if (oldCenter) {
            oldCenter.classList.remove('center');
            oldCenter.classList.add('completed', 'left');
            const fmImg = oldCenter.querySelector('.gift-fill-mask img');
            if (fmImg) fmImg.style.clipPath = 'inset(0 0 0 0)';
        }

        // Old right → center
        if (oldRight) {
            oldRight.classList.remove('right');
            oldRight.classList.add('center');
            oldRight.dataset.idx = activeIdx;
            oldRight.dataset.value = sortedGifts[activeIdx].value;
        }

        carouselIdx = activeIdx;

        // Add new right slide: start offscreen, then animate to .right
        if (carouselIdx + 1 < sortedGifts.length && container) {
            const g = sortedGifts[carouselIdx + 1];
            const slide = document.createElement('div');
            slide.className = 'crash-gift-slide offscreen-right';
            slide.dataset.idx = carouselIdx + 1;
            slide.dataset.value = g.value;
            slide.innerHTML = `<div class="gift-img-wrap">
                <img class="gift-img-gray" src="${g._conveyorImg || g.image}" alt="${g.name}" onerror="this.src='${g.image}'">
                <div class="gift-fill-mask"><img src="${g._conveyorImg || g.image}" alt="" onerror="this.src='${g.image}'"></div>
            </div>`;
            container.appendChild(slide);
            // Two rAF frames to ensure offscreen class is painted before transitioning
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    slide.classList.remove('offscreen-right');
                    slide.classList.add('right');
                });
            });
        }

        // Unlock after transition duration
        setTimeout(() => { carouselAnimating = false; }, 650);
    }

    // Update fill clip-path — ONLY on center slide; left=completed, right=empty
    const slides = document.querySelectorAll('.crash-gift-slide');
    slides.forEach(slide => {
        const idx = parseInt(slide.dataset.idx);
        if (isNaN(idx)) return;
        const val = parseFloat(slide.dataset.value);
        const fmImg = slide.querySelector('.gift-fill-mask img');
        if (!fmImg) return;

        if (slide.classList.contains('left') || slide.classList.contains('leaving-left')) {
            // Left side = already completed
            slide.classList.add('completed');
            fmImg.style.clipPath = 'inset(0 0 0 0)';
        } else if (slide.classList.contains('right') || slide.classList.contains('offscreen-right')) {
            // Right side = stays gray/empty
            slide.classList.remove('completed');
            fmImg.style.clipPath = 'inset(100% 0 0 0)';
        } else if (slide.classList.contains('center')) {
            // Center — animate fill from bottom (progressive: relative to previous gift)
            if (currentValue >= val) {
                slide.classList.add('completed');
                fmImg.style.clipPath = 'inset(0 0 0 0)';
            } else {
                slide.classList.remove('completed');
                const prevVal = (idx > 0 && sortedGifts[idx - 1]) ? sortedGifts[idx - 1].value : 0;
                const range = val - prevVal;
                const fillPct = range > 0 ? Math.min(1, Math.max(0, (currentValue - prevVal) / range)) : 0;
                fmImg.style.clipPath = 'inset(' + ((1 - fillPct) * 100) + '% 0 0 0)';
            }
        }
    });

    // Dynamic color theme based on multiplier
    updateMultColor(mult);
}

/* ─── Reset carousel ─── */
function resetConveyor() {
    carouselAnimating = false;
    // If we have an active bet, jump to the correct gift for the bet amount
    const betAmt = lastBetAmount || (myBet ? myBet.amount : 0);
    if (betAmt && sortedGifts.length) {
        initCarouselForBet(betAmt);
    } else {
        carouselIdx = 0;
        lastBetAmount = 0;
        renderCarouselSlides();
        document.querySelectorAll('.crash-gift-slide').forEach(slide => {
            slide.classList.remove('completed');
            const fmImg = slide.querySelector('.gift-fill-mask img');
            if (fmImg) fmImg.style.clipPath = 'inset(100% 0 0 0)';
        });
    }
    // Reset color theme
    clearMultColor();
}

/* ─── Multiplier color themes ─── */
let currentMultColorClass = '';
function getMultColorClass(mult) {
    if (mult >= 25) return 'mult-cosmic';
    if (mult >= 15) return 'mult-sky';
    if (mult >= 10) return 'mult-legendary';
    if (mult >= 5)  return 'mult-gold';
    if (mult >= 3)  return 'mult-purple';
    if (mult >= 2)  return 'mult-blue';
    if (mult >= 1.5) return 'mult-green';
    return '';
}
function updateMultColor(mult) {
    const field = document.getElementById('crashField');
    const multEl = document.getElementById('crashMult');
    const statusEl = document.getElementById('crashStatusText');
    const newCls = getMultColorClass(mult);
    if (newCls !== currentMultColorClass) {
        if (currentMultColorClass) {
            field.classList.remove(currentMultColorClass);
            multEl.classList.remove(currentMultColorClass);
            statusEl.classList.remove(currentMultColorClass);
        }
        if (newCls) {
            field.classList.add(newCls);
            multEl.classList.add(newCls);
            statusEl.classList.add(newCls);
        }
        currentMultColorClass = newCls;
    }
}
function clearMultColor() {
    const field = document.getElementById('crashField');
    const multEl = document.getElementById('crashMult');
    const statusEl = document.getElementById('crashStatusText');
    if (currentMultColorClass) {
        field.classList.remove(currentMultColorClass);
        multEl.classList.remove(currentMultColorClass);
        statusEl.classList.remove(currentMultColorClass);
        currentMultColorClass = '';
    }
}

/* ─── Tab switching ─── */
function setBetTab(tab) {
    betTab = tab;
    document.querySelectorAll('.crash-bet-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.tab === tab)
    );
    document.getElementById('betBodyGift').style.display = tab === 'gift' ? 'block' : 'none';
    document.getElementById('betBodyStars').style.display = tab === 'stars' ? 'block' : 'none';
}

/* ─── Stars bet helpers ─── */
function setMaxStarsBet() {
    if (!currentUser) return;
    document.getElementById('starsBetInput').value = Math.floor(currentUser.balance);
}
function quickStarsBet(val) {
    document.getElementById('starsBetInput').value = val;
}

/* ─── Gift picker ─── */
function openGiftPicker() {
    const grid = document.getElementById('giftPickerGrid');
    if (!userInventory.length) {
        grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px 0;color:rgba(255,255,255,0.3);font-size:14px;">' + t('no_gifts') + '</div>';
    } else {
        grid.innerHTML = userInventory.map(item => {
            const name = item.gift_name || item.name || '';
            const img = item.gift_image || item.image || '';
            const price = item.gift_price || item.price || 0;
            return `<div class="crash-gift-pick-item" onclick="selectInventoryGift(${item.id}, '${name.replace(/'/g, "\\'")}', '${img}', ${price})">
                <img src="${img}" alt="${name}" loading="lazy">
                <div class="gift-pick-name">${name}</div>
                <div class="gift-pick-val"><img src="/static/img/star.svg" alt="">${price}</div>
            </div>`;
        }).join('');
    }
    document.getElementById('giftPickerModal').classList.add('show');
}
function closeGiftPicker() {
    document.getElementById('giftPickerModal').classList.remove('show');
}
function selectInventoryGift(id, name, image, value) {
    selectedGift = { id, name, image, value };
    document.getElementById('selectedGiftImg').src = image;
    document.getElementById('selectedGiftName').textContent = name;
    document.getElementById('selectedGiftVal').textContent = value;
    document.getElementById('selectedGiftPreview').style.display = 'flex';
    document.getElementById('selectGiftBtn').style.display = 'none';
    document.querySelector('.crash-bet-gift-row').style.display = 'none';
    closeGiftPicker();
}
function removeSelectedGift() {
    selectedGift = null;
    document.getElementById('selectedGiftPreview').style.display = 'none';
    document.getElementById('selectGiftBtn').style.display = 'inline-flex';
    document.querySelector('.crash-bet-gift-row').style.display = 'flex';
}

/* ─── Update top bar ─── */
function updateCrashTopBar() {
    if (!currentUser) return;
    document.getElementById('crashBalVal').textContent = Math.floor(currentUser.balance);
    const nickEl = document.getElementById('crashNick');
    if (nickEl) nickEl.textContent = currentUser.first_name || currentUser.username || 'Player';
    const avatarImg = document.getElementById('crashAvatarImg');
    if (currentUser.photo_url && avatarImg) {
        avatarImg.src = currentUser.photo_url;
    } else if (avatarImg) {
        avatarImg.style.display = 'none';
        const wrap = document.getElementById('crashAvatar');
        if (wrap && !wrap.querySelector('.crash-avatar-letter')) {
            const letter = document.createElement('div');
            letter.className = 'crash-avatar-letter';
            letter.style.cssText = 'width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:800;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;';
            letter.textContent = (currentUser.first_name || '?')[0];
            wrap.appendChild(letter);
        }
    }
}



/* ─── History colors ─── */
function getHistColor(mult) {
    if (mult >= 25) return 'cosmic';
    if (mult >= 15) return 'sky';
    if (mult >= 10) return 'legendary';
    if (mult <= 1.1) return 'gray';
    if (mult <= 1.7) return 'green';
    if (mult <= 2.5) return 'blue';
    if (mult <= 4) return 'purple';
    return 'gold';
}

/* ─── Load history ─── */
async function loadHistory() {
    try {
        const r = await fetch('/api/crash/history');
        const d = await r.json();
        if (!d.success) return;
        const bar = document.getElementById('crashHistory');
        bar.innerHTML = (d.history || []).map(h => {
            const m = h.multiplier;
            const cls = getHistColor(m);
            const hashShort = h.hash ? h.hash.substring(0, 6) : '';
            return `<div class="crash-hist-pill ${cls}" title="${h.hash || ''}">
                <span class="hist-mult">${m.toFixed(2)}x</span>
                ${hashShort ? `<span class="hist-hash">#${hashShort}</span>` : ''}
            </div>`;
        }).join('');
    } catch (e) {}
}

/* ─── Load bets / players ─── */
async function loadBets() {
    try {
        const r = await fetch('/api/crash/bets');
        const d = await r.json();
        if (!d.success) return;
        const list = document.getElementById('playersList');
        const bets = d.bets || [];
        document.getElementById('playersCount').textContent = bets.length;

        // Check if server auto-cashed out our bet
        if (myBet && currentUser) {
            const mine = bets.find(b => String(b.user_id) === String(currentUser.telegram_id));
            if (mine && mine.status === 'won' && myBet.game_id === gameState.game_id) {
                // Server auto-cashed out — show win popup
                currentUser.balance = (currentUser.balance || 0) + mine.win_amount;
                updateCrashTopBar();
                if (typeof updateUI === 'function') updateUI();
                showWinPopup(myBet, mine.win_amount, mine.cashout_mult, mine.won_gift_image ? { image: mine.won_gift_image, name: 'Gift', price: 0 } : null);
                try { tg.HapticFeedback.impactOccurred('light'); } catch (e) {}
                try { LunaSound.win(); } catch (e) {}
                loadUserInventory();
                refreshBalance();
                lastBetAmount = myBet.amount;
                myBet = null;
                const btn = document.getElementById('crashActionBtn');
                btn.disabled = false;
                btn.className = 'crash-action-btn';
                document.getElementById('crashActionText').textContent = t('bet');
            }
        }

        list.innerHTML = bets.map(b => {
            const avatar = b.photo_url
                ? `<img src="${b.photo_url}" alt="">`
                : `<div style="width:100%;height:100%;background:linear-gradient(135deg,#6366f1,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;border-radius:10px;color:#fff;">${(b.first_name || '?')[0]}</div>`;

            // Auto-cashout badge
            let autoBadge = '';
            if (b.auto_cashout_at && b.auto_cashout_at > 0) {
                if (b.status === 'won') {
                    autoBadge = `<span class="crash-auto-badge cashed">${(b.cashout_mult || b.auto_cashout_at).toFixed(2)}x</span>`;
                } else {
                    autoBadge = `<span class="crash-auto-badge">${b.auto_cashout_at.toFixed(2)}x</span>`;
                }
            } else if (b.status === 'won') {
                autoBadge = `<span class="crash-auto-badge cashed">${(b.cashout_mult || 0).toFixed(2)}x</span>`;
            }

            let resultHtml = '';
            if (b.status === 'won') {
                const wonIcon = b.won_gift_image
                    ? `<img src="${b.won_gift_image}" alt="" style="width:16px;height:16px;border-radius:4px;">`
                    : `<img src="/static/img/star.svg" alt="">`;
                resultHtml = `<div class="crash-player-win">${wonIcon}+${Math.floor(b.win_amount)}</div>`;
            } else if (b.status === 'lost') {
                resultHtml = `<div class="crash-player-win lost">${t('crash_text')}</div>`;
            } else {
                resultHtml = `<div class="crash-player-win playing">${t('playing')}</div>`;
            }
            const betIcon = b.bet_type === 'gift' && b.gift_image
                ? `<img src="${b.gift_image}" alt="" style="width:14px;height:14px;border-radius:3px;">`
                : `<img src="/static/img/star.svg" alt="">`;
            return `
                <div class="crash-player-row ${b.status === 'won' ? 'won' : ''}">
                    <div class="crash-player-avatar">${avatar}</div>
                    <div class="crash-player-info">
                        <div class="crash-player-name">${b.first_name || t('player')}${autoBadge}</div>
                        <div class="crash-player-bet">${betIcon}${Math.floor(b.bet_amount)}</div>
                    </div>
                    <div class="crash-player-result">${resultHtml}</div>
                </div>`;
        }).join('');
    } catch (e) {}
}

/* ─── Poll status ─── */
async function pollStatus() {
    const t0 = performance.now();
    try {
        const r = await fetch('/api/crash/status');
        const d = await r.json();
        pingMs = Math.round(performance.now() - t0);
        if (!d.success) return;

        const prevStatus = gameState.status;
        const prevId = gameState.game_id;
        gameState = d;
        serverMult = d.multiplier || 1.00;

        // Sync time offset
        if (d.server_time) {
            timeOffset = d.server_time - (Date.now() / 1000);
        }



        // New round detection
        if (prevId !== 0 && d.game_id !== prevId) {
            crashDone = false;
            displayMult = 1.00;
            serverMult = 1.00;
            flyStartLocal = 0;
            flyStartServer = 0;
            lastCountdownSec = -1;
            resetConveyor();
            if (myBet && myBet.game_id !== d.game_id) myBet = null;
            loadHistory();
            loadBets();
        }

        // Countdown sync
        if (d.status === 'counting' && d.countdown > 0) {
            countdownTarget = Date.now() + d.countdown * 1000;
        }

        // Phase transition: counting → flying — record start time
        if (prevStatus !== 'flying' && d.status === 'flying') {
            // Start with server's current multiplier to avoid lag gap
            displayMult = d.multiplier || 1.00;
            flyStartServer = d.start_time || 0;
            // Calculate how far server already progressed and offset flyStartLocal
            if (d.server_time && d.start_time) {
                const serverElapsed = d.server_time - d.start_time;
                flyStartLocal = (Date.now() / 1000) - serverElapsed;
            } else {
                flyStartLocal = Date.now() / 1000;
            }
            // Speed up bets polling during flying (500ms for instant cashout visibility)
            clearInterval(betsPollTimer);
            betsPollTimer = setInterval(loadBets, 500);
        }

        // Phase transition: flying → crashed/waiting — slow bets polling back down
        if (prevStatus === 'flying' && d.status !== 'flying') {
            clearInterval(betsPollTimer);
            betsPollTimer = setInterval(loadBets, 3000);
        }

        updateGameUI();
    } catch (e) {}
}

/* ─── Update game UI ─── */
function updateGameUI() {
    const st = gameState.status;
    const multEl = document.getElementById('crashMult');
    const statusEl = document.getElementById('crashStatusText');
    const field = document.getElementById('crashField');
    const btn = document.getElementById('crashActionBtn');
    const btnText = document.getElementById('crashActionText');

    field.classList.remove('flying', 'crashed', 'counting');

    if (st === 'waiting' || st === 'counting') {
        if (st === 'counting') {
            field.classList.add('counting');
            const remaining = Math.max(0, (countdownTarget - Date.now()) / 1000);
            const sec = Math.ceil(remaining);
            multEl.textContent = '00 : ' + String(Math.min(sec, 10)).padStart(2, '0');
            multEl.classList.remove('flying', 'crashed');
            statusEl.textContent = t('next_game_in');
            statusEl.classList.remove('flying', 'crashed');
        } else {
            multEl.textContent = '—';
            multEl.classList.remove('flying', 'crashed');
            statusEl.textContent = t('waiting');
            statusEl.classList.remove('flying', 'crashed');
        }
        clearMultColor();
        resetConveyor();
        if (!myBet) {
            btn.className = 'crash-action-btn';
            btn.disabled = false;
            btnText.textContent = t('bet');
        } else {
            btn.className = 'crash-action-btn waiting';
            btn.disabled = true;
            btnText.textContent = t('waiting_dots');
        }

    } else if (st === 'flying') {
        field.classList.add('flying');
        multEl.classList.remove('crashed');
        multEl.classList.add('flying');
        statusEl.textContent = t('game_in_progress');
        statusEl.classList.remove('crashed');
        statusEl.classList.add('flying');
        crashDone = false;
        if (myBet && myBet.game_id === gameState.game_id) {
            btn.className = 'crash-action-btn cashout';
            btn.disabled = false;
            btnText.textContent = t('cash_out');
        } else {
            btn.className = 'crash-action-btn waiting';
            btn.disabled = true;
            btnText.textContent = t('waiting_dots');
        }

    } else if (st === 'crashed') {
        field.classList.add('crashed');
        clearMultColor();
        displayMult = gameState.multiplier || 1;
        multEl.textContent = 'x' + displayMult.toFixed(2);
        multEl.classList.remove('flying');
        multEl.classList.add('crashed');
        statusEl.textContent = 'CRASH!';
        statusEl.classList.remove('flying');
        statusEl.classList.add('crashed');
        if (!crashDone) {
            crashDone = true;
            try { tg.HapticFeedback.impactOccurred('heavy'); } catch (e) {}
            try { LunaSound.lose(); } catch (e) {}
        }
        if (myBet && myBet.game_id === gameState.game_id) myBet = null;
        btn.className = 'crash-action-btn';
        btn.disabled = false;
        btnText.textContent = t('bet');
    }
}

/* ─── Elapsed time → predicted multiplier (O(1), matches server tick model) ─── */
// Server: +0.01 per tick. Tick intervals: 60ms (<2x), 40ms (2-5x), 25ms (5-10x), 8ms (>10x)
// Phase durations: 1→2: 6.0s | 2→5: 12.0s | 5→10: 12.5s | 10+: 0.8s per 1.0x
function elapsedToMult(t) {
    if (t <= 0) return 1.00;
    if (t <= 6.0)  return 1.00 + (t / 6.0);              // 1.00 → 2.00
    if (t <= 18.0) return 2.00 + ((t - 6.0) / 4.0);      // 2.00 → 5.00
    if (t <= 30.5) return 5.00 + ((t - 18.0) / 2.5);      // 5.00 → 10.00
    return 10.00 + ((t - 30.5) / 0.8);                     // 10.00+ (fast)
}

/* ─── Render loop ─── */
function renderLoop() {
    if (gameState.status === 'flying') {
        if (flyStartServer > 0) {
            const now = Date.now() / 1000;
            const elapsed = now - flyStartLocal;
            const predicted = elapsedToMult(elapsed);
            // Use server value when ahead, predict when server lags
            const target = Math.max(predicted, serverMult);
            // Snap faster to avoid display lag: 30% blend
            displayMult = displayMult + (target - displayMult) * 0.3;
            if (displayMult < 1) displayMult = 1;
        } else {
            const diff = serverMult - displayMult;
            displayMult += diff * 0.3;
            if (displayMult < 1) displayMult = 1;
        }
        const multEl = document.getElementById('crashMult');
        multEl.textContent = 'x' + displayMult.toFixed(2);

        // Auto cashout now handled server-side; client only as fallback
        const autoVal = parseFloat(document.getElementById('autoCashoutInput').value);
        if (autoVal && autoVal > 1 && displayMult >= autoVal && myBet && myBet.game_id === gameState.game_id) {
            // Server should have auto-cashed, but call just in case
            doCashout();
        }
        updateConveyor(displayMult);
    } else if (gameState.status === 'counting') {
        // Smooth countdown interpolation
        const remaining = Math.max(0, (countdownTarget - Date.now()) / 1000);
        const sec = Math.ceil(remaining);
        const multEl = document.getElementById('crashMult');
        multEl.textContent = '00 : ' + String(Math.min(sec, 10)).padStart(2, '0');
        // Haptic vibration each second of countdown
        if (sec !== lastCountdownSec && sec > 0 && sec <= 10) {
            lastCountdownSec = sec;
            try {
                if (sec <= 3) tg.HapticFeedback.impactOccurred('heavy');
                else if (sec <= 6) tg.HapticFeedback.impactOccurred('medium');
                else tg.HapticFeedback.impactOccurred('light');
            } catch(e){}
        }
    }
    rafId = requestAnimationFrame(renderLoop);
}

/* ─── Place bet ─── */
async function crashAction() {
    if (gameState.status === 'flying' && myBet && myBet.game_id === gameState.game_id) {
        doCashout();
        return;
    }
    if (myBet) return;
    if (!currentUser) { showNotification(t('authorize'), 'error'); return; }

    let starsAmount = 0;
    if (betTab === 'stars') {
        const amount = parseFloat(document.getElementById('starsBetInput').value);
        if (!amount || amount <= 0) { showNotification(t('enter_bet'), 'error'); return; }
        starsAmount = Math.floor(amount);
        if (starsAmount < 1) { showNotification(t('min_1_star'), 'error'); return; }
        if (currentUser.balance < starsAmount) { showNotification(t('insufficient_funds'), 'error'); return; }
    } else {
        if (!selectedGift) { showNotification(t('select_gift'), 'error'); return; }
        starsAmount = selectedGift.value;
    }

    const btn = document.getElementById('crashActionBtn');
    btn.disabled = true;
    try {
        const body = { telegram_id: currentUser.telegram_id, bet: starsAmount, bet_type: betTab };
        if (betTab === 'gift' && selectedGift) body.gift_inventory_id = selectedGift.id;
        const autoVal = parseFloat(document.getElementById('autoCashoutInput').value);
        if (autoVal && autoVal > 1) body.auto_cashout_at = autoVal;

        const r = await fetch('/api/crash/bet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const d = await r.json();
        if (!d.success) {
            showNotification(d.error || 'Ошибка', 'error');
            btn.disabled = false;
            return;
        }
        currentUser.balance = d.new_balance;
        updateCrashTopBar();
        if (typeof updateUI === 'function') updateUI();
        myBet = { game_id: d.game_id, amount: starsAmount, type: betTab, gift: betTab === 'gift' ? selectedGift : null, auto_cashout_at: autoVal || 0 };
        lastBetAmount = starsAmount;
        initCarouselForBet(starsAmount);
        if (betTab === 'gift') { removeSelectedGift(); loadUserInventory(); }
        btn.className = 'crash-action-btn waiting';
        btn.disabled = true;
        document.getElementById('crashActionText').textContent = t('waiting_dots');
        try { tg.HapticFeedback.impactOccurred('medium'); } catch (e) {}
        try { LunaSound.bet(); } catch (e) {}
    } catch (e) {
        showNotification(t('connection_error'), 'error');
        btn.disabled = false;
    }
}

/* ─── Cashout ─── */
async function doCashout() {
    if (!myBet) return;
    const btn = document.getElementById('crashActionBtn');
    btn.disabled = true;
    try {
        const r = await fetch('/api/crash/cashout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telegram_id: currentUser.telegram_id, game_id: myBet.game_id })
        });
        const d = await r.json();
        if (d.success) {
            currentUser.balance = d.new_balance;
            updateCrashTopBar();
            if (typeof updateUI === 'function') updateUI();
            showWinPopup(myBet, d.winnings, d.multiplier, d.gift);
            try { tg.HapticFeedback.impactOccurred('light'); } catch (e) {}
            try { LunaSound.win(); } catch (e) {}
            // Instantly refresh bets list so all players see the cashout
            loadBets();
            // Refresh inventory (cashout may award gifts)
            loadUserInventory();
        } else {
            showNotification(d.error || t('cashout_error'), 'error');
        }
    } catch (e) {
        showNotification(t('connection_error'), 'error');
    }
    lastBetAmount = myBet ? myBet.amount : lastBetAmount;
    myBet = null;
    btn.disabled = false;
    btn.className = 'crash-action-btn';
    document.getElementById('crashActionText').textContent = t('bet');
}

/* ─── Win popup ─── */
function showWinPopup(bet, winnings, multiplier, serverGift) {
    const overlay = document.getElementById('winOverlay');
    const giftImg = document.getElementById('winGiftImg');
    const multEl = document.getElementById('winMult');
    const details = document.getElementById('winDetails');
    const breakdown = document.getElementById('winBreakdown');

    // Always show multiplier
    multEl.textContent = multiplier.toFixed(2) + 'x';
    multEl.style.display = 'inline-block';

    // Reset image
    giftImg.onerror = null;
    giftImg.style.display = 'none';

    if (serverGift && serverGift.image) {
        // Server awarded a gift — show it big
        giftImg.src = serverGift.image;
        giftImg.onerror = function() {
            // Try NFT jpg fallback via slug extraction from image path
            const slug = serverGift.image.replace(/.*\//, '').replace(/\.\w+$/, '');
            this.onerror = function() { this.style.display = 'none'; };
            this.src = '/static/img/nft/' + slug + '.jpg';
        };
        giftImg.style.display = 'block';
        details.innerHTML = `${t('you_got_gift')} <b>${serverGift.name}</b>`;
        const remaining = winnings - (serverGift.price || 0);
        if (remaining > 0) {
            breakdown.innerHTML = `+ <img src="/static/img/star.svg" alt=""> ${remaining} ${t('stars_to_balance')}`;
            breakdown.style.display = 'flex';
        } else {
            breakdown.style.display = 'none';
        }
    } else if (bet.type === 'gift' && bet.gift && bet.gift.image) {
        giftImg.src = bet.gift.image;
        giftImg.style.display = 'block';
        details.innerHTML = `${t('bet_label')} <img src="/static/img/star.svg" alt=""> <b>${bet.amount}</b> → ${t('win_label')} <img src="/static/img/star.svg" alt=""> <b>${Math.floor(winnings)}</b>`;
        breakdown.innerHTML = `<img src="/static/img/star.svg" alt=""> ${Math.floor(winnings)} ${t('stars_to_balance')}`;
        breakdown.style.display = 'flex';
    } else {
        // Stars-only win — show star icon
        giftImg.src = '/static/img/star.svg';
        giftImg.style.display = 'block';
        details.innerHTML = `${t('win_label')} <img src="/static/img/star.svg" alt=""> <b>${Math.floor(winnings)}</b>`;
        breakdown.innerHTML = `${t('bet_label')} <img src="/static/img/star.svg" alt=""> ${bet.amount} × ${multiplier.toFixed(2)}`;
        breakdown.style.display = 'flex';
    }
    overlay.classList.add('show');
}

function closeWinPopup() {
    document.getElementById('winOverlay').classList.remove('show');
}

/* ─── Restore bet after page refresh ─── */
async function restoreMyBet() {
    if (!currentUser || myBet) return;
    try {
        const r = await fetch('/api/crash/bets');
        const d = await r.json();
        if (!d.success) return;
        const mine = (d.bets || []).find(b =>
            String(b.user_id) === String(currentUser.telegram_id) && b.status === 'playing'
        );
        if (mine) {
            myBet = {
                game_id: gameState.game_id,
                amount: mine.bet_amount,
                type: mine.bet_type || 'stars',
                gift: mine.gift_image ? { image: mine.gift_image } : null,
                auto_cashout_at: mine.auto_cashout_at || 0
            };
            lastBetAmount = mine.bet_amount;
            initCarouselForBet(mine.bet_amount);
            updateGameUI();
        }
    } catch (e) {}
}



/* ─── Init ─── */
document.addEventListener('DOMContentLoaded', async function () {
    setLoadProgress(5, 'Инициализация...');
    await initApp();
    setLoadProgress(40, 'Загрузка подарков...');
    await loadCrashGifts();
    buildConveyor();
    setLoadProgress(60, 'Loading inventory...');
    await loadUserInventory();
    updateCrashTopBar();
    loadHistory();
    loadBets();

    setLoadProgress(80, 'Подключение...');

    // Poll status (1s interval — client predicts between polls)
    await pollStatus();
    // Try to restore bet if page was refreshed mid-game
    await restoreMyBet();
    statusPollTimer = setInterval(pollStatus, 1000);
    betsPollTimer = setInterval(loadBets, 3000);
    historyTimer = setInterval(loadHistory, 10000);


    rafId = requestAnimationFrame(renderLoop);

    setLoadProgress(100, 'Готово!');
    dismissLoading();

    // Apply language
    if (typeof applyLang === 'function') applyLang();

    // First-visit tutorial
    setTimeout(()=>{ showTutorial('crash', buildCrashTutorialSteps()); }, 600);
});
