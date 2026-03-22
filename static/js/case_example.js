// Пример оформления кейсов — подключённый вспомогательный скрипт.
// Оригинал примера находится в `exemple/Новый текстовый документ.txt` в репозитории.
// Замените содержимое этого файла на полный пример при необходимости.
(function(){
    console.log('case_example.js loaded — пример оформления кейсов подключён');
    // Пример: добавить вспомогательные классы/инициализацию для страницы кейсов
    window.caseExampleInit = function(){
        const style = document.createElement('style');
        style.textContent = `
        /* Быстрые визуальные правки примера */
        .case-card-v2 { border: 1px solid rgba(255,255,255,0.05); transition:transform .16s ease, box-shadow .16s ease; }
        .case-card-v2:hover { transform:translateY(-6px); box-shadow:0 12px 30px rgba(0,0,0,.35); }
        .popular-case-card { border-left:4px solid var(--gold); }
        .roulette-card.winner { outline: 3px solid rgba(255,230,150,0.22); transform:scale(1.04); }
        `;
        document.head.appendChild(style);
    };
    if(document.readyState==='complete' || document.readyState==='interactive'){
        window.caseExampleInit();
    } else document.addEventListener('DOMContentLoaded', window.caseExampleInit);
})();
