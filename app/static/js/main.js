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

// ── Copy buttons ───────────────────────────────────────────────────────
document.querySelectorAll('[data-copy]').forEach(button => {
  if (button.dataset.copyInit === '1') return;
  button.dataset.copyInit = '1';
  const defaultLabel = button.textContent;
  button.addEventListener('click', async () => {
    const value = button.getAttribute('data-copy');
    try {
      await navigator.clipboard.writeText(value);
      button.textContent = 'Copié';
      setTimeout(() => {
        button.textContent = defaultLabel;
      }, 1800);
    } catch (error) {
      button.textContent = 'À copier';
    }
  });
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

// ── Internal store reference lookup ─────────────────────────────────
function initStoreReferenceLookup() {
  document.querySelectorAll('[data-store-ref-widget]').forEach(widget => {
    if (widget.dataset.lookupInit === '1') return;
    widget.dataset.lookupInit = '1';

    const form = widget.closest('form');
    const searchUrl = widget.dataset.searchUrl;
    const searchInput = widget.querySelector('[data-store-ref-search]');
    const results = widget.querySelector('[data-store-ref-results]');
    const selected = widget.querySelector('[data-store-ref-selected]');
    const aliasTextarea = form?.querySelector('[name="store_reference_aliases"]');
    const referenceIdInput = form?.querySelector('[name="store_reference_id"]');
    const nameInput = form?.querySelector('[name="nom_magasin"]');
    const enseigneInput = form?.querySelector('[name="enseigne"]');
    const postalInput = form?.querySelector('[name="code_postal"]');
    const communeInput = form?.querySelector('[name="commune"]');
    const departmentInput = form?.querySelector('[name="code_departement"]');
    const regionInput = form?.querySelector('[name="region"]');

    if (!form || !searchUrl || !searchInput || !results) return;

    let debounceTimer = null;
    let abortController = null;
    let applyingReference = false;

    function escapeHtml(value) {
      return String(value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;');
    }

    function renderSelected(reference) {
      if (!selected) return;
      if (!reference) {
        selected.hidden = true;
        selected.innerHTML = '';
        return;
      }
      const location = [reference.code_postal, reference.commune].filter(Boolean).join(' ');
      const meta = [reference.enseigne, location, reference.region].filter(Boolean).join(' · ');
      selected.hidden = false;
      selected.innerHTML = `
        <strong>${escapeHtml(reference.nom_magasin || '')}</strong>
        <span>${escapeHtml(meta || 'Référence prête à appliquer')}</span>
      `;
    }

    function clearSelectedReference() {
      if (applyingReference) return;
      if (referenceIdInput) referenceIdInput.value = '';
      renderSelected(null);
    }

    function applyReference(reference) {
      applyingReference = true;
      if (referenceIdInput) referenceIdInput.value = reference.id || '';
      if (searchInput) searchInput.value = reference.nom_magasin || '';
      if (nameInput) nameInput.value = reference.nom_magasin || '';
      if (enseigneInput && reference.enseigne) enseigneInput.value = reference.enseigne;
      if (postalInput && reference.code_postal) postalInput.value = reference.code_postal;
      if (communeInput && reference.commune) communeInput.value = reference.commune;
      if (departmentInput && reference.code_departement) departmentInput.value = reference.code_departement;
      if (regionInput && reference.region) regionInput.value = reference.region;
      if (aliasTextarea && !aliasTextarea.value.trim()) {
        aliasTextarea.value = [reference.nom_magasin, ...(reference.aliases || [])]
          .filter(Boolean)
          .join('\n');
      }
      renderSelected(reference);
      results.innerHTML = '';
      applyingReference = false;
    }

    function renderResults(items) {
      if (!items.length) {
        results.innerHTML = '<div class="store-ref-empty">Aucune proposition pour cette saisie.</div>';
        return;
      }

      results.innerHTML = items.map(item => {
        const location = [item.code_postal, item.commune].filter(Boolean).join(' ');
        const meta = [item.enseigne, location, item.region].filter(Boolean).join(' · ');
        const aliasText = (item.aliases || []).slice(0, 3).join(', ');
        return `
          <button type="button" class="store-ref-result" data-reference="${encodeURIComponent(JSON.stringify(item))}">
            <span class="store-ref-result-title">${escapeHtml(item.nom_magasin || '')}</span>
            <span class="store-ref-result-meta">${escapeHtml(meta || 'Référence sans localisation')}</span>
            ${aliasText ? `<span class="store-ref-result-alias">Alias : ${escapeHtml(aliasText)}</span>` : ''}
          </button>
        `;
      }).join('');

      results.querySelectorAll('.store-ref-result').forEach(button => {
        button.addEventListener('click', () => {
          const reference = JSON.parse(decodeURIComponent(button.dataset.reference || '%7B%7D'));
          applyReference(reference);
        });
      });
    }

    async function fetchReferences() {
      const query = searchInput.value.trim();
      const enseigne = enseigneInput?.value?.trim() || '';
      const codePostal = postalInput?.value?.trim() || '';
      const commune = communeInput?.value?.trim() || '';

      if (!query && !codePostal && !commune) {
        results.innerHTML = '';
        return;
      }

      if (query && query.length < 2 && !codePostal && !commune) {
        results.innerHTML = '<div class="store-ref-empty">Tapez au moins 2 caractères pour lancer la recherche.</div>';
        return;
      }

      abortController?.abort();
      abortController = new AbortController();

      const url = new URL(searchUrl, window.location.origin);
      url.searchParams.set('q', query);
      url.searchParams.set('enseigne', enseigne);
      url.searchParams.set('code_postal', codePostal);
      url.searchParams.set('commune', commune);

      results.innerHTML = '<div class="store-ref-empty">Recherche en cours…</div>';

      try {
        const response = await fetch(url, { signal: abortController.signal });
        const data = await response.json();
        renderResults(data.results || []);
      } catch (error) {
        if (error.name === 'AbortError') return;
        console.error('Store reference lookup error', error);
        results.innerHTML = '<div class="store-ref-empty">La recherche n’a pas abouti. Vous pouvez saisir le magasin manuellement.</div>';
      }
    }

    function scheduleFetch() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(fetchReferences, 180);
    }

    searchInput.addEventListener('input', scheduleFetch);
    [enseigneInput, postalInput, communeInput].forEach(input => {
      input?.addEventListener('input', scheduleFetch);
      input?.addEventListener('change', scheduleFetch);
    });
    [nameInput, enseigneInput, postalInput, communeInput, departmentInput, regionInput].forEach(input => {
      input?.addEventListener('input', clearSelectedReference);
      input?.addEventListener('change', clearSelectedReference);
    });

    if (searchInput.value.trim()) {
      renderSelected(referenceIdInput?.value ? {
        id: referenceIdInput.value,
        nom_magasin: nameInput?.value || searchInput.value,
        enseigne: enseigneInput?.value || '',
        code_postal: postalInput?.value || '',
        commune: communeInput?.value || '',
        region: regionInput?.value || '',
      } : null);
      scheduleFetch();
    }
  });
}

initStoreReferenceLookup();

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
