/**
 * Spotify to YouTube Music — Frontend Application Logic
 */

let currentTracks = [];
let currentPlaylistName = "";
let activeJobId = null;
let pollInterval = null;

// DOM Elements
const formFetchUrl = document.getElementById("form-fetch-url");
const inputUrl = document.getElementById("input-url");
const btnFetchUrl = document.getElementById("btn-fetch-url");
const spinnerUrl = document.getElementById("spinner-url");
const iconUrl = document.getElementById("icon-url");

const formFetchUser = document.getElementById("form-fetch-user");
const inputUsername = document.getElementById("input-username");
const btnFetchUser = document.getElementById("btn-fetch-user");
const spinnerUser = document.getElementById("spinner-user");
const iconUser = document.getElementById("icon-user");
const userPlaylistsContainer = document.getElementById("user-playlists-container");
const userPlaylistsGrid = document.getElementById("user-playlists-grid");
const userProfileBanner = document.getElementById("user-profile-banner");
const userProfileBadge = document.getElementById("user-profile-badge");
const btnOpenSpotifyProfile = document.getElementById("btn-open-spotify-profile");
const btnSwitchToUrlTab = document.getElementById("btn-switch-to-url-tab");
const userPlaylistsCount = document.getElementById("user-playlists-count");

const dropzoneCsv = document.getElementById("dropzone-csv");
const fileCsv = document.getElementById("file-csv");

const previewSection = document.getElementById("preview-section");
const inputTargetName = document.getElementById("input-target-name");
const countNumber = document.getElementById("count-number");
const switchSync = document.getElementById("switch-sync");
const btnStartTransfer = document.getElementById("btn-start-transfer");

// Plan Elements
const btnRefreshPlan = document.getElementById("btn-refresh-plan");
const spinnerPlan = document.getElementById("spinner-plan");
const iconPlan = document.getElementById("icon-plan");
const planResultAlert = document.getElementById("plan-result-alert");
const planStatusIcon = document.getElementById("plan-status-icon");
const planTitle = document.getElementById("plan-title");
const planDescription = document.getElementById("plan-description");
const planStatsContainer = document.getElementById("plan-stats-container");
const planBadgeAction = document.getElementById("plan-badge-action");
const planStatToAdd = document.getElementById("plan-stat-to-add");
const planStatAlready = document.getElementById("plan-stat-already");
const planListsAccordion = document.getElementById("plan-lists-accordion");
const planDetailsCount = document.getElementById("plan-details-count");
const planTracksBody = document.getElementById("plan-tracks-body");
const pillCountAdd = document.getElementById("pill-count-add");
const pillCountAlready = document.getElementById("pill-count-already");
const pillCountAll = document.getElementById("pill-count-all");

const monitorSection = document.getElementById("monitor-section");
const transferProgressBar = document.getElementById("transfer-progress-bar");
const progressPercent = document.getElementById("progress-percent");
const statProcessed = document.getElementById("stat-processed");
const statAdded = document.getElementById("stat-added");
const statExisting = document.getElementById("stat-existing");
const statNotFound = document.getElementById("stat-notfound");
const liveConsole = document.getElementById("live-console");
const logCount = document.getElementById("log-count");
const badgeStatus = document.getElementById("badge-status");
const finishedActions = document.getElementById("finished-actions");
const finishedSummaryText = document.getElementById("finished-summary-text");
const btnDlNotFound = document.getElementById("btn-dl-notfound");
const btnDlSpotify = document.getElementById("btn-dl-spotify");

// Auth Elements
const btnUploadAuthFile = document.getElementById("btn-upload-auth-file");
const inputAuthFile = document.getElementById("input-auth-file");
const spinnerAuthUpload = document.getElementById("spinner-auth-upload");
const btnSaveAuthText = document.getElementById("btn-save-auth-text");
const textareaAuthJson = document.getElementById("textarea-auth-json");
const spinnerAuthText = document.getElementById("spinner-auth-text");
const modalAuthAlert = document.getElementById("modal-auth-alert");
const modalAuthStatusTitle = document.getElementById("modal-auth-status-title");
const modalAuthStatusMsg = document.getElementById("modal-auth-status-msg");
const authStatusText = document.getElementById("auth-status-text");
const btnAuthStatus = document.getElementById("btn-auth-status");
const authWarningAlert = document.getElementById("auth-warning-alert");

// ── Toast Helper ─────────────────────────────────────────────────────────────
function showToast(message, type = "info") {
  const toastEl = document.getElementById("liveToast");
  const toastIcon = document.getElementById("toast-icon");
  const toastMsg = document.getElementById("toast-message");

  toastMsg.textContent = message;
  toastIcon.className = "fa-solid me-1";

  if (type === "success") {
    toastIcon.classList.add("fa-circle-check", "text-success");
  } else if (type === "danger" || type === "error") {
    toastIcon.classList.add("fa-circle-exclamation", "text-danger");
  } else if (type === "warning") {
    toastIcon.classList.add("fa-triangle-exclamation", "text-warning");
  } else {
    toastIcon.classList.add("fa-circle-info", "text-info");
  }

  const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
  toast.show();
}

// ── Display Tracks in Preview Section ────────────────────────────────────────
let currentPlanData = null;
let currentPlanFilter = "to_add";
let planDebounceTimer = null;

function displayTracksPreview(name, tracks) {
  currentPlaylistName = name;
  currentTracks = tracks;

  inputTargetName.value = name;
  countNumber.textContent = tracks.length;

  previewSection.classList.remove("d-none");
  previewSection.scrollIntoView({ behavior: "smooth" });

  // Disparar automáticamente el análisis previo con YouTube Music
  fetchPlanTransfer();
}

async function fetchPlanTransfer() {
  const targetName = inputTargetName.value.trim();
  if (!targetName || !currentTracks.length) return;

  if (spinnerPlan) spinnerPlan.classList.remove("d-none");
  if (iconPlan) iconPlan.classList.add("d-none");
  if (btnRefreshPlan) btnRefreshPlan.disabled = true;

  planResultAlert.className = "alert alert-dark border-0 rounded-3 mb-3 d-flex align-items-start gap-3";
  planStatusIcon.className = "fa-solid fa-circle-notch fa-spin text-primary fs-4 mt-1";
  planTitle.textContent = "Analizando biblioteca de YouTube Music...";
  planDescription.textContent = `Buscando si ya existe "${targetName}" y calculando diferencias de canciones...`;

  try {
    const resp = await fetch("/api/plan-transfer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        playlist_name: targetName,
        tracks: currentTracks,
        sync_mode: switchSync.checked,
      }),
    });
    const data = await resp.json();

    if (!data.success) {
      planResultAlert.className = "alert alert-warning border-0 rounded-3 mb-3 d-flex align-items-start gap-3";
      planStatusIcon.className = "fa-solid fa-triangle-exclamation text-warning fs-4 mt-1";
      planTitle.textContent = "Configuración de YouTube Music pendiente";
      planDescription.textContent = data.error || "No se pudo realizar el análisis previo.";
      planStatsContainer.classList.add("d-none");
      planListsAccordion.classList.add("d-none");
      return;
    }

    currentPlanData = data.plan;
    renderPlanResult(data.plan);
  } catch (e) {
    planResultAlert.className = "alert alert-danger border-0 rounded-3 mb-3 d-flex align-items-start gap-3";
    planStatusIcon.className = "fa-solid fa-circle-exclamation text-danger fs-4 mt-1";
    planTitle.textContent = "Error de red";
    planDescription.textContent = "No se pudo conectar con el servidor para simular la transferencia.";
  } finally {
    if (spinnerPlan) spinnerPlan.classList.add("d-none");
    if (iconPlan) iconPlan.classList.remove("d-none");
    if (btnRefreshPlan) btnRefreshPlan.disabled = false;
  }
}

function renderPlanResult(plan) {
  planStatsContainer.classList.remove("d-none");
  planListsAccordion.classList.remove("d-none");

  planStatToAdd.textContent = plan.total_a_anadir;
  planStatAlready.textContent = plan.total_ya_existentes;
  pillCountAdd.textContent = plan.total_a_anadir;
  pillCountAlready.textContent = plan.total_ya_existentes;
  pillCountAll.textContent = plan.total_spotify;

  if (plan.tipo_accion === "sincronizar") {
    planResultAlert.className = "alert alert-success border-0 bg-opacity-10 d-flex align-items-start gap-3 rounded-3 mb-3";
    planStatusIcon.className = "fa-solid fa-arrows-rotate text-success fs-4 mt-1";
    planTitle.textContent = `Playlist existente detectada: "${plan.listas_existentes[0]}"`;
    planDescription.textContent = plan.mensaje;
    planBadgeAction.innerHTML = '<span class="badge bg-warning text-dark"><i class="fa-solid fa-arrows-rotate me-1"></i>Sincronización</span>';
  } else {
    planResultAlert.className = "alert alert-info border-0 bg-opacity-10 d-flex align-items-start gap-3 rounded-3 mb-3";
    planStatusIcon.className = "fa-solid fa-circle-plus text-info fs-4 mt-1";
    planTitle.textContent = `Se creará una nueva lista: "${inputTargetName.value.trim()}"`;
    planDescription.textContent = plan.mensaje;
    planBadgeAction.innerHTML = '<span class="badge bg-success"><i class="fa-solid fa-plus me-1"></i>Crear Nueva</span>';
  }

  // Preseleccionar pestaña: si hay para añadir, esa; si ya están todas, ver las existentes
  if (plan.total_a_anadir > 0) {
    currentPlanFilter = "to_add";
  } else {
    currentPlanFilter = "already";
  }
  updatePlanFilterButtons();
  renderPlanTracks();
}

function updatePlanFilterButtons() {
  document.querySelectorAll(".plan-filter-btn").forEach((btn) => {
    if (btn.dataset.filter === currentPlanFilter) {
      btn.className = `btn btn-sm rounded-pill px-3 py-1 fw-semibold plan-filter-btn ${
        currentPlanFilter === "to_add"
          ? "btn-success"
          : currentPlanFilter === "already"
          ? "btn-info text-dark"
          : "btn-secondary"
      }`;
    } else {
      btn.className = `btn btn-sm rounded-pill px-3 py-1 fw-semibold plan-filter-btn ${
        btn.dataset.filter === "to_add"
          ? "btn-outline-success"
          : btn.dataset.filter === "already"
          ? "btn-outline-info"
          : "btn-outline-secondary"
      }`;
    }
  });
}

function renderPlanTracks() {
  if (!currentPlanData) return;
  planTracksBody.innerHTML = "";

  let list = [];
  if (currentPlanFilter === "to_add") {
    list = currentPlanData.canciones_a_anadir || [];
    planDetailsCount.textContent = `${list.length} canciones nuevas`;
  } else if (currentPlanFilter === "already") {
    list = currentPlanData.canciones_ya_existentes || [];
    planDetailsCount.textContent = `${list.length} ya existentes`;
  } else {
    list = currentTracks;
    planDetailsCount.textContent = `${list.length} canciones en total`;
  }

  if (list.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="4" class="text-center text-secondary py-3">No hay canciones en esta categoría.</td>`;
    planTracksBody.appendChild(tr);
    return;
  }

  const toAddSet = new Set(
    (currentPlanData.canciones_a_anadir || []).map((t) => (t.titulo || "").toLowerCase().trim())
  );

  list.slice(0, 150).forEach((t, i) => {
    const isToAdd = toAddSet.has((t.titulo || "").toLowerCase().trim());
    const tr = document.createElement("tr");
    const badgeHtml = isToAdd
      ? '<span class="badge bg-success bg-opacity-25 text-success border border-success border-opacity-50 px-2 py-1"><i class="fa-solid fa-plus me-1"></i>Se añadirá</span>'
      : '<span class="badge bg-secondary bg-opacity-25 text-secondary border border-secondary border-opacity-50 px-2 py-1"><i class="fa-solid fa-check me-1"></i>Ya en YTM</span>';

    tr.innerHTML = `
      <td class="text-secondary small">${i + 1}</td>
      <td class="fw-semibold text-light">${escapeHtml(t.titulo)}</td>
      <td class="text-secondary">${escapeHtml((t.artistas || []).join(", "))}</td>
      <td class="text-end">${badgeHtml}</td>
    `;
    planTracksBody.appendChild(tr);
  });

  if (list.length > 150) {
    const trMore = document.createElement("tr");
    trMore.innerHTML = `
      <td colspan="4" class="text-center text-secondary small py-2">
        ... y ${list.length - 150} canciones más.
      </td>
    `;
    planTracksBody.appendChild(trMore);
  }
}

// Event Listeners para actualizar el plan
if (inputTargetName) {
  inputTargetName.addEventListener("input", () => {
    clearTimeout(planDebounceTimer);
    planDebounceTimer = setTimeout(() => {
      fetchPlanTransfer();
    }, 600);
  });
}

if (switchSync) {
  switchSync.addEventListener("change", () => {
    fetchPlanTransfer();
  });
}

if (btnRefreshPlan) {
  btnRefreshPlan.addEventListener("click", () => {
    fetchPlanTransfer();
  });
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".plan-filter-btn");
  if (btn) {
    currentPlanFilter = btn.dataset.filter;
    updatePlanFilterButtons();
    renderPlanTracks();
  }
});

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/[&<>"']/g, function (m) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
  });
}

// ── Option 1: URL Fetch ──────────────────────────────────────────────────────
formFetchUrl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = inputUrl.value.trim();
  if (!url) return;

  spinnerUrl.classList.remove("d-none");
  iconUrl.classList.add("d-none");
  btnFetchUrl.disabled = true;

  try {
    const resp = await fetch("/api/fetch-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await resp.json();

    if (!data.success) {
      showToast(data.error || "No se pudo extraer la playlist.", "danger");
      return;
    }

    showToast(`Extraídas ${data.count} canciones de "${data.name}"`, "success");
    displayTracksPreview(data.name, data.tracks);
  } catch (err) {
    showToast("Error de red al conectar con el servidor.", "danger");
  } finally {
    spinnerUrl.classList.add("d-none");
    iconUrl.classList.remove("d-none");
    btnFetchUrl.disabled = false;
  }
});

// ── Option 2: User Playlists Fetch ───────────────────────────────────────────
formFetchUser.addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = inputUsername.value.trim();
  if (!username) return;

  spinnerUser.classList.remove("d-none");
  iconUser.classList.add("d-none");
  btnFetchUser.disabled = true;

  try {
    const resp = await fetch("/api/fetch-user", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const data = await resp.json();

    if (data.username && data.profile_url) {
      userProfileBanner.classList.remove("d-none");
      userProfileBadge.textContent = data.username;
      btnOpenSpotifyProfile.href = data.profile_url;
    }

    if (!data.success || !data.playlists || data.playlists.length === 0) {
      userPlaylistsContainer.classList.add("d-none");
      showToast(data.error || "No se encontraron playlists en la vista previa del perfil.", "warning");
      return;
    }

    if (userPlaylistsCount) {
      userPlaylistsCount.textContent = `${data.playlists.length} listas`;
    }
    renderUserPlaylists(data.playlists);
    showToast(`Se encontraron ${data.playlists.length} playlists en la vista previa.`, "success");
  } catch (err) {
    showToast("Error de red al buscar usuario.", "danger");
  } finally {
    spinnerUser.classList.add("d-none");
    iconUser.classList.remove("d-none");
    btnFetchUser.disabled = false;
  }
});

function renderUserPlaylists(playlists) {
  userPlaylistsGrid.innerHTML = "";
  playlists.forEach((pl) => {
    const col = document.createElement("div");
    col.className = "col-12 col-md-6 col-lg-4";
    col.innerHTML = `
      <div class="user-playlist-card bg-black p-3 rounded-3 d-flex align-items-center justify-content-between h-100" data-url="${escapeHtml(pl.url)}" data-name="${escapeHtml(pl.nombre)}">
        <div class="me-2 overflow-hidden flex-grow-1">
          <div class="fw-bold text-light text-truncate" title="${escapeHtml(pl.nombre)}">${escapeHtml(pl.nombre)}</div>
          <div class="text-secondary small d-flex align-items-center gap-2">
            <span><i class="fa-solid fa-music me-1"></i>${pl.total} canciones</span>
          </div>
        </div>
        <div class="d-flex align-items-center gap-1 flex-shrink-0">
          <button class="btn btn-sm btn-outline-secondary rounded-pill px-2 py-1 copy-playlist-btn" title="Copiar enlace directo">
            <i class="fa-regular fa-copy"></i>
          </button>
          <button class="btn btn-sm btn-outline-success rounded-pill px-3 py-1 select-playlist-btn fw-semibold">
            Elegir
          </button>
        </div>
      </div>
    `;

    const btnSelect = col.querySelector(".select-playlist-btn");
    btnSelect.addEventListener("click", () => {
      fetchPlaylistFromCard(pl.url);
    });

    const btnCopy = col.querySelector(".copy-playlist-btn");
    btnCopy.addEventListener("click", (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(pl.url).then(() => {
        showToast(`Enlace copiado al portapapeles: ${pl.nombre}`, "info");
      }).catch(() => {
        showToast(pl.url, "info");
      });
    });

    userPlaylistsGrid.appendChild(col);
  });

  userPlaylistsContainer.classList.remove("d-none");
}

if (btnSwitchToUrlTab) {
  btnSwitchToUrlTab.addEventListener("click", () => {
    const tabUrlBtn = document.getElementById("tab-url-btn");
    if (tabUrlBtn) tabUrlBtn.click();
    setTimeout(() => {
      inputUrl.focus();
    }, 150);
  });
}

async function fetchPlaylistFromCard(url) {
  showToast("Extrayendo canciones de la lista seleccionada...", "info");
  try {
    const resp = await fetch("/api/fetch-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await resp.json();

    if (!data.success) {
      showToast(data.error || "Error al leer playlist.", "danger");
      return;
    }

    displayTracksPreview(data.name, data.tracks);
    showToast(`Cargada playlist "${data.name}" (${data.count} pistas)`, "success");
  } catch (err) {
    showToast("Error al cargar playlist.", "danger");
  }
}

// ── Option 3: CSV Upload & Drag and Drop ─────────────────────────────────────
dropzoneCsv.addEventListener("click", () => fileCsv.click());

["dragenter", "dragover"].forEach((eventName) => {
  dropzoneCsv.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropzoneCsv.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropzoneCsv.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropzoneCsv.classList.remove("dragover");
  });
});

dropzoneCsv.addEventListener("drop", (e) => {
  const dt = e.dataTransfer;
  const files = dt.files;
  if (files.length > 0 && files[0].name.toLowerCase().endsWith(".csv")) {
    uploadCsvFile(files[0]);
  } else {
    showToast("Por favor, sube un archivo con extensión .csv", "warning");
  }
});

fileCsv.addEventListener("change", () => {
  if (fileCsv.files.length > 0) {
    uploadCsvFile(fileCsv.files[0]);
  }
});

async function uploadCsvFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  showToast(`Procesando archivo "${file.name}"...`, "info");

  try {
    const resp = await fetch("/api/upload-csv", {
      method: "POST",
      body: formData,
    });
    const data = await resp.json();

    if (!data.success) {
      showToast(data.error || "Error al procesar CSV.", "danger");
      return;
    }

    displayTracksPreview(data.name, data.tracks);
    showToast(`Cargadas ${data.count} canciones del CSV.`, "success");
  } catch (err) {
    showToast("Error de red al subir archivo CSV.", "danger");
  }
}

// ── Start Transfer ───────────────────────────────────────────────────────────
btnStartTransfer.addEventListener("click", async () => {
  const targetName = inputTargetName.value.trim();
  if (!targetName) {
    showToast("Por favor, escribe un nombre para la lista en YouTube Music.", "warning");
    inputTargetName.focus();
    return;
  }
  if (!currentTracks.length) {
    showToast("No hay canciones cargadas para transferir.", "warning");
    return;
  }

  btnStartTransfer.disabled = true;

  try {
    const resp = await fetch("/api/start-transfer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        playlist_name: targetName,
        tracks: currentTracks,
        sync_mode: switchSync.checked,
      }),
    });
    const data = await resp.json();

    if (!data.success) {
      showToast(data.error || "No se pudo iniciar la transferencia.", "danger");
      btnStartTransfer.disabled = false;
      return;
    }

    activeJobId = data.job_id;
    showToast("¡Transferencia iniciada en segundo plano!", "success");

    // Reveal live monitor
    monitorSection.classList.remove("d-none");
    finishedActions.classList.add("d-none");
    monitorSection.scrollIntoView({ behavior: "smooth" });

    // Start polling
    startPollingJob(activeJobId);
  } catch (err) {
    showToast("Error de red al iniciar la tarea.", "danger");
    btnStartTransfer.disabled = false;
  }
});

// ── Job Polling & Real-Time Console ──────────────────────────────────────────
function startPollingJob(jobId) {
  if (pollInterval) clearInterval(pollInterval);

  pollInterval = setInterval(async () => {
    try {
      const resp = await fetch(`/api/job/${jobId}`);
      const data = await resp.json();
      if (!data.success) return;

      const job = data.job;
      updateJobUI(job);

      if (job.ha_finalizado) {
        clearInterval(pollInterval);
        btnStartTransfer.disabled = false;
        handleJobCompleted(job);
      }
    } catch (e) {
      console.error("Error polling job:", e);
    }
  }, 1200);
}

function updateJobUI(job) {
  // Update progress bar
  const pct = job.progreso_porcentaje || 0;
  transferProgressBar.style.width = `${pct}%`;
  progressPercent.textContent = `${pct}%`;

  // Update counters
  statProcessed.textContent = `${job.procesadas} / ${job.total_canciones}`;
  statAdded.textContent = job.anadidas;
  statExisting.textContent = job.existentes;
  statNotFound.textContent = job.no_encontradas_count;

  // Status badge
  if (job.estado === "ejecutando") {
    badgeStatus.className = "badge bg-primary rounded-pill px-3 py-1";
    badgeStatus.textContent = "Transfiriendo...";
  } else if (job.estado === "completado") {
    badgeStatus.className = "badge bg-success rounded-pill px-3 py-1";
    badgeStatus.textContent = "Completado";
  } else if (job.estado === "error") {
    badgeStatus.className = "badge bg-danger rounded-pill px-3 py-1";
    badgeStatus.textContent = "Error";
  }

  // Update Logs
  if (job.logs && job.logs.length) {
    logCount.textContent = `${job.logs.length} eventos`;
    liveConsole.innerHTML = job.logs
      .map((entry) => {
        const cls =
          entry.nivel === "success"
            ? "log-entry-success"
            : entry.nivel === "error"
            ? "log-entry-error"
            : entry.nivel === "warning"
            ? "log-entry-warning"
            : "log-entry-info";
        return `<div class="${cls}"><span class="text-secondary">[${escapeHtml(entry.timestamp)}]</span> ${escapeHtml(entry.texto)}</div>`;
      })
      .join("");
    liveConsole.scrollTop = liveConsole.scrollHeight;
  }
}

function handleJobCompleted(job) {
  finishedActions.classList.remove("d-none");

  const summary = `Se añadieron ${job.anadidas} canciones nuevas, ${job.existentes} ya estaban en tu lista y ${job.no_encontradas_count} no se encontraron en YouTube Music.`;
  finishedSummaryText.textContent = summary;

  // Configure download links
  btnDlNotFound.href = `/api/download-report/${job.id}/no_encontradas`;
  btnDlSpotify.href = `/api/download-report/${job.id}/solo_en_spotify`;

  if (job.no_encontradas_count === 0) {
    btnDlNotFound.classList.add("d-none");
  } else {
    btnDlNotFound.classList.remove("d-none");
  }

  showToast("¡Proceso de transferencia finalizado!", "success");
}

// ── Auth Handling ────────────────────────────────────────────────────────────
btnUploadAuthFile.addEventListener("click", async () => {
  if (!inputAuthFile.files.length) {
    showToast("Selecciona un archivo JSON.", "warning");
    return;
  }

  const formData = new FormData();
  formData.append("file", inputAuthFile.files[0]);

  spinnerAuthUpload.classList.remove("d-none");
  btnUploadAuthFile.disabled = true;

  try {
    const resp = await fetch("/api/upload-auth", {
      method: "POST",
      body: formData,
    });
    const data = await resp.json();
    handleAuthResponse(data);
  } catch (err) {
    showToast("Error al subir archivo de autenticación.", "danger");
  } finally {
    spinnerAuthUpload.classList.add("d-none");
    btnUploadAuthFile.disabled = false;
  }
});

btnSaveAuthText.addEventListener("click", async () => {
  const jsonContent = textareaAuthJson.value.trim();
  if (!jsonContent) {
    showToast("El campo de texto está vacío.", "warning");
    return;
  }

  spinnerAuthText.classList.remove("d-none");
  btnSaveAuthText.disabled = true;

  try {
    const resp = await fetch("/api/upload-auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ json_content: jsonContent }),
    });
    const data = await resp.json().catch(() => null);
    if (data) {
      handleAuthResponse(data);
    } else {
      showToast("Error en la respuesta del servidor.", "danger");
    }
  } catch (err) {
    showToast("Error de conexión al enviar las cabeceras.", "danger");
  } finally {
    spinnerAuthText.classList.add("d-none");
    btnSaveAuthText.disabled = false;
  }
});

function handleAuthResponse(data) {
  if (data.success) {
    showToast("¡Autenticación con YouTube Music confirmada!", "success");
    modalAuthAlert.className = "alert alert-success border-0 bg-opacity-10 d-flex align-items-center gap-3 rounded-3 mb-4";
    modalAuthAlert.querySelector("i").className = "fa-solid fa-circle-check text-success fs-4";
    modalAuthStatusTitle.textContent = "Autenticado con éxito";
    modalAuthStatusMsg.textContent = data.message;

    authStatusText.textContent = "YouTube Music Conectado";
    btnAuthStatus.className = "btn btn-sm rounded-pill px-3 py-1 d-flex align-items-center gap-2 btn-outline-success";
    authWarningAlert.classList.add("d-none");
  } else {
    showToast(data.error || data.message || "Error de autenticación.", "danger");
    modalAuthAlert.className = "alert alert-warning border-0 bg-opacity-10 d-flex align-items-center gap-3 rounded-3 mb-4";
    modalAuthAlert.querySelector("i").className = "fa-solid fa-triangle-exclamation text-warning fs-4";
    modalAuthStatusTitle.textContent = "Error al autenticar";
    modalAuthStatusMsg.textContent = data.error || data.message;
  }
}

// ── Google OAuth Flow ────────────────────────────────────────────────────────
const btnStartOauth = document.getElementById("btn-start-oauth");
const spinnerOauthStart = document.getElementById("spinner-oauth-start");
const inputOauthClientId = document.getElementById("input-oauth-client-id");
const inputOauthClientSecret = document.getElementById("input-oauth-client-secret");
const oauthStepInput = document.getElementById("oauth-step-input");
const oauthStepWaiting = document.getElementById("oauth-step-waiting");
const oauthDisplayCode = document.getElementById("oauth-display-code");
const oauthBtnOpenGoogle = document.getElementById("oauth-btn-open-google");
const btnCancelOauth = document.getElementById("btn-cancel-oauth");

let oauthPollInterval = null;

if (btnStartOauth) {
  btnStartOauth.addEventListener("click", async () => {
    const clientId = inputOauthClientId.value.trim();
    const clientSecret = inputOauthClientSecret.value.trim();

    if (!clientId || !clientSecret) {
      showToast("Por favor, introduce tu Google Client ID y Client Secret.", "warning");
      return;
    }

    spinnerOauthStart.classList.remove("d-none");
    btnStartOauth.disabled = true;

    try {
      const resp = await fetch("/api/oauth/init", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
      });
      const data = await resp.json();

      if (!data.success) {
        showToast(data.error || "No se pudo iniciar el flujo OAuth.", "danger");
        return;
      }

      oauthDisplayCode.textContent = data.user_code;
      oauthBtnOpenGoogle.href = data.direct_url;
      oauthStepInput.classList.add("d-none");
      oauthStepWaiting.classList.remove("d-none");

      // Auto-abrir en nueva pestaña para comodidad del usuario
      window.open(data.direct_url, "_blank");

      startPollingOauthToken(data.session_id, data.interval || 5);
    } catch (e) {
      showToast("Error de conexión al iniciar OAuth.", "danger");
    } finally {
      spinnerOauthStart.classList.add("d-none");
      btnStartOauth.disabled = false;
    }
  });
}

function startPollingOauthToken(sessionId, intervalSec) {
  if (oauthPollInterval) clearInterval(oauthPollInterval);

  oauthPollInterval = setInterval(async () => {
    try {
      const resp = await fetch(`/api/oauth/check/${sessionId}`);
      const data = await resp.json();

      if (data.status === "success") {
        clearInterval(oauthPollInterval);
        oauthStepWaiting.classList.add("d-none");
        oauthStepInput.classList.remove("d-none");
        handleAuthResponse(data);
        showToast("¡Google OAuth vinculado con éxito!", "success");
      } else if (data.status === "error") {
        clearInterval(oauthPollInterval);
        oauthStepWaiting.classList.add("d-none");
        oauthStepInput.classList.remove("d-none");
        showToast(data.error || "Error durante la autorización de Google.", "danger");
      }
    } catch (e) {
      console.error("Error comprobando token OAuth:", e);
    }
  }, Math.max(3000, intervalSec * 1000));
}

if (btnCancelOauth) {
  btnCancelOauth.addEventListener("click", () => {
    if (oauthPollInterval) clearInterval(oauthPollInterval);
    oauthStepWaiting.classList.add("d-none");
    oauthStepInput.classList.remove("d-none");
    showToast("Flujo OAuth cancelado.", "info");
  });
}
