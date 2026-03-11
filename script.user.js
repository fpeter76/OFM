// ==UserScript==
// @name         Online Football Manager
// @namespace    http://tampermonkey.net/
// @version      1.0.1
// @description  try to take over the world!
// @author       pfazekas
// @match        https://en.onlinefootballmanager.com/*
// @icon         data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==
// @run-at       document-end
// ==/UserScript==

const DEBUG_LOG = false;
const ACADEMY = '/stadium/stadium-spielerakademie.php';
const FANSHOP = '/stadium/stadium-fanshop.php';
const TRANSFER = '/transfer/transfermarkt.php';
const YOUTH_ACADEMY = [
    '/stadium/stadium-jugendakademie.php',
    '/game/stadium/youth-academy',
];
const TACTICS_SCHOOL = [
    '/stadium/stadium-taktikschule.php',
    '/game/stadium/tactics',
];

const CHECK_INTERVAL_SECONDS = 30;
const VERSION ='1.0.1';
const FANSHOP_TARGET_SLOT = 1;
const COOLDOWN_SECONDS = 20;

function getTimestampString(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');

  return `${date.getFullYear()}.` +
         `${pad(date.getMonth() + 1)}.` +
         `${pad(date.getDate())}. ` +
         `${pad(date.getHours())}:` +
         `${pad(date.getMinutes())}:` +
         `${pad(date.getSeconds())}`;
}

function logPrefix() {
    return `${getTimestampString()} v${VERSION} Tampermonkey`;
}

function log(msg) {
    console.log(`${logPrefix()} [INFO]  ${msg}`);
}

function debug(msg) {
    if (!DEBUG_LOG) {
        return;
    }
    console.log(`${logPrefix()} [DEBUG] ${msg}`);
}

function isVideoInProgress() {
    const watermark = document.querySelector('.enigma-watermark');
    if (watermark) {
        debug('Video watermark detected. Action paused.');
        return true;
    }
    return false;
}

function calculateUp(ep, tp) {
    return Math.round(2*ep*tp/(ep+tp));
}

function getLevelInfo(up) {
    // Array of thresholds: Index 0 = Level 2, Index 1 = Level 3, etc.
    const thresholds = [
        165, 371, 721, 1215, 1936, 2699, 3502, 4367, 5274, 6221, 
        7210, 8240, 9321, 10455, 11639, 12875, 14163, 15501, 16871, 
        18190, 19478, 20734, 21970, 23206, 24678, 26174, 27694, 
        29237, 30805, 32397, 34013, 35652
    ];

    let level = 1;
    let nextThreshold = thresholds[0];

    // Loop through thresholds to find current level
    for (let i = 0; i < thresholds.length; i++) {
        if (up >= thresholds[i]) {
            level = i + 2; // Level is index + 2 (e.g., index 0 is level 2)
            // Get the next threshold if it exists
            nextThreshold = thresholds[i + 1] || null;
        } else {
            // Since thresholds are sorted, we can stop early
            nextThreshold = thresholds[i];
            break;
        }
    }

    const missing = nextThreshold ? (nextThreshold - up) : 0;

    return {
        level: level,
        missing: missing,
        nextLevel: nextThreshold ? level + 1 : null
    };
}

function talentPlayer(currentLevel, calculatedLevel, calculatedMissing) {
    return (currentLevel < calculatedLevel) ||
        ((currentLevel == calculatedLevel) && (calculatedMissing < 100));
}

// ---------------------------------------------------------------------------------

function checkAcademyUnitsCreatedSlot(slotNumber) {
    debug(`Check academy ${slotNumber}. slot...`);

    const id = `unitsCreated_slot${slotNumber}`;

    const slot = document.getElementById(id);

    if (!slot) return;

    const count = parseInt(slot.innerText.trim());
    debug(`${count} piece(s) of material`);
    if (!isNaN(count) && count >= 1) {
        log('Material found! Clicking...');
        const collectButton = slot.closest('.tooltip-button');
        if (collectButton) {
            log(`Clicking ACADEMY ${slotNumber}. material button`);
            collectButton.click();
        }
    }
}

function checkAcademyPlayButton() {
    debug(`Check academy play button...`);

    if (isVideoInProgress()) return;

    const playBtn = document.querySelector('#play');

    if (!playBtn) return;

    if (playBtn.classList.contains('disabled')) return;

    if (typeof playBtn.onclick !== 'function') return;

    const timerElement = document.getElementById('generatorCountdown');
    const remainingTime = timerElement ? timerElement.innerText.trim() : "unknown time";
    log(`Clicking ACADEMY video button. Time remaining: ${remainingTime}`);
    playBtn.click();
}

function checkTacticsSchoolPlayButton() {
    debug(`Check tactics school play button...`);

    if (isVideoInProgress()) return;

    const playBtn = document.querySelector('#play');

    if (!playBtn) return;
    debug('Play button found');

    if (!playBtn.classList.contains('grau')) return;
    log('Play button is enabled');

    if (typeof playBtn.onclick !== 'function') return;
    log('Play button has onclick handler');

    const timerElement = document.getElementById('countdownTaktikschuleCardGenerator');
    const remainingTime = timerElement ? timerElement.innerText.trim() : "unknown time";
    log(`Clicking TACTICS SCHOOL video button. Time remaining: ${remainingTime}`);
    playBtn.click();
}

function checkFanshopPlayButton() {
    debug(`Check fanshop play button...`);

    if (isVideoInProgress()) return;

    const playBtn = document.getElementById(`play_slot${FANSHOP_TARGET_SLOT}`);
    const timerId = `importCountdown${FANSHOP_TARGET_SLOT}`;
    const timerElement = document.getElementById(timerId);
    
    if (playBtn && !playBtn.classList.contains('disabled')) {
        const remainingTime = timerElement ? timerElement.innerText.trim() : "time unknown";
        log(`Clicking FANSHOP slot ${FANSHOP_TARGET_SLOT}. Time remaining: ${remainingTime}`);
        playBtn.click();
    }
}

function modifyTransfer() {
    const mainTable = document.querySelector('.content_table2');
    if (!mainTable) return;
    const rows = mainTable.querySelectorAll(':scope > tbody > tr');
    rows.forEach(async (row, index) => {
        if (index === 0) return;

        if (row.dataset.upProcessed) return;
        row.dataset.upProcessed = "true";

        const strengthCell = row.childNodes[9];
        const trainingCell = row.childNodes[11];
        if (trainingCell) {
            if (trainingCell.querySelector('.tm-training-value')) return;
            const [ep, tr] = trainingCell.innerHTML.replace(/\./g, '').split('/').map(num => parseInt(num.trim()));
            const up = calculateUp(ep, tr);
            const levelInfo = getLevelInfo(up);
            trainingCell.innerHTML += ` -> ${up}`

            const trainingValue = `Current: ${levelInfo.level}<br/>need ${levelInfo.missing} UP for ${levelInfo.nextLevel}`;
            const currentLevel = strengthCell.textContent.trim();
            const trDisplay = document.createElement('div');

            // processed flag
            trDisplay.classList.add('tm-market-value');

            trDisplay.style.fontSize = '8px';
            trDisplay.style.color = talentPlayer(currentLevel, levelInfo.level, levelInfo.missing) ? '#0a0' : '#666';
            trDisplay.style.marginTop = '2px';
            trDisplay.style.fontWeight = talentPlayer(currentLevel, levelInfo.level, levelInfo.missing) ? 'bold' : 'normal';
            trDisplay.innerHTML = `${trainingValue}`;
            trainingCell.appendChild(trDisplay);
        }

        const bidCell = row.childNodes[13];
        if (bidCell) {
            if (bidCell.querySelector('.tm-market-value')) return;

            const tooltipAttr = bidCell.getAttribute('onmouseover');
            const regex = /Market value:  <\/td><td align=right>(.*?)<\/td>/i;
            const match = tooltipAttr.match(regex);

            if (match && match[1]) {
                const marketValue = match[1];
                const mvDisplay = document.createElement('div');

                // processed flag
                mvDisplay.classList.add('tm-market-value');

                mvDisplay.style.fontSize = '8px';
                mvDisplay.style.color = '#666';
                mvDisplay.style.marginTop = '2px';
                mvDisplay.style.fontWeight = 'normal';
                mvDisplay.innerHTML = `(${marketValue})`;
                bidCell.appendChild(mvDisplay);
            }
        }
    });
}

(function() {
    'use strict';

    let lastPath = location.pathname;

    debug(`lastPath: ${lastPath}`);

    if (lastPath === ACADEMY || lastPath === YOUTH_ACADEMY[0]) {
        setInterval(() => {
            debug(`Check ${lastPath}...`);

            for(var i = 1; i <= 4; i++) {
                checkAcademyUnitsCreatedSlot(i);
            }

            checkAcademyPlayButton();

        }, CHECK_INTERVAL_SECONDS * 1000);
    }

    if (lastPath === FANSHOP) {
        setInterval(() => {
            debug('Check FANSHOP...');

            checkFanshopPlayButton();

        }, CHECK_INTERVAL_SECONDS * 1000);
    }
    
    if (lastPath === TACTICS_SCHOOL[0]) {
        setInterval(() => {
            debug('Check TACTICS_SCHOOL...');
            
            checkTacticsSchoolPlayButton();
            
        }, CHECK_INTERVAL_SECONDS * 1000);
    }

    if (lastPath === TRANSFER) {
        debug('Modify TRANSFER...');
        modifyTransfer();
    }
})();
