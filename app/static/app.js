// Front-end: desenha o cruzamento e mostra o raciocínio do agente a cada tick.
// Não há lógica de decisão aqui: tudo vem pronto do Python via WebSocket.
// Os carros são animados entre um tick e outro para facilitar o acompanhamento.

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

const SIZE = 600;
const C = SIZE / 2;        // centro do cruzamento
const HALF = 60;           // metade da largura da pista
const CAR_L = 28, CAR_W = 16, GAP = 6;
const SLOT = CAR_L + GAP;  // distância entre carros na fila
const MAX_VISIBLE = 7;     // carros desenhados por via (o resto vira "+N")

const DIRS = ["N", "S", "E", "W"];
const AXIS_OF = { N: "NS", S: "NS", E: "EW", W: "EW" };
// rotação do carro: N vem do norte e anda para o sul, E vem do leste e anda para o oeste...
const HEADING = { N: Math.PI, S: 0, E: -Math.PI / 2, W: Math.PI / 2 };
const COLORS = ["#2563eb", "#7c3aed", "#0891b2", "#059669", "#ea580c", "#475569", "#db2777", "#ca8a04"];

const PERF_LABELS = {
  score: "Pontuação",
  throughput: "Carros que passaram",
  total_wait: "Espera acumulada (carro x tick)",
  avg_wait: "Espera média por carro",
  max_queue: "Maior fila vista",
  switches: "Trocas de sinal",
  emergency_passed: "Emergências atendidas",
  max_emergency_wait: "Maior espera de emergência",
};
const METRIC_LABELS = {
  green_axis: "Eixo verde",
  red_axis: "Eixo vermelho",
  green_queue: "Fila no verde",
  red_queue: "Fila no vermelho",
  green_pressure: "Pressão do verde",
  red_pressure: "Pressão do vermelho",
  green_time: "Verde há (ticks)",
};

let ws;
let paused = false;
let lastRule = null;
let latest = null;                 // último estado recebido do servidor
const cars = new Map();            // id -> carro sendo animado
const speedInput = document.getElementById("speed");
const tickDelay = () => parseFloat(speedInput.value);   // segundos por tick

// ---------- conexão ----------

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    setStatus(true);
    cars.clear();
    latest = null;
    send({ cmd: "speed", value: tickDelay() });
  };
  ws.onclose = () => { setStatus(false); setTimeout(connect, 1500); };
  ws.onmessage = (ev) => render(JSON.parse(ev.data));
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

function setStatus(on) {
  const el = document.getElementById("status");
  el.textContent = on ? "conectado" : "desconectado";
  el.className = "status " + (on ? "on" : "off");
}

// ---------- posições (mão direita, como no Brasil) ----------

// Centro do i-ésimo carro da fila de cada via.
function slotCenter(dir, i) {
  const d = HALF + 8 + CAR_L / 2 + i * SLOT;   // distância até o centro do cruzamento
  switch (dir) {
    case "N": return { x: C - 30, y: C - d };
    case "S": return { x: C + 30, y: C + d };
    case "E": return { x: C + d, y: C - 30 };
    case "W": return { x: C - d, y: C + 30 };
  }
}

// Onde o carro nasce (fora da tela, no começo da via).
const spawnPoint = (dir) => slotCenter(dir, MAX_VISIBLE + 1);

// Para onde o carro vai depois de passar pelo cruzamento (sai pelo lado oposto).
function exitPoint(dir) {
  switch (dir) {
    case "N": return { x: C - 30, y: SIZE + 40 };
    case "S": return { x: C + 30, y: -40 };
    case "E": return { x: -40, y: C - 30 };
    case "W": return { x: SIZE + 40, y: C + 30 };
  }
}

// ---------- animação ----------

const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
const moveDuration = () => tickDelay() * 1000 * 0.85;

function progress(car, now) {
  return car.dur ? Math.min(1, Math.max(0, (now - car.t0) / car.dur)) : 1;
}

function position(car, now) {
  const e = ease(progress(car, now));
  return { x: car.fromX + (car.toX - car.fromX) * e, y: car.fromY + (car.toY - car.fromY) * e };
}

function moveTo(car, target, dur, now) {
  const p = position(car, now);
  Object.assign(car, { fromX: p.x, fromY: p.y, toX: target.x, toY: target.y, t0: now, dur });
}

// Compara o novo estado com os carros na tela: novos entram, os da fila andam, os que sumiram atravessam.
function updateCars(state) {
  const now = performance.now();
  const seen = new Set();
  for (const dir of DIRS) {
    state.queues[dir].forEach((c, i) => {
      seen.add(c.id);
      let car = cars.get(c.id);
      if (!car) {
        const s = spawnPoint(dir);
        car = { id: c.id, dir, emergency: c.emergency, fromX: s.x, fromY: s.y, toX: s.x, toY: s.y, t0: now, dur: 0 };
        cars.set(c.id, car);
      }
      const target = i < MAX_VISIBLE ? slotCenter(dir, i) : spawnPoint(dir);
      if (target.x !== car.toX || target.y !== car.toY) moveTo(car, target, moveDuration(), now);
    });
  }
  for (const car of cars.values()) {
    if (!seen.has(car.id) && !car.leaving) {
      car.leaving = true;
      moveTo(car, exitPoint(car.dir), moveDuration() * 1.6, now);
    }
  }
}

// ---------- desenho do ambiente ----------

const LIGHT_POS = {
  N: [C - HALF - 14, C - HALF - 12],
  S: [C + HALF + 14, C + HALF + 12],
  E: [C + HALF + 12, C - HALF - 14],
  W: [C - HALF - 12, C + HALF + 14],
};

// onde aparece o "+N" quando a fila não cabe na tela
const OVERFLOW_POS = {
  N: [C - HALF - 22, 52],
  S: [C + HALF + 22, SIZE - 18],
  E: [SIZE - 22, C - HALF - 18],
  W: [22, C + HALF + 18],
};

function lightColor(dir, signal) {
  if (AXIS_OF[dir] !== signal.axis) return "#dc2626";
  return signal.phase === "GREEN" ? "#16a34a" : "#eab308";
}

function drawRoads() {
  ctx.fillStyle = "#86a96b";
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.fillStyle = "#3f4450";
  ctx.fillRect(C - HALF, 0, HALF * 2, SIZE);
  ctx.fillRect(0, C - HALF, SIZE, HALF * 2);

  // faixa central tracejada
  ctx.strokeStyle = "#f5f5f5";
  ctx.lineWidth = 2;
  ctx.setLineDash([12, 10]);
  ctx.beginPath();
  ctx.moveTo(C, 0); ctx.lineTo(C, C - HALF);
  ctx.moveTo(C, C + HALF); ctx.lineTo(C, SIZE);
  ctx.moveTo(0, C); ctx.lineTo(C - HALF, C);
  ctx.moveTo(C + HALF, C); ctx.lineTo(SIZE, C);
  ctx.stroke();
  ctx.setLineDash([]);

  // linhas de retenção
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(C - HALF, C - HALF - 2); ctx.lineTo(C, C - HALF - 2);
  ctx.moveTo(C, C + HALF + 2); ctx.lineTo(C + HALF, C + HALF + 2);
  ctx.moveTo(C + HALF + 2, C - HALF); ctx.lineTo(C + HALF + 2, C);
  ctx.moveTo(C - HALF - 2, C); ctx.lineTo(C - HALF - 2, C + HALF);
  ctx.stroke();
}

// Clareia (pct > 0) ou escurece (pct < 0) uma cor hex.
function shade(hex, pct) {
  const n = parseInt(hex.slice(1), 16);
  const f = (v) => Math.round(pct < 0 ? v * (1 + pct / 100) : v + (255 - v) * (pct / 100));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`;
}

function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  ctx.fill();
}

function polygon(...pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0], pts[1]);
  for (let i = 2; i < pts.length; i += 2) ctx.lineTo(pts[i], pts[i + 1]);
  ctx.closePath();
  ctx.fill();
}

// Carro visto de cima, desenhado "apontando para cima" e depois girado para a sua direção.
function drawCar(car, x, y, moving, now) {
  const L = CAR_L, W = CAR_W;
  const base = car.emergency ? "#f8fafc" : COLORS[car.id % COLORS.length];
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(HEADING[car.dir]);

  // sombra
  ctx.fillStyle = "rgba(0,0,0,.3)";
  roundRect(-W / 2 + 2, -L / 2 + 3, W, L, 5);

  // rodas
  ctx.fillStyle = "#111";
  for (const wy of [-L / 2 + 5, L / 2 - 10]) {
    ctx.fillRect(-W / 2 - 1.5, wy, 3, 5);
    ctx.fillRect(W / 2 - 1.5, wy, 3, 5);
  }

  // carroceria com degradê lateral (dá sensação de volume)
  const g = ctx.createLinearGradient(-W / 2, 0, W / 2, 0);
  g.addColorStop(0, shade(base, -30));
  g.addColorStop(0.5, shade(base, 25));
  g.addColorStop(1, shade(base, -30));
  ctx.fillStyle = g;
  roundRect(-W / 2, -L / 2, W, L, 5);

  // para-brisa e vidro traseiro
  ctx.fillStyle = "#a5d3f0";
  polygon(-W / 2 + 2, -L / 2 + 10, W / 2 - 2, -L / 2 + 10, W / 2 - 3.5, -L / 2 + 5.5, -W / 2 + 3.5, -L / 2 + 5.5);
  ctx.fillStyle = "#7fb3d5";
  polygon(-W / 2 + 2.5, L / 2 - 7, W / 2 - 2.5, L / 2 - 7, W / 2 - 3.5, L / 2 - 3.5, -W / 2 + 3.5, L / 2 - 3.5);

  // teto
  ctx.fillStyle = shade(base, -12);
  roundRect(-W / 2 + 3, -L / 2 + 10.5, W - 6, L - 18, 2);

  // faróis
  ctx.fillStyle = "#fef9c3";
  ctx.fillRect(-W / 2 + 1.5, -L / 2 + 0.5, 3.5, 2);
  ctx.fillRect(W / 2 - 5, -L / 2 + 0.5, 3.5, 2);

  // lanternas: brilham forte quando o carro está parado (freando)
  ctx.fillStyle = moving ? "#7f1d1d" : "#ff3b3b";
  if (!moving) { ctx.shadowColor = "#ff3b3b"; ctx.shadowBlur = 6; }
  ctx.fillRect(-W / 2 + 1.5, L / 2 - 2.5, 3.5, 2);
  ctx.fillRect(W / 2 - 5, L / 2 - 2.5, 3.5, 2);
  ctx.shadowBlur = 0;

  if (car.emergency) drawSiren(W, now);
  ctx.restore();
}

// Detalhes da ambulância: faixas, cruz no teto e giroflex piscando.
function drawSiren(W, now) {
  ctx.fillStyle = "#dc2626";
  ctx.fillRect(-W / 2, 2, 2, 8);
  ctx.fillRect(W / 2 - 2, 2, 2, 8);
  ctx.fillRect(-1, 1.5, 2, 6);
  ctx.fillRect(-3, 3.5, 6, 2);

  const on = Math.floor(now / 250) % 2 === 0;
  const [left, right] = on ? ["#ef4444", "#3b82f6"] : ["#3b82f6", "#ef4444"];
  ctx.shadowBlur = 10;
  ctx.fillStyle = ctx.shadowColor = left;
  ctx.fillRect(-W / 2 + 3, -3, W / 2 - 3, 3);
  ctx.fillStyle = ctx.shadowColor = right;
  ctx.fillRect(0, -3, W / 2 - 3, 3);
  ctx.shadowBlur = 0;
}

function drawCars(now) {
  for (const [id, car] of cars) {
    const done = progress(car, now) >= 1;
    if (car.leaving && done) { cars.delete(id); continue; }
    const p = position(car, now);
    drawCar(car, p.x, p.y, !done, now);
  }
}

function drawOverlays(state) {
  for (const dir of DIRS) {
    const extra = state.queues[dir].length - MAX_VISIBLE;
    if (extra > 0) {
      const [x, y] = OVERFLOW_POS[dir];
      ctx.fillStyle = "rgba(0,0,0,.65)";
      roundRect(x - 18, y - 10, 36, 20, 10);
      ctx.fillStyle = "#fff";
      ctx.font = "bold 12px system-ui";
      ctx.textAlign = "center";
      ctx.fillText(`+${extra}`, x, y + 4);
      ctx.textAlign = "start";
    }
    // marca visual: sensor quebrado e pico de tráfego
    const [lx, ly] = LIGHT_POS[dir];
    ctx.font = "bold 12px system-ui";
    if (state.sensors_failed.includes(dir)) {
      ctx.fillStyle = "#fde047";
      ctx.fillText("sensor X", lx - 24, ly + 26);
    }
    if (state.surge.includes(dir)) {
      ctx.fillStyle = "#fff";
      ctx.fillText("pico", lx - 12, ly - 16);
    }
  }
}

function drawLights(signal) {
  for (const dir of DIRS) {
    const [x, y] = LIGHT_POS[dir];
    ctx.fillStyle = "#111";
    ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = lightColor(dir, signal);
    ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "bold 10px system-ui";
    ctx.textAlign = "center";
    ctx.fillText(dir, x, y + 4);
    ctx.textAlign = "start";
  }
}

function drawHud(state) {
  ctx.fillStyle = "rgba(0,0,0,.55)";
  ctx.fillRect(8, 8, 190, 26);
  ctx.fillStyle = "#fff";
  ctx.font = "bold 13px system-ui";
  const fase = state.signal.phase === "GREEN" ? "verde" : "amarelo";
  ctx.fillText(`tick ${state.tick}  |  ${state.signal.axis} ${fase}`, 16, 26);
}

// Laço de desenho: roda a ~60 quadros/s, independente do ritmo dos ticks.
function frame() {
  const now = performance.now();   // mesmo relógio usado em updateCars
  drawRoads();
  drawCars(now);
  if (latest) {
    drawOverlays(latest);
    drawLights(latest.signal);
    drawHud(latest);
  }
  requestAnimationFrame(frame);
}

// ---------- painéis ----------

function renderPercept(p) {
  const tbody = document.querySelector("#percept tbody");
  tbody.innerHTML = "";
  for (const dir of DIRS) {
    const fail = p.queue[dir] === null;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${dir}</td>
      <td class="${fail ? "fail" : ""}">${fail ? "falhou" : p.queue[dir]}</td>
      <td class="${fail ? "fail" : ""}">${fail ? "falhou" : p.max_wait[dir]}</td>
      <td>${p.emergency.includes(dir) ? "SIM" : "-"}</td>`;
    tbody.appendChild(tr);
  }
  const fase = p.phase === "GREEN" ? "verde" : "amarelo";
  document.getElementById("signal-line").textContent =
    `Semáforo lido: eixo ${p.axis} em ${fase} há ${p.phase_time} ticks.`;
}

function renderDecision(d) {
  const action = document.getElementById("action");
  action.textContent = d.action === "SWITCH" ? "TROCAR" : "MANTER";
  action.className = "badge " + d.action;
  document.getElementById("rule").textContent = d.rule;
  document.getElementById("reason").textContent = d.reason;
  fillTable("#metrics", d.metrics, METRIC_LABELS);
}

function fillTable(selector, data, labels) {
  const tbody = document.querySelector(selector + " tbody");
  tbody.innerHTML = "";
  for (const [k, v] of Object.entries(data)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${labels[k] || k}</td><td><strong>${v}</strong></td>`;
    tbody.appendChild(tr);
  }
}

function addLog(text, cls) {
  const log = document.getElementById("log");
  const li = document.createElement("li");
  li.textContent = text;
  if (cls) li.className = cls;
  log.prepend(li);
  while (log.children.length > 40) log.lastChild.remove();
}

function renderLog(state) {
  for (const ev of state.events) addLog(`t=${state.tick} ${ev}`, "event");
  const d = state.decision;
  // registra trocas e mudanças de regra (ignora o "amarelo em andamento")
  if (d.rule !== "EM_TRANSICAO" && (d.action === "SWITCH" || d.rule !== lastRule)) {
    const verb = d.action === "SWITCH" ? "TROCAR" : "MANTER";
    addLog(`t=${state.tick} ${verb} [${d.rule}] ${d.reason}`);
    lastRule = d.rule;
  }
}

function syncToggles(state) {
  document.querySelectorAll('.row[data-cmd="sensor"] button').forEach((b) =>
    b.classList.toggle("active", state.sensors_failed.includes(b.dataset.dir)));
  document.querySelectorAll('.row[data-cmd="surge"] button').forEach((b) =>
    b.classList.toggle("active", state.surge.includes(b.dataset.dir)));
}

function render(state) {
  latest = state;
  updateCars(state);
  renderPercept(state.percept);
  renderDecision(state.decision);
  renderLog(state);
  fillTable("#perf", state.performance, PERF_LABELS);
  syncToggles(state);
}

// ---------- controles ----------

function showSpeed() {
  document.getElementById("speed-value").textContent = `${tickDelay().toFixed(1)} s por tick`;
}

document.getElementById("btn-pause").onclick = (e) => {
  paused = !paused;
  e.target.textContent = paused ? "Continuar" : "Pausar";
  document.getElementById("btn-step").disabled = !paused;
  send({ cmd: "pause", value: paused });
};
document.getElementById("btn-step").onclick = () => send({ cmd: "step" });
speedInput.oninput = () => {
  showSpeed();
  send({ cmd: "speed", value: tickDelay() });
};
document.getElementById("btn-reset").onclick = () => {
  document.getElementById("log").innerHTML = "";
  lastRule = null;
  cars.clear();
  send({ cmd: "reset", seed: 7 });
};

document.querySelectorAll(".row button").forEach((btn) => {
  btn.onclick = () => {
    const cmd = btn.parentElement.dataset.cmd;
    const dir = btn.dataset.dir;
    const on = !btn.classList.contains("active");
    if (cmd === "emergency") send({ cmd: "emergency", dir });
    if (cmd === "sensor") send({ cmd: on ? "fail_sensor" : "repair_sensor", dir });
    if (cmd === "surge") send({ cmd: "surge", dir, on });
  };
});

showSpeed();
requestAnimationFrame(frame);
connect();
