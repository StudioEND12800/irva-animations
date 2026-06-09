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
  const isDeferredUpload = !grid;
  const status = isDeferredUpload ? document.getElementById('sig-boucher-status') : null;

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (isDeferredUpload) {
      assignFilesToInput(input, e.dataTransfer.files);
      updateDeferredStatus();
      return;
    }
    handleFiles(e.dataTransfer.files);
  });
  input.addEventListener('change', () => {
    if (isDeferredUpload) {
      updateDeferredStatus();
      return;
    }
    handleFiles(input.files);
  });

  function assignFilesToInput(fileInput, files) {
    if (!files?.length) return;
    try {
      const dt = new DataTransfer();
      dt.items.add(files[0]);
      fileInput.files = dt.files;
    } catch (error) {
      console.error('File assignment error', error);
    }
  }

  function updateDeferredStatus() {
    if (!status) return;
    const file = input.files?.[0];
    status.textContent = file
      ? `Fichier sélectionné : ${file.name}`
      : 'Aucun fichier sélectionné pour le moment.';
  }

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
    input.value = '';
  }

  function addThumb(data) {
    const div = document.createElement('div');
    div.className = 'photo-thumb';
    div.innerHTML = `
      <img src="${data.url}" alt="${data.name}">
      <button type="button" class="remove-photo" data-id="${data.id}">×</button>
    `;
    bindPhotoRemoval(div);
    grid.appendChild(div);
  }

  function bindPhotoRemoval(root) {
    const button = root.querySelector('.remove-photo');
    if (!button) return;
    button.addEventListener('click', async () => {
      const photoId = button.dataset.id;
      if (!photoId) return;
      button.disabled = true;
      try {
        const resp = await fetch(`/upload-photo/${photoId}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error(`Delete failed with ${resp.status}`);
        root.remove();
      } catch (error) {
        console.error('Delete error', error);
        button.disabled = false;
      }
    });
  }

  grid?.querySelectorAll('.photo-thumb').forEach(bindPhotoRemoval);
  updateDeferredStatus();
}

initUploadZone('upload-zone-photos', 'photos-input', 'photo-grid');
initUploadZone('upload-zone-signature', 'sig-boucher-input', null);

// ── Progress track auto-shift on mobile ──────────────────────────────
function initProgressSteps() {
  document.querySelectorAll('[data-progress-shell]').forEach(shell => {
    const track = shell.querySelector('.progress-steps');
    const activeStep = track?.querySelector('.step.active');
    if (!track || !activeStep) return;

    const update = () => {
      if (!window.matchMedia('(max-width: 640px)').matches) {
        shell.scrollLeft = 0;
        return;
      }

      const maxScroll = Math.max(track.scrollWidth - shell.clientWidth, 0);
      if (!maxScroll) {
        shell.scrollLeft = 0;
        return;
      }

      const activeCenter = activeStep.offsetLeft + (activeStep.offsetWidth / 2);
      const anchor = 0.38;
      const target = Math.max(0, Math.min(activeCenter - (shell.clientWidth * anchor), maxScroll));
      shell.scrollTo({ left: target, behavior: 'auto' });
    };

    requestAnimationFrame(update);
    window.addEventListener('resize', update, { passive: true });
  });
}

initProgressSteps();

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
