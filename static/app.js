const months = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December'
];

const facilitySelect = document.getElementById('facilitySelect');
const monthSelect = document.getElementById('monthSelect');
const yearSelect = document.getElementById('yearSelect');
const runBtn = document.getElementById('runReport');
const progressBar = document.getElementById('progressBar');
const progressPercent = document.getElementById('progressPercent');
const progressMessage = document.getElementById('progressMessage');
const facilityCount = document.getElementById('facilityCount');
const facilityRows = document.getElementById('facilityRows');
const facilityModal = document.getElementById('facilityModal');
const facilitySearch = document.getElementById('facilitySearch');
const downloadCard = document.getElementById('downloadCard');
const downloadActions = document.getElementById('downloadActions');
const toast = document.getElementById('toast');

let facilities = [];
let currentJobId = null;
let reportKey = sessionStorage.getItem('nexionReportKey') || '';

function initPeriod() {
  const now = new Date();
  months.forEach((m, i) => {
    const opt = document.createElement('option');
    opt.value = i + 1;
    opt.textContent = m;
    monthSelect.appendChild(opt);
  });
  for (let y = now.getFullYear(); y >= now.getFullYear() - 5; y--) {
    const opt = document.createElement('option');
    opt.value = y;
    opt.textContent = y;
    yearSelect.appendChild(opt);
  }
  monthSelect.value = now.getMonth() + 1;
  yearSelect.value = now.getFullYear();
}

async function loadFacilities() {
  const res = await fetch('/api/facilities');
  const data = await res.json();

  facilities = data.facilities || [];

  facilityCount.textContent = data.count ?? facilities.length;

  renderFacilities(facilities);

  facilitySelect.innerHTML = '';

  const allOption = document.createElement('option');
  allOption.value = '';
  allOption.textContent = `All ${facilities.length} active facilities`;
  facilitySelect.appendChild(allOption);

  const sorted = [...facilities].sort((a, b) => {
    const stateCompare = a.state.localeCompare(b.state);
    if (stateCompare !== 0) return stateCompare;

    return a.facility.localeCompare(b.facility);
  });

  sorted.forEach(facility => {
    const option = document.createElement('option');

    option.value = facility.id;
    option.textContent = `${facility.state} — ${facility.facility}`;

    facilitySelect.appendChild(option);
  });
}

function renderFacilities(list) {
  facilityRows.innerHTML = '';
  list.forEach(f => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${escapeHtml(f.state)}</td><td>${escapeHtml(f.facility)}</td>`;
    facilityRows.appendChild(tr);
  });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
    .replaceAll('"','&quot;').replaceAll("'",'&#039;');
}

function openModal() {
  facilityModal.classList.remove('hidden');
  facilityModal.setAttribute('aria-hidden', 'false');
  setTimeout(() => facilitySearch.focus(), 50);
}
function closeModal() {
  facilityModal.classList.add('hidden');
  facilityModal.setAttribute('aria-hidden', 'true');
}

document.getElementById('openFacilities').addEventListener('click', openModal);
document.getElementById('openFacilitiesNav').addEventListener('click', openModal);
document.querySelectorAll('[data-close-modal]').forEach(el => el.addEventListener('click', closeModal));
facilitySearch.addEventListener('input', e => {
  const q = e.target.value.trim().toLowerCase();
  renderFacilities(facilities.filter(f => `${f.state} ${f.facility}`.toLowerCase().includes(q)));
});

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (reportKey) h['X-Report-Key'] = reportKey;
  return h;
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  if (res.status === 401) {
    const entered = window.prompt('Enter the reporting password:');
    if (entered === null) throw new Error('Password required.');
    reportKey = entered;
    sessionStorage.setItem('nexionReportKey', reportKey);
    return apiFetch(url, options);
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return res;
}

runBtn.addEventListener('click', async () => {
  const sources = [];
  if (document.getElementById('facebookCheck').checked) sources.push('facebook');
  if (document.getElementById('googleCheck').checked) sources.push('google');
  if (!sources.length) return showToast('Choose Facebook, Google, or both.');

  runBtn.disabled = true;
  downloadCard.classList.add('hidden');
  resetStages(sources);
  setProgress(2, 'Loading saved facility list…');

  try {
    const res = await apiFetch('/api/reports', {
      method: 'POST',
      body: JSON.stringify({
        month: Number(monthSelect.value),
        year: Number(yearSelect.value),
        sources,
        facility_id: facilitySelect.value
          ? Number(facilitySelect.value)
          : null
})
    });
    const data = await res.json();
    currentJobId = data.job_id;
    pollJob(currentJobId, sources);
  } catch (err) {
    runBtn.disabled = false;
    setProgress(0, err.message);
    showToast(err.message);
  }
});

async function pollJob(jobId, sources) {
  try {
    const res = await apiFetch(`/api/reports/${jobId}`);
    const job = await res.json();
    updateFromJob(job, sources);

    if (job.status === 'complete') {
      runBtn.disabled = false;
      showDownloads(job, sources);
      return;
    }
    if (job.status === 'error') {
      runBtn.disabled = false;
      showToast(job.message || 'Report failed.');
      return;
    }
    setTimeout(() => pollJob(jobId, sources), 900);
  } catch (err) {
    runBtn.disabled = false;
    showToast(err.message);
  }
}

function setProgress(value, message) {
  const pct = Math.max(0, Math.min(100, Number(value || 0)));
  progressBar.style.width = `${pct}%`;
  progressPercent.textContent = `${pct}%`;
  progressMessage.textContent = message || '';
}

function resetStages(sources) {
  ['stagePreparing','stageFacebook','stageGoogle','stageFiles'].forEach(id => {
    document.getElementById(id).classList.remove('active','done');
  });
  document.getElementById('stagePreparing').classList.add('active');
  if (!sources.includes('facebook')) document.getElementById('stageFacebook').querySelector('small').textContent = 'Not selected';
  else document.getElementById('stageFacebook').querySelector('small').textContent = 'Waiting';
  if (!sources.includes('google')) document.getElementById('stageGoogle').querySelector('small').textContent = 'Not selected';
  else document.getElementById('stageGoogle').querySelector('small').textContent = 'Waiting';
  document.getElementById('stageFiles').querySelector('small').textContent = 'Waiting';
}

function updateFromJob(job, sources) {
  setProgress(job.progress, job.message);
  const stage = (job.stage || '').toLowerCase();

  document.getElementById('stagePreparing').classList.toggle('done', job.progress > 3);
  document.getElementById('stagePreparing').classList.toggle('active', job.progress <= 3);

  if (stage.includes('facebook')) {
    markStage('stageFacebook', 'active', `${job.current}/${job.total}`);
  } else if (sources.includes('facebook') && (stage.includes('google') || stage.includes('generating') || job.status === 'complete')) {
    markStage('stageFacebook', 'done', 'Complete');
  }

  if (stage.includes('google')) {
    markStage('stageGoogle', 'active', `${job.current}/${job.total}`);
  } else if (sources.includes('google') && (stage.includes('generating') || job.status === 'complete')) {
    markStage('stageGoogle', 'done', 'Complete');
  }

  if (stage.includes('generating')) markStage('stageFiles', 'active', 'Building .xlsx');
  if (job.status === 'complete') markStage('stageFiles', 'done', 'Complete');
}

function markStage(id, state, label) {
  const el = document.getElementById(id);
  el.classList.remove('active','done');
  el.classList.add(state);
  el.querySelector('small').textContent = label;
}

function showDownloads(job, sources) {
  downloadActions.innerHTML = '';
  sources.forEach((source, idx) => {
    if (!job.files || !job.files[source]) return;
    const btn = document.createElement('button');
    btn.className = `download-btn ${idx ? 'secondary' : ''}`;
    btn.textContent = `Download ${source === 'facebook' ? 'Facebook' : 'Google'} Excel`;
    btn.addEventListener('click', () => downloadFile(job.id, source));
    downloadActions.appendChild(btn);
  });
  downloadCard.classList.remove('hidden');
  downloadCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function downloadFile(jobId, source) {
  try {
    const res = await apiFetch(`/api/reports/${jobId}/download/${source}`, { method: 'GET' });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nexion_${source}_report.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    showToast(err.message);
  }
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove('hidden');
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => toast.classList.add('hidden'), 3800);
}

initPeriod();
loadFacilities().catch(err => showToast(`Could not load facilities: ${err.message}`));
