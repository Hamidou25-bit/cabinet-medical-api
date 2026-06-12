let patientsData = [];
let stockData = [];

// 1. Initialisation sécurisée (on vérifie si l'élément existe)
document.addEventListener('DOMContentLoaded', function() {
    // Date
    const dateEl = document.getElementById('current-date');
    if (dateEl) {
        dateEl.textContent = new Date().toLocaleDateString('fr-FR', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });
    }

    // Nom utilisateur
    const userName = localStorage.getItem('nom_utilisateur');
    const userEl = document.getElementById('user-name');
    if (userName && userEl) {
        userEl.textContent = '👤 ' + userName;
    }
    
    // Chargement initial
    loadDashboard();
});

// Navigation
function showPage(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
    document.getElementById('page-' + page).classList.add('active');
    event.currentTarget.classList.add('active');

    const titles = { dashboard: 'Tableau de bord', patients: 'Patients', consultations: 'Consultations', stock: 'Stock' };
    document.getElementById('page-title').textContent = titles[page];

    if (page === 'patients') loadPatients();
    if (page === 'consultations') loadConsultations();
    if (page === 'stock') loadStock();
}

// Modal
function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// Dashboard
async function loadDashboard() {
    try {
        const [patients, consultations, stock, alertes] = await Promise.all([
            apiFetch('/patients').then(r => r.json()),
            apiFetch('/consultations').then(r => r.json()),
            apiFetch('/stock').then(r => r.json()),
            apiFetch('/stock/alertes').then(r => r.json())
        ]);

        document.getElementById('stat-patients').textContent = patients.length;
        document.getElementById('stat-consultations').textContent = consultations.length;
        document.getElementById('stat-stock').textContent = stock.length;
        document.getElementById('stat-alertes').textContent = alertes.length;

        const tbody = document.getElementById('recent-consultations');
        tbody.innerHTML = consultations.slice(0, 10).map(c => `
            <tr>
                <td>${c.date_consult || ''}</td>
                <td>${c.nom || ''} ${c.prenom || ''}</td>
                <td>${c.motif || '-'}</td>
                <td>${(c.montant_total || 0).toLocaleString()} FCFA</td>
            </tr>
        `).join('');
    } catch(e) { console.error('Erreur dashboard:', e); }
}

// Patients
async function loadPatients() {
    try {
        patientsData = await apiFetch('/patients').then(r => r.json());
        renderPatients(patientsData);
    } catch(e) { document.getElementById('table-patients').innerHTML = '<tr><td colspan="6">Erreur</td></tr>'; }
}

function renderPatients(data) {
    const tbody = document.getElementById('table-patients');
    if (!data.length) { tbody.innerHTML = '<tr><td colspan="6">Aucun patient</td></tr>'; return; }
    tbody.innerHTML = data.map(p => `<tr><td>${p.nom}</td><td>${p.prenom}</td><td>${p.age}</td><td>${p.sexe}</td><td>${p.telephone || '-'}</td><td>${p.date_enregistrement}</td></tr>`).join('');
}

function filterPatients() {
    const q = document.getElementById('search-patients').value.toLowerCase();
    renderPatients(patientsData.filter(p => (p.nom||'').toLowerCase().includes(q) || (p.prenom||'').toLowerCase().includes(q)));
}

async function savePatient() {
    const patient = {
        nom: document.getElementById('p-nom').value.toUpperCase(),
        prenom: document.getElementById('p-prenom').value,
        age: parseInt(document.getElementById('p-age').value),
        sexe: document.getElementById('p-sexe').value,
        telephone: document.getElementById('p-telephone').value,
        profession: document.getElementById('p-profession').value,
        adresse: document.getElementById('p-adresse').value,
        date_enregistrement: new Date().toISOString().split('T')[0]
    };
    try {
        await apiFetch('/patients', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(patient) });
        closeModal('modal-patient'); loadPatients(); loadDashboard(); alert('Patient enregistré !');
    } catch(e) { alert('Erreur'); }
}

// Consultations
async function loadConsultations() {
    try {
        const data = await apiFetch('/consultations').then(r => r.json());
        document.getElementById('table-consultations').innerHTML = data.map(c => `<tr><td>${c.date_consult||''}</td><td>${c.nom||''} ${c.prenom||''}</td><td>${c.motif||'-'}</td><td>${c.diagnostic||'-'}</td><td>${(c.montant_total||0).toLocaleString()} FCFA</td></tr>`).join('');
    } catch(e) { document.getElementById('table-consultations').innerHTML = '<tr><td colspan="5">Erreur</td></tr>'; }
}

// Stock
async function loadStock() {
    try {
        const [data, alertes] = await Promise.all([apiFetch('/stock').then(r => r.json()), apiFetch('/stock/alertes').then(r => r.json())]);
        stockData = data;
        const alertDiv = document.getElementById('alertes-stock');
        alertDiv.innerHTML = alertes.length > 0 ? `<div class="alert alert-warning">⚠️ ${alertes.length} article(s) en alerte</div>` : '';
        renderStock(data);
    } catch(e) { document.getElementById('table-stock').innerHTML = '<tr><td colspan="6">Erreur</td></tr>'; }
}

function renderStock(data) {
    const tbody = document.getElementById('table-stock');
    if (!data.length) { tbody.innerHTML = '<tr><td colspan="6">Aucun article</td></tr>'; return; }
    tbody.innerHTML = data.map(s => {
        const statut = s.Quantite <= 0 ? '<span class="status status-danger">Rupture</span>' : s.Quantite <= s.SeuilAlerte ? '<span class="status status-warning">Alerte</span>' : '<span class="status status-ok">Normal</span>';
        return `<tr><td>${s.Designation||''}</td><td>${s.Type||''}</td><td>${s.Quantite||0}</td><td>${s.SeuilAlerte||0}</td><td>${(s.PrixVente||0).toLocaleString()} FCFA</td><td>${statut}</td></tr>`;
    }).join('');
}

function filterStock() {
    const q = document.getElementById('search-stock').value.toLowerCase();
    renderStock(stockData.filter(s => (s.Designation||'').toLowerCase().includes(q)));
}
