
// Topology Tooltips
const tooltip = document.getElementById('topo-tooltip');
const nodes = document.querySelectorAll('.topo-node, .topo-node-primary, .topo-node-alt, .topo-app, .topo-service, .topo-service-ai');

nodes.forEach(node => {
    node.addEventListener('mouseenter', (e) => {
        const title = node.getAttribute('data-title');
        const desc = node.getAttribute('data-desc');
        if (tooltip) {
            document.getElementById('topo-tool-title').innerText = title;
            document.getElementById('topo-tool-desc').innerText = desc;
            tooltip.style.display = 'block';
            updateTooltipPos(e);
        }
    });

    node.addEventListener('mousemove', updateTooltipPos);

    node.addEventListener('mouseleave', () => {
        if (tooltip) tooltip.style.display = 'none';
    });
});

function updateTooltipPos(e) {
    if (!tooltip) return;
    const container = document.querySelector('.svg-container');
    if (!container) return;
    const rect = container.getBoundingClientRect();
    tooltip.style.left = (e.clientX - rect.left + 20) + 'px';
    tooltip.style.top = (e.clientY - rect.top + 20) + 'px';
}

// Chaos Engineer Game v2
let chaosGameActive = false;
let chaosUptime = 0;
let chaosPods = 8;
let chaosFailed = 0;
let chaosInterval, chaosTimer;
const chaosGrid = document.getElementById('chaos-grid');
const chaosStartScreen = document.getElementById('chaos-start-screen');

const startChaosBtn = document.getElementById('start-chaos-btn');
if (startChaosBtn) startChaosBtn.addEventListener('click', startChaosGame);

function startChaosGame() {
    chaosGameActive = true;
    chaosUptime = 0;
    chaosFailed = 0;
    if (chaosStartScreen) chaosStartScreen.classList.add('d-none');
    if (chaosGrid) chaosGrid.classList.remove('d-none');

    renderPods();

    chaosTimer = setInterval(() => {
        chaosUptime++;
        const timeEl = document.getElementById('game-v2-time');
        if (timeEl) timeEl.innerText = chaosUptime + 's';

        // Randomly fail pods
        if (Math.random() < 0.2 + (chaosUptime / 100)) {
            triggerPodFailure();
        }

        updateLoad();
    }, 1000);
}

function renderPods() {
    if (!chaosGrid) return;
    chaosGrid.innerHTML = '';
    for (let i = 0; i < 8; i++) {
        const pod = document.createElement('div');
        pod.className = 'col';
        pod.innerHTML = `
            <div class="chaos-pod" id="pod-${i}" onclick="restartPod(${i})">
                <i class="opacity-50">📦</i>
                <span class="smallest opacity-80">pod-v${i}</span>
            </div>
        `;
        chaosGrid.appendChild(pod);
    }
    const podsCountEl = document.getElementById('game-v2-pods');
    if (podsCountEl) podsCountEl.innerText = 8;
}

function triggerPodFailure() {
    const livePods = [];
    for (let i = 0; i < 8; i++) {
        const p = document.getElementById(`pod-${i}`);
        if (p && !p.classList.contains('failed')) livePods.push(p);
    }

    if (livePods.length > 0) {
        const target = livePods[Math.floor(Math.random() * livePods.length)];
        target.classList.add('failed');
        target.querySelector('i').innerText = '⚠️';
        chaosFailed++;
    }
}

window.restartPod = function(id) {
    const pod = document.getElementById(`pod-${id}`);
    if (pod && pod.classList.contains('failed')) {
        pod.classList.remove('failed');
        pod.querySelector('i').innerText = '📦';
        chaosFailed--;
        updateLoad();
    }
};

function updateLoad() {
    const load = Math.round((chaosFailed / 8) * 100);
    const loadEl = document.getElementById('game-v2-load');
    if (loadEl) {
        loadEl.innerText = load + '%';
        if (load < 40) loadEl.className = 'h4 mb-0 fw-bold text-success';
        else if (load < 80) loadEl.className = 'h4 mb-0 fw-bold text-warning';
        else loadEl.className = 'h4 mb-0 fw-bold text-danger';
    }

    if (load >= 100) {
        endChaosGame();
    }
}

function endChaosGame() {
    chaosGameActive = false;
    clearInterval(chaosTimer);
    if (chaosGrid) chaosGrid.classList.add('d-none');
    if (chaosStartScreen) {
        chaosStartScreen.classList.remove('d-none');
        chaosStartScreen.innerHTML = `
            <h2 class="text-danger fw-bold mb-3">CLUSTER OVERFLOW</h2>
            <p class="mb-4 lead text-white">Uptime: ${chaosUptime} seconds. Infrastructure collapsed under load.</p>
            <button id="retry-chaos-btn" onclick="startChaosGame()" class="btn btn-outline-light px-5 py-3 rounded-pill fw-bold">RETRY ARCHITECTURE</button>
        `;
    }
}

const K8S_GAME = {
    active: false,
    wave: 0,
    health: 100,
    credits: 100,
    selectedPod: null,
    towers: [],
    enemies: [],
    projectiles: [],
    grid: { rows: 9, cols: 15, cellSize: 60 },
    path: [],
    waveInProgress: false,
    enemiesSpawned: 0,
    enemiesKilled: 0,

    podTypes: {
        nginx: { cost: 20, damage: 10, range: 120, fireRate: 500, icon: '🔵' },
        redis: { cost: 35, damage: 8, range: 100, fireRate: 400, icon: '🔴', aoe: 50 },
        database: { cost: 50, damage: 30, range: 140, fireRate: 1200, icon: '🟣' },
        loadbalancer: { cost: 80, damage: 15, range: 180, fireRate: 300, icon: '🟢', multiTarget: 2 }
    },

    enemyTypes: {
        traffic: { health: 50, speed: 1.5, reward: 10, icon: '🟠' },
        ddos: { health: 100, speed: 2, reward: 15, icon: '🔴' },
        leak: { health: 80, speed: 1, reward: 12, icon: '🟣' },
        boss: { health: 300, speed: 0.8, reward: 50, icon: '💀' }
    }
};

const startK8sBtn = document.getElementById('start-k8s-game');
if (startK8sBtn) {
    startK8sBtn.addEventListener('click', () => {
        const startScreen = document.getElementById('game-start-screen');
        const grid = document.getElementById('k8s-game-grid');
        const shop = document.getElementById('pod-shop');
        if (startScreen) startScreen.classList.add('d-none');
        if (grid) grid.classList.remove('d-none');
        if (shop) shop.classList.remove('d-none');
        K8S_GAME.active = true;
        initGame();
    });
}

function initGame() {
    createGrid();
    createPath();
    setupPodSelection();
    startWave();
    gameLoop();
}

function createGrid() {
    const grid = document.getElementById('tower-grid');
    if (!grid) return;
    grid.innerHTML = '';

    for (let row = 0; row < K8S_GAME.grid.rows; row++) {
        for (let col = 0; col < K8S_GAME.grid.cols; col++) {
            const cell = document.createElement('div');
            cell.className = 'grid-cell';
            cell.style.left = (col * K8S_GAME.grid.cellSize) + 'px';
            cell.style.top = (row * K8S_GAME.grid.cellSize) + 'px';
            cell.dataset.row = row;
            cell.dataset.col = col;

            cell.addEventListener('click', () => placeTower(row, col, cell));
            grid.appendChild(cell);
        }
    }
}

function createPath() {
    K8S_GAME.path = [
        { x: -30, y: 270 },
        { x: 120, y: 270 },
        { x: 120, y: 150 },
        { x: 360, y: 150 },
        { x: 360, y: 390 },
        { x: 600, y: 390 },
        { x: 600, y: 210 },
        { x: 780, y: 210 },
        { x: 780, y: 330 },
        { x: 950, y: 330 }
    ];

    const pathEl = document.getElementById('attack-path');
    if (pathEl) {
        const pathStr = K8S_GAME.path.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
        pathEl.setAttribute('d', pathStr);
    }

    K8S_GAME.path.forEach(point => {
        const col = Math.floor(point.x / K8S_GAME.grid.cellSize);
        const row = Math.floor(point.y / K8S_GAME.grid.cellSize);
        const cell = document.querySelector(`[data-row="${row}"][data-col="${col}"]`);
        if (cell) cell.classList.add('path');
    });
}

function setupPodSelection() {
    document.querySelectorAll('.pod-card').forEach(card => {
        card.addEventListener('click', function () {
            document.querySelectorAll('.pod-card').forEach(c => c.classList.remove('selected'));
            this.classList.add('selected');
            K8S_GAME.selectedPod = this.dataset.pod;
        });
    });
}

function placeTower(row, col, cell) {
    if (!K8S_GAME.selectedPod || cell.classList.contains('path') || cell.classList.contains('has-tower')) {
        return;
    }

    const podType = K8S_GAME.podTypes[K8S_GAME.selectedPod];

    if (K8S_GAME.credits < podType.cost) {
        showMessage('Not enough CPU credits!', 'danger');
        return;
    }

    K8S_GAME.credits -= podType.cost;
    updateStats();

    const tower = {
        type: K8S_GAME.selectedPod,
        row, col,
        x: col * K8S_GAME.grid.cellSize + 30,
        y: row * K8S_GAME.grid.cellSize + 30,
        lastFire: Date.now(),
        ...podType
    };

    K8S_GAME.towers.push(tower);

    cell.classList.add('has-tower');
    cell.innerHTML = `
        <div class="tower ${K8S_GAME.selectedPod}">
            <span>${podType.icon}</span>
            <div class="tower-range" style="width: ${tower.range * 2}px; height: ${tower.range * 2}px; left: 50%; top: 50%; transform: translate(-50%, -50%);"></div>
        </div>
    `;

    K8S_GAME.selectedPod = null;
    document.querySelectorAll('.pod-card').forEach(c => c.classList.remove('selected'));
}

function startWave() {
    if (K8S_GAME.wave >= 15) {
        victory();
        return;
    }

    K8S_GAME.wave++;
    K8S_GAME.waveInProgress = true;
    K8S_GAME.enemiesSpawned = 0;
    K8S_GAME.enemiesKilled = 0;

    updateStats();
    const waveStatusEl = document.getElementById('wave-status');
    if (waveStatusEl) waveStatusEl.textContent = `Wave ${K8S_GAME.wave} - Incoming!`;

    const waveConfig = getWaveConfig(K8S_GAME.wave);
    spawnWave(waveConfig);
}

function getWaveConfig(wave) {
    const configs = {
        easy: { count: 5 + wave, types: ['traffic'], interval: 1500 },
        medium: { count: 8 + wave, types: ['traffic', 'ddos'], interval: 1200 },
        hard: { count: 10 + wave, types: ['traffic', 'ddos', 'leak'], interval: 1000 },
        boss: { count: 3, types: ['boss'], interval: 3000 }
    };

    if (wave % 5 === 0) return configs.boss;
    if (wave > 10) return configs.hard;
    if (wave > 5) return configs.medium;
    return configs.easy;
}

function spawnWave(config) {
    const spawnInterval = setInterval(() => {
        if (K8S_GAME.enemiesSpawned >= config.count) {
            clearInterval(spawnInterval);
            return;
        }

        const type = config.types[Math.floor(Math.random() * config.types.length)];
        spawnEnemy(type);
        K8S_GAME.enemiesSpawned++;
    }, config.interval);
}

function spawnEnemy(type) {
    const enemyData = K8S_GAME.enemyTypes[type];
    const enemy = {
        type,
        health: enemyData.health,
        maxHealth: enemyData.health,
        speed: enemyData.speed,
        reward: enemyData.reward,
        icon: enemyData.icon,
        pathIndex: 0,
        x: K8S_GAME.path[0].x,
        y: K8S_GAME.path[0].y,
        slow: 1
    };

    K8S_GAME.enemies.push(enemy);

    const layer = document.getElementById('enemy-layer');
    if (!layer) return;

    const enemyEl = document.createElement('div');
    enemyEl.className = `enemy ${type}`;
    enemyEl.innerHTML = `
        ${enemy.icon}
        <div class="health-bar">
            <div class="health-bar-fill" style="width: 100%"></div>
        </div>
    `;
    enemy.element = enemyEl;
    layer.appendChild(enemyEl);
}

function gameLoop() {
    if (!K8S_GAME.active) return;

    updateEnemies();
    updateTowers();
    updateProjectiles();
    checkWaveComplete();

    requestAnimationFrame(gameLoop);
}

function updateEnemies() {
    K8S_GAME.enemies.forEach((enemy, index) => {
        if (enemy.health <= 0) {
            killEnemy(enemy, index);
            return;
        }

        const target = K8S_GAME.path[enemy.pathIndex + 1];
        if (!target) {
            K8S_GAME.health -= 10;
            updateStats();
            if (enemy.element) enemy.element.remove();
            K8S_GAME.enemies.splice(index, 1);
            K8S_GAME.enemiesKilled++;

            if (K8S_GAME.health <= 0) {
                gameOver();
            }
            return;
        }

        const dx = target.x - enemy.x;
        const dy = target.y - enemy.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 5) {
            enemy.pathIndex++;
        } else {
            const moveSpeed = enemy.speed * enemy.slow;
            enemy.x += (dx / dist) * moveSpeed;
            enemy.y += (dy / dist) * moveSpeed;
        }

        if (enemy.element) {
            enemy.element.style.left = enemy.x + 'px';
            enemy.element.style.top = enemy.y + 'px';
            const healthPercent = (enemy.health / enemy.maxHealth) * 100;
            const fill = enemy.element.querySelector('.health-bar-fill');
            if (fill) fill.style.width = healthPercent + '%';
        }

        enemy.slow = Math.min(enemy.slow + 0.05, 1);
    });
}

function updateTowers() {
    const now = Date.now();
    K8S_GAME.towers.forEach(tower => {
        if (now - tower.lastFire < tower.fireRate) return;
        const targets = K8S_GAME.enemies.filter(enemy => {
            const dx = enemy.x - tower.x;
            const dy = enemy.y - tower.y;
            return Math.sqrt(dx * dx + dy * dy) <= tower.range;
        });
        if (targets.length === 0) return;
        const targetsToHit = tower.multiTarget ? targets.slice(0, tower.multiTarget) : [targets[0]];
        targetsToHit.forEach(target => createProjectile(tower, target));
        tower.lastFire = now;
    });
}

function createProjectile(tower, target) {
    const projectile = {
        x: tower.x,
        y: tower.y,
        target,
        damage: tower.damage,
        speed: 5,
        aoe: tower.aoe || 0
    };
    K8S_GAME.projectiles.push(projectile);
    const layer = document.getElementById('enemy-layer');
    if (layer) {
        const projEl = document.createElement('div');
        projEl.className = 'projectile';
        projectile.element = projEl;
        layer.appendChild(projEl);
    }
}

function updateProjectiles() {
    K8S_GAME.projectiles.forEach((proj, index) => {
        if (!proj.target || proj.target.health <= 0) {
            if (proj.element) proj.element.remove();
            K8S_GAME.projectiles.splice(index, 1);
            return;
        }
        const dx = proj.target.x - proj.x;
        const dy = proj.target.y - proj.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 10) {
            damageEnemy(proj.target, proj.damage);
            if (proj.aoe > 0) {
                K8S_GAME.enemies.forEach(enemy => {
                    if (enemy === proj.target) return;
                    const edx = enemy.x - proj.target.x;
                    const edy = enemy.y - proj.target.y;
                    const edist = Math.sqrt(edx * edx + edy * edy);
                    if (edist <= proj.aoe) {
                        damageEnemy(enemy, proj.damage * 0.5);
                        enemy.slow = 0.5;
                    }
                });
            }
            if (proj.element) proj.element.remove();
            K8S_GAME.projectiles.splice(index, 1);
        } else {
            proj.x += (dx / dist) * proj.speed;
            proj.y += (dy / dist) * proj.speed;
            if (proj.element) {
                proj.element.style.left = proj.x + 'px';
                proj.element.style.top = proj.y + 'px';
            }
        }
    });
}

function damageEnemy(enemy, damage) {
    enemy.health -= damage;
    const layer = document.getElementById('enemy-layer');
    if (layer) {
        const popup = document.createElement('div');
        popup.className = 'damage-popup';
        popup.textContent = `-${Math.round(damage)}`;
        popup.style.left = enemy.x + 'px';
        popup.style.top = enemy.y + 'px';
        layer.appendChild(popup);
        setTimeout(() => popup.remove(), 800);
    }
}

function killEnemy(enemy, index) {
    K8S_GAME.credits += enemy.reward;
    K8S_GAME.enemiesKilled++;
    updateStats();
    if (enemy.element) enemy.element.remove();
    K8S_GAME.enemies.splice(index, 1);
}

function checkWaveComplete() {
    if (K8S_GAME.waveInProgress && K8S_GAME.enemiesSpawned > 0 && K8S_GAME.enemies.length === 0) {
        K8S_GAME.waveInProgress = false;
        const status = document.getElementById('wave-status');
        if (status) status.textContent = `Wave ${K8S_GAME.wave} Complete! Next wave in 3s...`;
        setTimeout(() => { if (K8S_GAME.active) startWave(); }, 3000);
    }
}

function updateStats() {
    const healthEl = document.getElementById('cluster-health');
    const waveEl = document.getElementById('current-wave');
    const cpuEl = document.getElementById('cpu-credits');
    if (healthEl) {
        healthEl.textContent = K8S_GAME.health;
        if (K8S_GAME.health > 60) healthEl.className = 'h4 mb-0 fw-bold text-success';
        else if (K8S_GAME.health > 30) healthEl.className = 'h4 mb-0 fw-bold text-warning';
        else healthEl.className = 'h4 mb-0 fw-bold text-danger';
    }
    if (waveEl) waveEl.textContent = K8S_GAME.wave;
    if (cpuEl) cpuEl.textContent = K8S_GAME.credits;
}

function showMessage(text, type) {
    const msg = document.createElement('div');
    msg.className = `alert alert-${type} position-fixed top-0 start-50 translate-middle-x mt-5`;
    msg.style.zIndex = '10000';
    msg.textContent = text;
    document.body.appendChild(msg);
    setTimeout(() => msg.remove(), 2000);
}

function gameOver() {
    K8S_GAME.active = false;
    const finalWaveEl = document.getElementById('final-wave');
    if (finalWaveEl) finalWaveEl.textContent = K8S_GAME.wave;
    const gameOverScreen = document.getElementById('game-over-screen');
    if (gameOverScreen) gameOverScreen.classList.remove('d-none');
}

function victory() {
    K8S_GAME.active = false;
    const victoryScreen = document.getElementById('victory-screen');
    if (victoryScreen) victoryScreen.classList.remove('d-none');
}
