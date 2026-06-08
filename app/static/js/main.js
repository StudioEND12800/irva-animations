// ── Radio/Checkbox visual selection ──────────────────────────────────
document.addEventListener('change', e => {
  const inp = e.target;
  if (inp.type === 'radio') {
    const group = inp.closest('.radio-group');
    if (group) group.querySelectorAll('.radio-option').forEach(o => {
      o.classList.toggle('selected', o.querySelector('input') === inp);
    });
  }
  if (inp.type === 'checkbox') {
    const opt = inp.closest('.checkbox-option');
    if (opt) opt.classList.toggle('selected', inp.checked);
  }
});

// Init at page load
document.querySelectorAll('input[type=radio]:checked').forEach(inp => {
  inp.closest('.radio-option')?.classList.add('selected');
});
document.querySelectorAll('input[type=checkbox]:checked').forEach(inp => {
  inp.closest('.checkbox-option')?.classList.add('selected');
});

// ── Textarea word count ───────────────────────────────────────────────
document.querySelectorAll('textarea[data-limit]').forEach(ta => {
  const counter = ta.nextElementSibling;
  const limit = parseInt(ta.dataset.limit);
  const update = () => {
    const words = ta.value.trim().split(/\s+/).filter(w => w).length;
    counter.textContent = `${words} / ${limit} mots`;
    counter.style.color = words > limit ? '#ed6d64' : '';
  };
  ta.addEventListener('input', update);
  update();
});

// ── Signature pad ─────────────────────────────────────────────────────
function initSignaturePad(canvasId, inputId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const input = document.getElementById(inputId);
  let drawing = false;

  // Resize to actual px
  function resize() {
    const rect = canvas.getBoundingClientRect();
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    canvas.width = rect.width;
    canvas.height = rect.height || 160;
    ctx.putImageData(imageData, 0, 0);
    ctx.strokeStyle = '#1a1a1a';
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  }
  resize();
  window.addEventListener('resize', resize);

  function getPos(e) {
    const rect = canvas.getBoundingClientRect();
    if (e.touches) {
      return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top };
    }
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  canvas.addEventListener('mousedown', e => { drawing = true; ctx.beginPath(); const p = getPos(e); ctx.moveTo(p.x, p.y); });
  canvas.addEventListener('touchstart', e => { e.preventDefault(); drawing = true; ctx.beginPath(); const p = getPos(e); ctx.moveTo(p.x, p.y); }, { passive: false });
  canvas.addEventListener('mousemove', e => { if (!drawing) return; const p = getPos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); });
  canvas.addEventListener('touchmove', e => { e.preventDefault(); if (!drawing) return; const p = getPos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); }, { passive: false });
  canvas.addEventListener('mouseup', () => { drawing = false; save(); });
  canvas.addEventListener('touchend', () => { drawing = false; save(); });

  function save() {
    if (input) input.value = canvas.toDataURL('image/png');
  }

  // Clear button
  const btn = canvas.closest('.signature-pad-wrapper')?.querySelector('.sig-clear');
  if (btn) btn.addEventListener('click', () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (input) input.value = '';
  });
}

initSignaturePad('sig-eleveur', 'signature_eleveur_data');

// ── Photo upload (drag & drop + preview) ─────────────────────────────
function initUploadZone(zoneId, inputId, gridId) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const grid = document.getElementById(gridId);
  if (!zone || !input) return;

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    handleFiles(e.dataTransfer.files);
  });
  input.addEventListener('change', () => handleFiles(input.files));

  async function handleFiles(files) {
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const resp = await fetch('/upload-photo', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.id && grid) addThumb(data);
      } catch(e) {
        console.error('Upload error', e);
      }
    }
  }

  function addThumb(data) {
    const div = document.createElement('div');
    div.className = 'photo-thumb';
    div.innerHTML = `
      <img src="${data.url}" alt="${data.name}">
      <button type="button" class="remove-photo" data-id="${data.id}">×</button>
    `;
    div.querySelector('.remove-photo').addEventListener('click', async () => {
      div.remove();
    });
    grid.appendChild(div);
  }
}

initUploadZone('upload-zone-photos', 'photos-input', 'photo-grid');
initUploadZone('upload-zone-signature', 'sig-boucher-input', null);

// ── Inject current year in footer ─────────────────────────────────────
// (handled server-side via context processor)

// ── Conditional visibility ────────────────────────────────────────────
function bindConditional(triggerName, triggerValue, targetId, invert = false) {
  const inputs = document.querySelectorAll(`[name="${triggerName}"]`);
  const target = document.getElementById(targetId);
  if (!target) return;
  const update = () => {
    const vals = [...document.querySelectorAll(`[name="${triggerName}"]:checked`)].map(i => i.value);
    const match = vals.includes(triggerValue);
    target.classList.toggle('hidden', invert ? match : !match);
  };
  inputs.forEach(i => i.addEventListener('change', update));
  update();
}

bindConditional('animation_solo', 'Avec un autre éleveur·se', 'field-coeleveuse');
bindConditional('rayons_presents', 'Rayon libre-service (LS)', 'section-ls');
bindConditional('rayons_presents', 'Rayon Coupe (Trad)', 'section-trad');
bindConditional('ls_autre_veau', 'OUI', 'field-ls-autre-veau-detail');
bindConditional('trad_autre_veau', 'OUI', 'field-trad-autre-veau-detail');
bindConditional('incident', 'OUI', 'field-incident-detail');
bindConditional('ressenti_accroche', 'Facile', 'field-formation', true);
