"use strict";

/* ==========================================================================
   Telegram WebApp init
   ========================================================================== */

const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

function getInitData() {
  if (tg && tg.initData) return tg.initData;
  // Позволяет открыть и протестировать WebApp обычным браузером:
  // ?init_data=<строка из scripts/make_test_init_data.py>
  const fromQuery = new URLSearchParams(window.location.search).get("init_data");
  return fromQuery || "";
}

const INIT_DATA = getInitData();

function applyTelegramTheme() {
  if (!tg || !tg.themeParams) return;
  const p = tg.themeParams;
  const root = document.documentElement.style;
  if (p.bg_color) root.setProperty("--tg-bg", p.bg_color);
  if (p.secondary_bg_color) root.setProperty("--tg-secondary-bg", p.secondary_bg_color);
  if (p.text_color) root.setProperty("--tg-text", p.text_color);
  if (p.hint_color) root.setProperty("--tg-hint", p.hint_color);
  if (p.link_color) root.setProperty("--tg-link", p.link_color);
  if (p.button_color) root.setProperty("--tg-button", p.button_color);
  if (p.button_text_color) root.setProperty("--tg-button-text", p.button_text_color);
}

if (tg) {
  tg.ready();
  tg.expand();
  applyTelegramTheme();
  tg.onEvent("themeChanged", applyTelegramTheme);
  if (tg.setHeaderColor) {
    try { tg.setHeaderColor("secondary_bg_color"); } catch (e) { /* некоторые версии клиента не поддерживают */ }
  }
}

/* ==========================================================================
   API
   ========================================================================== */

async function apiRequest(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      Authorization: "tma " + INIT_DATA,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch (e) { /* ignore */ }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

const apiGet = (path) => apiRequest(path);
const apiPost = (path, body) => apiRequest(path, { method: "POST", body });
const apiPatch = (path, body) => apiRequest(path, { method: "PATCH", body });
const apiDelete = (path) => apiRequest(path, { method: "DELETE" });

/* ==========================================================================
   Toast
   ========================================================================== */

let toastTimer = null;
function showToast(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 1800);
}

/* ==========================================================================
   Bottom navigation
   ========================================================================== */

const navButtons = document.querySelectorAll(".nav-btn");
navButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
    navButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".screen").forEach((s) => s.classList.add("hidden"));
    document.getElementById("screen-" + btn.dataset.screen).classList.remove("hidden");
    if (btn.dataset.screen === "history") {
      loadHistory(currentPeriod);
      loadAchievements();
    }
  });
});

/* ==========================================================================
   Calendar
   ========================================================================== */

const MONTH_NAMES = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];
const WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

const today = new Date();
const todayKey = formatDateKey(today);

let viewYear = today.getFullYear();
let viewMonth = today.getMonth() + 1; // 1..12
let selectedDateKey = null;

const monthLabelEl = document.getElementById("monthLabel");
const calGridEl = document.getElementById("calGrid");

function formatDateKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function daysInMonth(year, month) {
  return new Date(year, month, 0).getDate();
}

// Понедельник = 0 ... воскресенье = 6
function mondayIndex(jsWeekday) {
  return (jsWeekday + 6) % 7;
}

async function loadCalendar(year, month) {
  calGridEl.classList.add("loading");
  monthLabelEl.textContent = `${MONTH_NAMES[month - 1]} ${year}`;
  try {
    const data = await apiGet(`/api/calendar?year=${year}&month=${month}`);
    renderCalendar(year, month, data.days);
  } catch (err) {
    showToast("Не удалось загрузить календарь: " + err.message);
    renderCalendar(year, month, []);
  } finally {
    calGridEl.classList.remove("loading");
  }
}

function renderCalendar(year, month, days) {
  const stateByDate = {};
  for (const d of days) stateByDate[d.date] = d.state;

  const totalDays = daysInMonth(year, month);
  const firstWeekday = mondayIndex(new Date(year, month - 1, 1).getDay());

  calGridEl.innerHTML = "";

  for (let i = 0; i < firstWeekday; i++) {
    const filler = document.createElement("div");
    filler.className = "cal-day other-month";
    calGridEl.appendChild(filler);
  }

  for (let day = 1; day <= totalDays; day++) {
    const dateKey = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const state = stateByDate[dateKey] || "empty";

    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = `cal-day state-${state}`;
    if (dateKey === todayKey) cell.classList.add("is-today");
    if (dateKey === selectedDateKey) cell.classList.add("is-selected");
    cell.dataset.date = dateKey;

    const num = document.createElement("span");
    num.className = "day-num";
    num.textContent = String(day);
    cell.appendChild(num);

    const dot = document.createElement("span");
    dot.className = "state-dot";
    cell.appendChild(dot);

    cell.addEventListener("click", () => openDay(dateKey));
    calGridEl.appendChild(cell);
  }
}

document.getElementById("prevMonth").addEventListener("click", () => {
  viewMonth -= 1;
  if (viewMonth < 1) { viewMonth = 12; viewYear -= 1; }
  loadCalendar(viewYear, viewMonth);
});

document.getElementById("nextMonth").addEventListener("click", () => {
  viewMonth += 1;
  if (viewMonth > 12) { viewMonth = 1; viewYear += 1; }
  loadCalendar(viewYear, viewMonth);
});

/* ==========================================================================
   Task sheet (список задач на дату)
   ========================================================================== */

const sheetOverlay = document.getElementById("sheetOverlay");
const sheetDateEl = document.getElementById("sheetDate");
const sheetBodyEl = document.getElementById("sheetBody");

const WEEKDAY_FULL = [
  "воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота",
];

function formatSheetDate(dateKey) {
  const [y, m, d] = dateKey.split("-").map(Number);
  const dateObj = new Date(y, m - 1, d);
  return `${d} ${MONTH_NAMES[m - 1].toLowerCase()}, ${WEEKDAY_FULL[dateObj.getDay()]}`;
}

async function openDay(dateKey) {
  selectedDateKey = dateKey;
  document.querySelectorAll(".cal-day").forEach((c) => {
    c.classList.toggle("is-selected", c.dataset.date === dateKey);
  });

  sheetDateEl.textContent = formatSheetDate(dateKey);
  sheetBodyEl.innerHTML = '<div class="sheet-loading">Загрузка…</div>';
  sheetOverlay.classList.remove("hidden");

  try {
    const data = await apiGet(`/api/tasks?date=${dateKey}`);
    renderTaskList(data.tasks);
  } catch (err) {
    sheetBodyEl.innerHTML = `<div class="sheet-empty">Ошибка загрузки: ${escapeHtml(err.message)}</div>`;
  }
}

function closeSheet() {
  sheetOverlay.classList.add("hidden");
}

document.getElementById("sheetClose").addEventListener("click", closeSheet);
sheetOverlay.addEventListener("click", (e) => {
  if (e.target === sheetOverlay) closeSheet();
});

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

const STATUS_ICON = { pending: "🟡", done: "✅", missed: "❌" };

const REPEAT_LABEL = {
  once: "Один раз",
  daily: "Каждый день",
  weekdays: "По будням",
  weekends: "По выходным",
  weekly: "Каждую неделю",
  monthly: "Каждый месяц",
  custom: "Особое повторение",
};

let currentTasks = []; // задачи, сейчас показанные в открытом sheet'е (по id)

function renderTaskList(tasks) {
  currentTasks = tasks;
  if (!tasks.length) {
    sheetBodyEl.innerHTML = '<div class="sheet-empty">На этот день задач нет</div>';
    return;
  }

  sheetBodyEl.innerHTML = "";
  for (const task of tasks) {
    const row = document.createElement("div");
    row.className = `task-row status-${task.status}`;
    row.dataset.taskId = String(task.id);

    row.innerHTML = `
      <span class="task-time">${task.time.slice(0, 5)}</span>
      <span class="task-title">${escapeHtml(task.title)}${task.is_recurring ? '<span class="task-recurring-mark">🔁</span>' : ""}</span>
      <span class="task-actions">
        <button data-action="done" title="Выполнено">✅</button>
        <button data-action="missed" title="Не выполнено">❌</button>
        <button data-action="edit" title="Редактировать">✏️</button>
        <button data-action="delete" title="Удалить">🗑</button>
        <button data-action="move" title="Перенести">📅</button>
      </span>
    `;

    row.querySelectorAll(".task-actions button").forEach((btn) => {
      btn.addEventListener("click", () => handleTaskAction(task, btn.dataset.action));
    });

    sheetBodyEl.appendChild(row);
  }
}

async function refreshAfterMutation() {
  // Состояние дней в календаре могло измениться (выполнено/не выполнено/удалено).
  await loadCalendar(viewYear, viewMonth);
  if (selectedDateKey && !sheetOverlay.classList.contains("hidden")) {
    try {
      const data = await apiGet(`/api/tasks?date=${selectedDateKey}`);
      renderTaskList(data.tasks);
    } catch (err) {
      showToast("Не удалось обновить список: " + err.message);
    }
  }
}

async function handleTaskAction(task, action) {
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");

  if (action === "done" || action === "missed") {
    try {
      const result = await apiPost(`/api/tasks/${task.id}/status`, { status: action });
      await refreshAfterMutation();
      announceNewAchievements(result.new_achievements);
    } catch (err) {
      showToast("Не удалось изменить статус: " + err.message);
    }
    return;
  }

  if (action === "edit") {
    const scope = await resolveScope(task, "edit");
    if (!scope) return;
    openEditSheet(task, scope);
    return;
  }

  if (action === "delete") {
    const scope = await resolveScope(task, "delete");
    if (!scope) return;
    try {
      await apiDelete(`/api/tasks/${task.id}?scope=${scope}`);
      await refreshAfterMutation();
      showToast(scope === "series" ? "Серия удалена" : "Задача удалена");
    } catch (err) {
      showToast("Не удалось удалить: " + err.message);
    }
    return;
  }

  if (action === "move") {
    openMoveSheet(task);
  }
}

/* Для повторяющейся задачи спрашивает "изменить/удалить только эту задачу"
   или "всю серию" (формулировка из ТЗ). Для разовой задачи подтверждение
   нужно только при удалении. */
async function resolveScope(task, action) {
  const isDelete = action === "delete";

  if (!task.is_recurring) {
    if (!isDelete) return "this";
    const picked = await showActionSheet({
      title: "Удалить задачу?",
      message: escapeSheetTitle(task.title),
      buttons: [
        { id: "this", label: "Удалить", destructive: true },
        { id: null, label: "Отмена", cancel: true },
      ],
    });
    return picked === "this" ? "this" : null;
  }

  return showActionSheet({
    title: isDelete ? "Удалить задачу?" : "Изменить задачу?",
    message: `${escapeSheetTitle(task.title)} · ${REPEAT_LABEL[task.repeat_type] || task.repeat_type}`,
    buttons: [
      { id: "this", label: isDelete ? "Удалить только эту задачу" : "Изменить только эту задачу" },
      { id: "series", label: isDelete ? "Удалить всю серию" : "Изменить всю серию", destructive: isDelete },
      { id: null, label: "Отмена", cancel: true },
    ],
  });
}

function escapeSheetTitle(text) {
  return text.length > 40 ? text.slice(0, 40) + "…" : text;
}

/* ==========================================================================
   Универсальный action sheet (выбор варианта / подтверждение)
   ========================================================================== */

const actionSheetOverlay = document.getElementById("actionSheetOverlay");
const actionSheetTitleEl = document.getElementById("actionSheetTitle");
const actionSheetMessageEl = document.getElementById("actionSheetMessage");
const actionSheetButtonsEl = document.getElementById("actionSheetButtons");

function showActionSheet({ title, message, buttons }) {
  return new Promise((resolve) => {
    actionSheetTitleEl.textContent = title || "";
    actionSheetMessageEl.textContent = message || "";
    actionSheetMessageEl.style.display = message ? "block" : "none";
    actionSheetButtonsEl.innerHTML = "";

    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      actionSheetOverlay.classList.add("hidden");
      resolve(value);
    };

    for (const b of buttons) {
      const btn = document.createElement("button");
      btn.textContent = b.label;
      if (b.destructive) btn.classList.add("destructive");
      if (b.cancel) btn.classList.add("cancel");
      btn.addEventListener("click", () => finish(b.id));
      actionSheetButtonsEl.appendChild(btn);
    }

    actionSheetOverlay.addEventListener(
      "click",
      (e) => { if (e.target === actionSheetOverlay) finish(null); },
      { once: true }
    );

    actionSheetOverlay.classList.remove("hidden");
  });
}

/* ==========================================================================
   Редактирование задачи
   ========================================================================== */

const editOverlay = document.getElementById("editOverlay");
const editTitleEl = document.getElementById("editTitle");
const editDateEl = document.getElementById("editDate");
const editTimeEl = document.getElementById("editTime");
const editRepeatEl = document.getElementById("editRepeat");
const editSubmitEl = document.getElementById("editSubmit");

let editingTask = null;
let editingScope = "this";

function openEditSheet(task, scope) {
  editingTask = task;
  editingScope = scope;

  editTitleEl.value = task.title;
  editDateEl.value = task.date;
  editTimeEl.value = task.time.slice(0, 5);
  editRepeatEl.value = task.repeat_type || "once";

  // Дата при редактировании серии не меняется (для переноса есть 📅) —
  // поле остаётся видимым для контекста, но недоступным для правки.
  editDateEl.disabled = scope === "series";
  // Повторение имеет смысл менять только для серии.
  editRepeatEl.closest(".field").style.display = scope === "series" ? "" : "none";

  editOverlay.classList.remove("hidden");
}

document.getElementById("editClose").addEventListener("click", () => editOverlay.classList.add("hidden"));
editOverlay.addEventListener("click", (e) => { if (e.target === editOverlay) editOverlay.classList.add("hidden"); });

editSubmitEl.addEventListener("click", async () => {
  if (!editingTask) return;
  const title = editTitleEl.value.trim();
  if (!title) { showToast("Введите название задачи"); return; }

  const payload = { scope: editingScope, title, time: editTimeEl.value + ":00" };
  if (editingScope === "this") payload.date = editDateEl.value;
  if (editingScope === "series") payload.repeat_type = editRepeatEl.value;

  editSubmitEl.disabled = true;
  try {
    await apiPatch(`/api/tasks/${editingTask.id}`, payload);
    editOverlay.classList.add("hidden");
    showToast("Задача сохранена");
    await refreshAfterMutation();
  } catch (err) {
    showToast("Не удалось сохранить: " + err.message);
  } finally {
    editSubmitEl.disabled = false;
  }
});

/* ==========================================================================
   Перенос задачи
   ========================================================================== */

const moveOverlay = document.getElementById("moveOverlay");
const moveDateEl = document.getElementById("moveDate");
const moveTimeEl = document.getElementById("moveTime");
const moveSubmitEl = document.getElementById("moveSubmit");

let movingTask = null;

function openMoveSheet(task) {
  movingTask = task;
  moveDateEl.value = task.date;
  moveTimeEl.value = task.time.slice(0, 5);
  moveOverlay.classList.remove("hidden");
}

document.getElementById("moveClose").addEventListener("click", () => moveOverlay.classList.add("hidden"));
moveOverlay.addEventListener("click", (e) => { if (e.target === moveOverlay) moveOverlay.classList.add("hidden"); });

moveSubmitEl.addEventListener("click", async () => {
  if (!movingTask) return;
  if (!moveDateEl.value || !moveTimeEl.value) { showToast("Укажите дату и время"); return; }

  moveSubmitEl.disabled = true;
  try {
    await apiPost(`/api/tasks/${movingTask.id}/move`, {
      date: moveDateEl.value,
      time: moveTimeEl.value + ":00",
    });
    moveOverlay.classList.add("hidden");
    showToast("Задача перенесена");
    await refreshAfterMutation();
  } catch (err) {
    showToast("Не удалось перенести: " + err.message);
  } finally {
    moveSubmitEl.disabled = false;
  }
});

/* ==========================================================================
   Создание задачи (экран "Добавить")
   ========================================================================== */

const addTitleEl = document.getElementById("addTitle");
const addDateEl = document.getElementById("addDate");
const addTimeEl = document.getElementById("addTime");
const addRepeatEl = document.getElementById("addRepeat");
const addSubmitEl = document.getElementById("addSubmit");

function prefillAddForm() {
  addDateEl.value = selectedDateKey || todayKey;
  addTimeEl.value = "09:00";
}
prefillAddForm();

addSubmitEl.addEventListener("click", async () => {
  const title = addTitleEl.value.trim();
  if (!title) { showToast("Введите название задачи"); return; }
  if (!addDateEl.value || !addTimeEl.value) { showToast("Укажите дату и время"); return; }

  addSubmitEl.disabled = true;
  try {
    await apiPost("/api/tasks", {
      title,
      date: addDateEl.value,
      time: addTimeEl.value + ":00",
      repeat_type: addRepeatEl.value,
    });
    showToast("Задача создана");
    const createdDateKey = addDateEl.value;
    addTitleEl.value = "";
    addRepeatEl.value = "once";

    // Переключаемся на календарь и открываем день созданной задачи.
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.screen === "calendar"));
    document.querySelectorAll(".screen").forEach((s) => s.classList.add("hidden"));
    document.getElementById("screen-calendar").classList.remove("hidden");

    const [y, m] = createdDateKey.split("-").map(Number);
    if (y !== viewYear || m !== viewMonth) {
      viewYear = y; viewMonth = m;
    }
    await loadCalendar(viewYear, viewMonth);
    await openDay(createdDateKey);
    prefillAddForm();
  } catch (err) {
    showToast("Не удалось создать задачу: " + err.message);
  } finally {
    addSubmitEl.disabled = false;
  }
});

/* ==========================================================================
   История (статистика)
   ========================================================================== */

const historyBodyEl = document.getElementById("historyBody");
const periodTabsEl = document.getElementById("periodTabs");
let currentPeriod = "today";

periodTabsEl.querySelectorAll(".period-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.classList.contains("active")) return;
    if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
    periodTabsEl.querySelectorAll(".period-tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentPeriod = btn.dataset.period;
    loadHistory(currentPeriod);
  });
});

function formatShortDate(dateKey) {
  const [y, m, d] = dateKey.split("-").map(Number);
  return `${d} ${MONTH_NAMES[m - 1].toLowerCase()}`;
}

function renderHistoryTaskRow(task) {
  const icon = STATUS_ICON[task.status] || "";
  return `
    <div class="history-task-row">
      <span class="task-time">${task.time.slice(0, 5)}</span>
      <span class="task-title">${escapeHtml(task.title)}</span>
      <span class="history-date">${icon} ${formatShortDate(task.date)}</span>
    </div>
  `;
}

function renderHistorySection(title, tasks) {
  const body = tasks.length
    ? tasks.map(renderHistoryTaskRow).join("")
    : '<div class="history-empty">Пока нет данных</div>';
  return `
    <div class="history-section">
      <div class="history-section-title">${title}</div>
      ${body}
    </div>
  `;
}

function renderHistory(data) {
  const productiveDay = data.most_productive_day
    ? `${formatShortDate(data.most_productive_day.date)} · ${data.most_productive_day.done_count}`
    : "—";

  historyBodyEl.innerHTML = `
    <div class="history-summary">
      <div class="percent-ring" style="--percent:${data.percent}"><span class="percent-value">${data.percent}%</span></div>
      <div class="summary-counts">
        <div class="summary-count"><span class="summary-icon">✅</span><span class="summary-num">${data.done_count}</span><span class="summary-label">Выполнено</span></div>
        <div class="summary-count"><span class="summary-icon">❌</span><span class="summary-num">${data.missed_count}</span><span class="summary-label">Не выполнено</span></div>
      </div>
    </div>
    <div class="stat-cards">
      <div class="stat-card"><span class="stat-icon">🔥</span><span class="stat-value">${data.current_streak}</span><span class="stat-label">Текущая серия</span></div>
      <div class="stat-card"><span class="stat-icon">🏆</span><span class="stat-value">${data.best_streak}</span><span class="stat-label">Лучшая серия</span></div>
      <div class="stat-card"><span class="stat-icon">📅</span><span class="stat-value">${productiveDay}</span><span class="stat-label">Продуктивный день</span></div>
    </div>
    ${renderHistorySection("Последние выполненные", data.recent_done)}
    ${renderHistorySection("Последние пропущенные", data.recent_missed)}
  `;
}

async function loadHistory(period) {
  historyBodyEl.innerHTML = '<div class="sheet-loading">Загрузка…</div>';
  try {
    const data = await apiGet(`/api/history?period=${period}`);
    renderHistory(data);
  } catch (err) {
    historyBodyEl.innerHTML = `<div class="sheet-empty">Ошибка загрузки: ${escapeHtml(err.message)}</div>`;
  }
}

/* ==========================================================================
   Достижения (блок на экране «История»)
   ========================================================================== */

const achievementsGridEl = document.getElementById("achievementsGrid");

function renderAchievements(achievements) {
  achievementsGridEl.innerHTML = achievements
    .map(
      (a) => `
        <div class="achievement-card ${a.unlocked ? "" : "locked"}" title="${escapeHtml(a.description)}">
          <span class="achievement-icon">${a.icon}</span>
          <span class="achievement-title">${escapeHtml(a.title)}</span>
        </div>
      `
    )
    .join("");
}

async function loadAchievements() {
  achievementsGridEl.innerHTML = '<div class="sheet-loading">Загрузка…</div>';
  try {
    const data = await apiGet("/api/achievements");
    renderAchievements(data.achievements);
  } catch (err) {
    achievementsGridEl.innerHTML = `<div class="sheet-empty">Ошибка загрузки: ${escapeHtml(err.message)}</div>`;
  }
}

/* Показывает тост о новых достижениях (пришедших в ответе на смену статуса
   задачи) и обновляет сетку достижений, если экран «История» уже открыт —
   чтобы не показывать устаревшую (locked) карточку до следующего перехода
   на этот экран. */
function announceNewAchievements(newAchievements) {
  if (!newAchievements || !newAchievements.length) return;
  const names = newAchievements.map((a) => `${a.icon} ${a.title}`).join(", ");
  showToast(`Новое достижение: ${names}`);
  if (!document.getElementById("screen-history").classList.contains("hidden")) {
    loadAchievements();
  }
}

/* ==========================================================================
   Старт
   ========================================================================== */

loadCalendar(viewYear, viewMonth);
