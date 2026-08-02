document.addEventListener('DOMContentLoaded', function() {
    var importModal = document.getElementById('importContratModal');
    if (!importModal) { return; }

    var contratIdInput = document.getElementById('contrat_id');
    var contratPanel = document.getElementById('contrat-selected-panel');
    var contratEmpty = document.getElementById('contrat-empty');
    var contratMessage = document.getElementById('contrat-message');

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function fmtCurrency(value) {
        if (value === null || value === undefined || value === '') { return '--'; }
        var n = Number(value);
        if (isNaN(n)) { return '--'; }
        return n.toLocaleString('fr-FR', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' €';
    }

    function fmtDate(value) { return value || '--'; }

    function setText(id, value) {
        var el = document.getElementById(id);
        if (el) { el.textContent = value || '--'; }
    }

    function showMessage(msg, isSuccess) {
        if (!contratMessage) { return; }
        contratMessage.classList.remove('d-none', 'alert-success', 'alert-danger');
        contratMessage.classList.add(isSuccess ? 'alert-success' : 'alert-danger');
        contratMessage.innerHTML = '<i class="fa-solid ' + (isSuccess ? 'fa-circle-check' : 'fa-circle-exclamation') + ' me-2"></i>' + esc(msg);
    }

    function hideMessage() {
        if (contratMessage) { contratMessage.classList.add('d-none'); }
    }

    function selectContrat(c) {
        if (!c || !c.id) { return; }
        contratIdInput.value = c.id;
        setText('contrat-info-numero', c.numero);
        setText('contrat-info-signature', fmtDate(c.date_signature));
        setText('contrat-info-debut', fmtDate(c.date_debut));
        setText('contrat-info-fin', fmtDate(c.date_fin));
        setText('contrat-info-loyer', fmtCurrency(c.montant_loyer));
        setText('contrat-info-depot', fmtCurrency(c.depot_garantie));
        setText('contrat-info-statut', c.statut || '--');
        setText('contrat-info-locataire', c.locataire || '--');
        setText('contrat-info-proprietaire', c.proprietaire || '--');
        setText('contrat-info-mode', c.mode_paiement || '--');
        setText('contrat-info-frequence', c.frequence || '--');
        if (contratEmpty) { contratEmpty.classList.add('d-none'); }
        if (contratPanel) { contratPanel.classList.remove('d-none'); }
        hideMessage();
        var modalEl = bootstrap.Modal.getOrCreateInstance(importModal);
        modalEl.hide();
    }

    function clearContrat() {
        contratIdInput.value = '';
        if (contratPanel) { contratPanel.classList.add('d-none'); }
        if (contratEmpty) { contratEmpty.classList.remove('d-none'); }
    }

    // Contrat pré-sélectionné (mode modification)
    var initialEl = document.getElementById('occupation-contrat-initial');
    if (initialEl) {
        try {
            var raw = JSON.parse(initialEl.textContent);
            if (raw && raw.id) { selectContrat(raw); }
        } catch (e) { /* ignore */ }
    }

    var btnRemove = document.getElementById('contrat-remove');
    if (btnRemove) {
        btnRemove.addEventListener('click', function(e) {
            e.preventDefault();
            clearContrat();
        });
    }

    // --- Onglet 1 : recherche d'un contrat existant ---
    var searchForm = document.getElementById('contrat-search-form');
    var searchInput = document.getElementById('contrat-search-input');
    var resultsBox = document.getElementById('contrat-search-results');
    var noResult = document.getElementById('contrat-search-none');
    var loadingBox = document.getElementById('contrat-search-loading');

    function doSearch(q) {
        if (!q) {
            resultsBox.innerHTML = '';
            if (noResult) { noResult.classList.add('d-none'); }
            return;
        }
        if (loadingBox) { loadingBox.classList.remove('d-none'); }
        var url = '/occupations/contrats/recherche?q=' + encodeURIComponent(q);
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (loadingBox) { loadingBox.classList.add('d-none'); }
                if (!data.ok) { showMessage(data.error || 'Erreur lors de la recherche.', false); return; }
                resultsBox.innerHTML = '';
                var items = data.contrats || [];
                if (noResult) { noResult.classList.toggle('d-none', items.length > 0); }
                items.forEach(function(c) {
                    var row = document.createElement('div');
                    row.className = 'd-flex flex-wrap justify-content-between align-items-center border rounded-3 p-3 mb-2 bg-white';
                    var info = document.createElement('div');
                    info.innerHTML =
                        '<strong class="font-monospace">' + esc(c.numero) + '</strong>' +
                        '<div class="small text-muted">Signé : ' + esc(fmtDate(c.date_signature)) +
                        ' &middot; ' + esc(fmtDate(c.date_debut)) + ' &rarr; ' + esc(fmtDate(c.date_fin)) + '</div>' +
                        '<div class="small text-muted">Loyer : <span class="text-dark fw-semibold">' + fmtCurrency(c.montant_loyer) +
                        '</span> &middot; Statut : ' + esc(c.statut || '--') + '</div>' +
                        '<div class="small text-muted">Locataire : ' + esc(c.locataire || '--') +
                        ' &middot; Propriétaire : ' + esc(c.proprietaire || '--') + '</div>';
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'btn btn-accent btn-sm rounded-3';
                    btn.innerHTML = '<i class="fa-solid fa-link me-1"></i>Sélectionner';
                    btn.addEventListener('click', function() { selectContrat(c); });
                    row.appendChild(info);
                    row.appendChild(btn);
                    resultsBox.appendChild(row);
                });
            })
            .catch(function() {
                if (loadingBox) { loadingBox.classList.add('d-none'); }
                showMessage('Erreur lors de la recherche de contrats.', false);
            });
    }

    if (searchForm) {
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            doSearch(searchInput ? searchInput.value.trim() : '');
        });
    }

    // --- Onglet 2 : import d'un contrat PDF ---
    var pdfForm = document.getElementById('contrat-pdf-form');
    if (pdfForm) {
        pdfForm.addEventListener('submit', function(e) {
            e.preventDefault();
            var btn = pdfForm.querySelector('button[type="submit"]');
            if (btn) { btn.disabled = true; }
            var fd = new FormData(pdfForm);
            fetch('/occupations/contrats/importer-pdf', { method: 'POST', body: fd })
                .then(function(r) {
                    return r.json().then(function(d) { return { status: r.status, body: d }; });
                })
                .then(function(res) {
                    if (btn) { btn.disabled = false; }
                    var d = res.body;
                    if (!d.ok) {
                        showMessage(d.error || 'Erreur lors de l\'import du contrat.', false);
                        return;
                    }
                    selectContrat(d.contrat);
                    pdfForm.reset();
                    showMessage('Contrat importé et lié à l\'occupation : ' + d.contrat.numero, true);
                })
                .catch(function() {
                    if (btn) { btn.disabled = false; }
                    showMessage('Erreur lors de l\'import du contrat.', false);
                });
        });
    }

    // --- Empêcher la création sans contrat valide ---
    var mainForm = document.getElementById('occupation-form');
    if (mainForm) {
        mainForm.addEventListener('submit', function(e) {
            if (!contratIdInput.value) {
                e.preventDefault();
                showMessage('Un contrat valide doit être importé avant d\'enregistrer l\'occupation.', false);
                if (contratEmpty) { contratEmpty.classList.add('border-danger'); }
                if (importModal) {
                    var tab = document.getElementById('contrat-search-tab');
                    if (tab && bootstrap.Tab) {
                        bootstrap.Tab.getOrCreateInstance(tab).show();
                    }
                    bootstrap.Modal.getOrCreateInstance(importModal).show();
                }
            }
        });
    }
});
