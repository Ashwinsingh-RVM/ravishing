/**
 * Goa DRS Field Update Tool - Frontend Application
 */

// Configuration
const API_BASE = '/api';  // Will be proxied or same origin

// ── Analytics Tracking ──────────────────────────────────────────────────────
const _ANALYTICS_SID = (() => {
    let sid = sessionStorage.getItem('drs_sid');
    if (!sid) {
        sid = Date.now().toString(36) + Math.random().toString(36).slice(2, 9);
        sessionStorage.setItem('drs_sid', sid);
    }
    return sid;
})();

function trackEvent(event_type, page, element = '', value = '') {
    if (!currentUser) return;
    fetch(`${API_BASE}/analytics/track`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_type, page, element, value: String(value), session_id: _ANALYTICS_SID }),
    }).catch(() => {});
}

// Scroll depth tracking — fires at 25/50/75/100% milestones, once per page per session
let _scrollPage = '';
let _tabEnterTime = Date.now();
const _scrollFired = new Set();
window.addEventListener('scroll', () => {
    if (!currentUser || !_scrollPage) return;
    const pct = Math.round((window.scrollY + window.innerHeight) / Math.max(document.body.scrollHeight, 1) * 100);
    const milestone = pct >= 100 ? 100 : pct >= 75 ? 75 : pct >= 50 ? 50 : pct >= 25 ? 25 : 0;
    if (milestone > 0) {
        const key = `${_scrollPage}:${milestone}`;
        if (!_scrollFired.has(key)) {
            _scrollFired.add(key);
            trackEvent('scroll', _scrollPage, '', milestone);
        }
    }
}, { passive: true });
// ────────────────────────────────────────────────────────────────────────────
const SHEET_ID = '1gy0xNL7-ayFfVjf3ETvi8qN3bWytNGbRZg68nShnkEo';

// Stage definitions (15 milestones - follow-ups tracked separately via Meetings)
const STAGES = [
    { value: 'yet_to_meet', label: 'Yet to Meet', number: 1 },
    { value: 'first_meeting_scheduled', label: 'First Meeting Scheduled', number: 2 },
    { value: 'first_meeting_done', label: 'First Meeting Done', number: 3 },
    { value: 'panch_meeting_scheduled', label: 'Panch Meeting Scheduled', number: 4 },
    { value: 'panch_meeting_done', label: 'Panch Meeting Done', number: 5 },
    { value: 'location_finalized', label: 'Location Finalized', number: 6 },
    { value: 'email_sent', label: 'Email Sent', number: 7 },
    { value: 'noc_pending', label: 'NOC Pending', number: 8 },
    { value: 'noc_received', label: 'NOC Received', number: 9 },
    { value: 'service_agreement_sent', label: 'Service Agreement Sent', number: 10 },
    { value: 'service_agreement_signed', label: 'Service Agreement Signed', number: 11 },
    { value: 'infra_pending', label: 'Infra Pending', number: 12 },
    { value: 'infra_complete', label: 'Infra Complete', number: 13 },
    { value: 'device_deployed', label: 'Device Deployed', number: 14 },
    { value: 'device_installed', label: 'Device Installed', number: 15 },
];

// ULB identification — blocks "NORTH" and "SOUTH" are ULBs, everything else is a VP
const ULB_BLOCKS = ['NORTH', 'SOUTH'];
const isULB = (vp) => ULB_BLOCKS.includes(vp.block);

// Legacy stage mapping for display (old values still in data)
const STAGE_MIGRATION = {
    'meeting_scheduled': 'first_meeting_scheduled',
    'follow_up_required': 'first_meeting_done',
};

// Stage-based default duration for calendar events (in minutes)
const STAGE_DURATION_MAP = {
    'yet_to_meet': 5,                    // Quick follow-up call
    'first_meeting_scheduled': 60,       // Full initial meeting
    'meeting_scheduled': 60,             // Legacy: same as first_meeting_scheduled
    'first_meeting_done': 5,             // Follow-up call
    'follow_up_required': 5,             // Legacy: follow-up call
    'panch_meeting_scheduled': 90,       // Panch meeting with ward members
    'punch_meeting_required': 90,        // Typo variant
    'panch_meeting_done': 5,             // Post-panch follow-up
    'location_finalized': 5,             // Quick call
    'email_sent': 5,
    'noc_pending': 5,
    'noc_received': 5,
    'service_agreement_sent': 5,
    'service_agreement_signed': 5,
    'infra_pending': 5,
    'infra_complete': 5,
    'device_deployed': 5,
    'device_installed': 5,
};

// Build a comprehensive stage-to-number lookup (handles enum values, labels, and legacy)
const STAGE_NUMBER_MAP = {};
STAGES.forEach(s => {
    STAGE_NUMBER_MAP[s.value] = s.number;                    // email_sent → 7
    STAGE_NUMBER_MAP[s.label.toLowerCase()] = s.number;      // email sent → 7
    STAGE_NUMBER_MAP[s.label] = s.number;                    // Email Sent → 7
});
// Legacy mappings
STAGE_NUMBER_MAP['meeting_scheduled'] = 2;
STAGE_NUMBER_MAP['follow_up_required'] = 3;
STAGE_NUMBER_MAP['punch_meeting_required'] = 4;

/**
 * Resolve a VP's effective stage number from currentStage text.
 * Falls back to stageNumber from sheet if unrecognized.
 */
function resolveStageNumber(vp) {
    const stage = vp.currentStage || '';
    const resolved = STAGE_NUMBER_MAP[stage] || STAGE_NUMBER_MAP[stage.toLowerCase()];
    if (resolved) return resolved;
    // Fallback to sheet's stageNumber
    return vp.stageNumber || 1;
}

// BDO Stage definitions (4 milestones - follow-ups tracked separately)
const BDO_STAGES = [
    { value: 'yet_to_meet', label: 'Yet to Meet', number: 1 },
    { value: 'meeting_scheduled', label: 'Meeting Scheduled', number: 2 },
    { value: 'meeting_done', label: 'Meeting Done', number: 3 },
    { value: 'communication_sent', label: 'Communication Sent to VPs', number: 4 },
];

// URL route ↔ tab mapping
const ROUTE_TO_TAB = {
    'VPs': 'vps', 'ULBs': 'ulbs', 'Dashboard': 'dashboard',
    'Meetings': 'meetings', 'Escalation': 'escalation',
    'Today': 'today', 'HoReCa': 'horeca', 'Learning': 'learning',
};
const TAB_TO_ROUTE = Object.fromEntries(Object.entries(ROUTE_TO_TAB).map(([k, v]) => [v, k]));

// Auth state
let currentUser = null;

// State
let vpData = [];
let currentVP = null;
let bdoData = [];
let currentBDOBlock = null;
let meetingsData = [];
let currentMeetingId = null;
let meetingsSelectedDate = null;  // Currently selected date (YYYY-MM-DD)
let meetingsWeekOffset = 0;       // 0 = current week, -1 = last week, +1 = next week
let needsSchedulingCache = null;  // Cache for HoReCa "Meeting aligned" data

// DOM Elements
const elements = {
    blockSelect: document.getElementById('block-select'),
    vpSelect: document.getElementById('vp-select'),
    vpDetails: document.getElementById('vp-details'),
    vpName: document.getElementById('vp-name'),
    currentStage: document.getElementById('current-stage'),
    // Collapsible sections (integrated into vp-details)
    statusSection: document.getElementById('status-section'),
    meetingsSection: document.getElementById('meetings-section'),
    historySection: document.getElementById('history-section'),
    profileSection: document.getElementById('profile-section'),
    // Form elements
    newStage: document.getElementById('new-stage'),
    meetingNotes: document.getElementById('meeting-notes'),
    updatedBy: document.getElementById('updated-by'),
    submitBtn: document.getElementById('submit-update'),
    searchInput: document.getElementById('search-input'),
    filterStage: document.getElementById('filter-stage'),
    vpList: document.getElementById('vp-list'),
    toast: document.getElementById('toast'),
    toastMessage: document.getElementById('toast-message'),
    loading: document.getElementById('loading'),
    // Voice recording elements
    voiceRecordBtn: document.getElementById('voice-record-btn'),
    stopRecordingBtn: document.getElementById('stop-recording-btn'),
    recordingStatus: document.getElementById('recording-status'),
    recordingTime: document.getElementById('recording-time'),
    voiceLanguage: document.getElementById('voice-language'),
    voiceLangSelect: document.getElementById('voice-lang-select'),
    // Profile fields
    secretaryName: document.getElementById('secretary-name'),
    secretaryPhone: document.getElementById('secretary-phone'),
    sarpanchName: document.getElementById('sarpanch-name'),
    sarpanchPhone: document.getElementById('sarpanch-phone'),
    vpEmail: document.getElementById('vp-email'),
    contractorName: document.getElementById('contractor-name'),
    contractorPhone: document.getElementById('contractor-phone'),
    plannedRvms: document.getElementById('planned-rvms'),
    agreedRvms: document.getElementById('agreed-rvms'),
    // Cost & Operations fields
    electricityBearer: document.getElementById('electricity-bearer'),
    internetBearer: document.getElementById('internet-bearer'),
    handlerHiredBy: document.getElementById('handler-hired-by'),
    spaceType: document.getElementById('space-type'),
    // RVM Locations
    rvmLocationsSection: document.getElementById('rvm-locations-section'),
    rvmLocationsList: document.getElementById('rvm-locations-list'),
    captureLocationBtn: document.getElementById('capture-location-btn'),
    addLocationBtn: document.getElementById('add-location-btn'),
    saveProfileBtn: document.getElementById('save-profile-btn'),
};

// RVM Location tracking
let rvmLocations = [];

// Voice recording state
let mediaRecorder = null;
let audioChunks = [];
let recordingStartTime = null;
let recordingTimer = null;

// Initialize
document.addEventListener('DOMContentLoaded', init);

async function init() {
    // Check authentication first
    const authed = await checkAuth();
    if (!authed) {
        return; // Show login screen, don't init app
    }

    initApp();
}

async function checkAuth() {
    try {
        const response = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;
            showApp();
            applyRBAC();
            return true;
        }
    } catch (e) {
        // Network error — show login
    }
    showLoginScreen();
    return false;
}

function showLoginScreen() {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('main-app').style.display = 'none';
}

function showApp() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('main-app').style.display = '';
}

/**
 * Apply RBAC: hide nav items not in allowed_tabs, switch to allowed tab if needed
 */
function applyRBAC() {
    if (!currentUser || !currentUser.allowed_tabs) return;
    const allowed = new Set(currentUser.allowed_tabs);

    // Hide/show nav items (use class to override !important CSS)
    document.querySelectorAll('.nav-item[data-tab]').forEach(item => {
        const tab = item.dataset.tab;
        item.classList.toggle('rbac-hidden', !allowed.has(tab));
    });

    // Hide/show More sheet items
    document.querySelectorAll('.more-sheet-item[data-tab]').forEach(item => {
        const tab = item.dataset.tab;
        item.classList.toggle('rbac-hidden', !allowed.has(tab));
    });

    // If current active tab is not allowed, switch to first allowed
    const savedTab = localStorage.getItem('activeTab');
    if (savedTab && !allowed.has(savedTab)) {
        const firstAllowed = currentUser.allowed_tabs[0] || 'learning';
        switchToTab(firstAllowed);
    }

    applyDashboardRBAC();
}

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const pin = document.getElementById('login-pin').value.trim();
    const errorEl = document.getElementById('login-error');
    const submitBtn = document.getElementById('login-submit-btn');

    errorEl.classList.add('hidden');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Logging in...';

    try {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ email, pin }),
        });

        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;
            showApp();
            applyRBAC();
            initApp();
        } else {
            const err = await response.json().catch(() => ({}));
            errorEl.textContent = err.detail || 'Invalid email or PIN';
            errorEl.classList.remove('hidden');
        }
    } catch (e) {
        errorEl.textContent = 'Network error. Please try again.';
        errorEl.classList.remove('hidden');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Log In';
    }
}

async function handleLogout() {
    trackEvent('click', 'auth', 'Logout', '');
    try {
        await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
    } catch (e) {
        // Ignore — clear local state anyway
    }
    currentUser = null;
    showLoginScreen();
}

async function initApp() {
    populateStageDropdowns();

    // Load ALL data BEFORE setting up tabs (tab restore triggers dashboard render)
    await loadVPData();
    await loadMeetingsData();

    setupEventListeners();
    setupMasterDetailListeners();
    setupULBListeners();

    // Populate master panel filters and list
    populateMasterFilters();
    populateULBFilters();
    renderMasterVPList();
    renderULBMasterList();

    // Update tab badges after data is loaded
    updateTabBadges();

    // Setup tabs LAST so saved tab restore has data available
    setupTabs();

    // Auto-fill user name from auth
    if (currentUser && currentUser.name) {
        if (elements.updatedBy) elements.updatedBy.value = currentUser.name;
        localStorage.setItem('updatedBy', currentUser.name);
        localStorage.setItem('userName', currentUser.name);
        if (currentUser.email) localStorage.setItem('userEmail', currentUser.email);
        const commentAuthor = document.getElementById('comment-author');
        if (commentAuthor) commentAuthor.value = currentUser.name;
    } else {
        const savedName = localStorage.getItem('updatedBy');
        if (savedName && elements.updatedBy) {
            elements.updatedBy.value = savedName;
        }
    }
}

// Make auth functions globally accessible
window.handleLogin = handleLogin;
window.handleLogout = handleLogout;

/**
 * Update badge counts on Escalation, Meetings, and Today tabs
 */
function updateTabBadges() {
    const todayStr = new Date().toISOString().split('T')[0];
    const now = new Date();
    const cutoffTime = new Date(todayStr + 'T06:00:00');

    // --- Escalation badge: count of RED escalations ---
    const escBadge = document.getElementById('badge-escalation');
    if (escBadge) {
        const vpsWithUpcoming = new Set();
        meetingsData.forEach(m => {
            if (m.status === 'scheduled' && m.vpCode && m.eventDate >= todayStr) {
                vpsWithUpcoming.add(m.vpCode);
            }
        });
        let redCount = 0;
        vpData.forEach(vp => {
            const stage = vp.currentStage;
            if (!ESCALATION_STAGES[stage]) return;
            if (vpsWithUpcoming.has(vp.vpCode)) return;
            if (!vp.stageDate) return;
            const stageDate = new Date(vp.stageDate);
            if (isNaN(stageDate.getTime())) return;
            const wd = countWorkingDays(stageDate, now);
            if (wd > 3) redCount++;
        });
        if (redCount > 0) {
            escBadge.textContent = redCount;
            escBadge.className = 'nav-badge active';
        } else {
            escBadge.className = 'nav-badge';
        }
    }

    // --- Meetings badge: today's scheduled meetings ---
    const mtgBadge = document.getElementById('badge-meetings');
    if (mtgBadge) {
        const todayMeetings = meetingsData.filter(m =>
            m.status === 'scheduled' && m.eventDate === todayStr
        ).length;
        if (todayMeetings > 0) {
            mtgBadge.textContent = todayMeetings;
            mtgBadge.className = 'nav-badge active badge-blue';
        } else {
            mtgBadge.className = 'nav-badge';
        }
    }

    // --- Today badge: updates made today ---
    const todayBadge = document.getElementById('badge-today');
    if (todayBadge) {
        let todayUpdates = 0;
        vpData.forEach(vp => {
            if (!vp.lastUpdated) return;
            try {
                const t = new Date(vp.lastUpdated);
                if (t >= cutoffTime && t.toISOString().split('T')[0] === todayStr) todayUpdates++;
            } catch (e) {}
        });
        if (todayUpdates > 0) {
            todayBadge.textContent = todayUpdates;
            todayBadge.className = 'nav-badge active badge-gray';
        } else {
            todayBadge.className = 'nav-badge';
        }
    }
}

function getTabFromURL() {
    const path = window.location.pathname.replace(/^\//, '').split('/')[0]; // e.g. "VPs", "Learning"
    if (path && ROUTE_TO_TAB[path]) return ROUTE_TO_TAB[path];
    return null;
}

function setupTabs() {
    document.querySelectorAll('.nav-item').forEach(tab => {
        // Skip the More button — it has its own onclick handler
        if (tab.classList.contains('more-btn')) return;

        tab.addEventListener('click', async () => {
            switchToTab(tab.dataset.tab);
        });
    });

    // Handle browser back/forward
    window.addEventListener('popstate', (e) => {
        const tab = (e.state && e.state.tab) ? e.state.tab : getTabFromURL();
        if (tab) {
            switchToTab(tab);
        } else {
            // Root URL — go to default tab
            const firstAllowed = (currentUser && currentUser.allowed_tabs) ? currentUser.allowed_tabs[0] : 'vps';
            switchToTab(firstAllowed);
        }
    });

    // Determine initial tab: URL path > localStorage > default
    const urlTab = getTabFromURL();
    const savedTab = localStorage.getItem('activeTab');
    const initialTab = urlTab || savedTab || 'vps';
    switchToTab(initialTab);

    // Restore sidebar state on desktop
    if (window.innerWidth >= 1024 && localStorage.getItem('sidebarExpanded') === 'true') {
        const nav = document.getElementById('nav-bar');
        const content = document.querySelector('.content');
        const header = document.querySelector('.header');
        if (nav) nav.classList.add('expanded');
        if (content) content.classList.add('sidebar-expanded');
        if (header) header.classList.add('sidebar-expanded');
    }
}

async function switchToTab(tabId) {
    // Update active tab styling
    document.querySelectorAll('.nav-item').forEach(t => t.classList.remove('active'));
    const tabBtn = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
    if (tabBtn) tabBtn.classList.add('active');

    // If HoReCa or Learning is active, also highlight More button on mobile
    const moreBtn = document.querySelector('.more-btn');
    if (moreBtn) {
        if (tabId === 'horeca' || tabId === 'learning') {
            moreBtn.classList.add('active');
        } else {
            moreBtn.classList.remove('active');
        }
    }

    // Show corresponding content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const tabEl = document.getElementById(`${tabId}-tab`);
    if (tabEl) tabEl.classList.add('active');

    // Save active tab for persistence across refresh
    localStorage.setItem('activeTab', tabId);

    // Update URL (pushState) — skip if already at the right URL
    const route = TAB_TO_ROUTE[tabId] || tabId;
    const targetPath = '/' + route;
    if (window.location.pathname !== targetPath) {
        history.pushState({ tab: tabId }, '', targetPath);
    }

    // Fire dwell time for the tab being left
    if (_scrollPage && _tabEnterTime) {
        const dwell = Math.round((Date.now() - _tabEnterTime) / 1000);
        if (dwell >= 3) trackEvent('dwell', _scrollPage, '', dwell);
    }
    _tabEnterTime = Date.now();
    // Track page view + reset scroll milestone tracking for this page
    _scrollPage = tabId;
    trackEvent('page_view', tabId);

    // Load data for specific tabs
    if (tabId === 'vps') {
        renderMasterVPList();
    }
    if (tabId === 'ulbs') {
        renderULBMasterList();
    }
    if (tabId === 'dashboard') {
        if (bdoData.length === 0) await loadBDOData();
        loadDashboard();
    }
    if (tabId === 'meetings') {
        if (meetingsData.length === 0) await loadMeetingsData();
        renderMeetingsTab();
    }
    if (tabId === 'escalation') {
        renderEscalationTab();
    }
    if (tabId === 'today') {
        renderTodayActivity();
    }
    if (tabId === 'horeca') {
        initHoReCaTab();
    }
    if (tabId === 'learning') {
        initLearningTab();
    }
}

function toggleSidebar() {
    const nav = document.getElementById('nav-bar');
    const content = document.querySelector('.content');
    const header = document.querySelector('.header');
    nav.classList.toggle('expanded');
    content.classList.toggle('sidebar-expanded');
    if (header) header.classList.toggle('sidebar-expanded');
    localStorage.setItem('sidebarExpanded', nav.classList.contains('expanded'));
}

function populateStageDropdowns() {
    const stageOptions = STAGES.map(s =>
        `<option value="${s.value}">${s.number}. ${s.label}</option>`
    ).join('');

    if (elements.newStage) {
        elements.newStage.innerHTML = '<option value="">-- Select Stage --</option>' + stageOptions;
    }
    // Legacy filter stage (if exists)
    if (elements.filterStage) {
        elements.filterStage.innerHTML = '<option value="">All Stages</option>' + stageOptions;
    }
}

async function loadVPData() {
    showLoading(true);
    try {
        // Load from backend API
        const response = await fetch(`${API_BASE}/vps/all`).catch(() => null);
        if (response && response.ok) {
            vpData = await response.json();
            localStorage.setItem('vpDataCache', JSON.stringify(vpData));
        } else {
            // Use cached data
            vpData = JSON.parse(localStorage.getItem('vpDataCache') || '[]');
            if (vpData.length === 0) {
                showToast('Could not load VP data. Please try refreshing.', 'error');
            } else {
                showToast('Using cached data', 'info');
            }
        }
    } catch (error) {
        console.error('Error loading VP data:', error);
        vpData = JSON.parse(localStorage.getItem('vpDataCache') || '[]');
    }

    populateBlockDropdown();
    showLoading(false);
}

function parseSheetData(rows) {
    return rows.filter(row => row[0]).map((row, index) => ({
        id: index + 2,  // Row number in sheet
        block: row[0] || '',
        vpCode: row[1] || '',
        vpName: row[2] || '',
        bdoName: row[3] || '',
        bdoPhone: row[4] || '',
        secretaryName: row[5] || '',
        secretaryPhone: row[6] || '',
        sarpanchName: row[7] || '',
        sarpanchPhone: row[8] || '',
        email: row[9] || '',
        vpContact: row[10] || '',
        website: row[11] || '',
        address: row[12] || '',
        currentStage: row[13] || 'yet_to_meet',
        stageNumber: parseInt(row[14]) || 1,
        stageDate: row[15] || '',
        meetingNotes: row[16] || '',
        followUpDate: row[17] || '',
    }));
}

function populateBlockDropdown() {
    const blocks = [...new Set(vpData.map(vp => vp.block))].filter(b => b).sort();
    // Legacy block dropdown (if exists)
    if (elements.blockSelect) {
        elements.blockSelect.innerHTML = '<option value="">-- Select Block --</option>' +
            blocks.map(b => `<option value="${b}">${b}</option>`).join('');
    }
    // Also populate master panel filters
    populateMasterFilters();
}

function setupEventListeners() {
    // Block selection (legacy - kept for backwards compatibility)
    if (elements.blockSelect) {
        elements.blockSelect.addEventListener('change', () => {
            const block = elements.blockSelect.value;
            if (block && elements.vpSelect) {
                const vps = vpData.filter(vp => vp.block === block);
                elements.vpSelect.innerHTML = '<option value="">-- Select VP --</option>' +
                    vps.map(vp => `<option value="${vp.vpCode}">${vp.vpName}</option>`).join('');
                elements.vpSelect.disabled = false;
            } else if (elements.vpSelect) {
                elements.vpSelect.innerHTML = '<option value="">-- Select VP --</option>';
                elements.vpSelect.disabled = true;
            }
            hideVPDetails();
        });
    }

    // VP selection (legacy - kept for backwards compatibility)
    if (elements.vpSelect) {
        elements.vpSelect.addEventListener('change', () => {
            const vpCode = elements.vpSelect.value;
            if (vpCode) {
                currentVP = vpData.find(vp => vp.vpCode === vpCode);
                showVPDetails(currentVP);
            } else {
                hideVPDetails();
            }
        });
    }

    // Submit update
    elements.submitBtn?.addEventListener('click', submitUpdate);

    // Old VP List tab search and filter (legacy)
    elements.searchInput?.addEventListener('input', renderVPList);
    elements.filterStage?.addEventListener('change', renderVPList);

    // Save user name
    elements.updatedBy.addEventListener('blur', () => {
        localStorage.setItem('updatedBy', elements.updatedBy.value);
    });

    // Agreed RVMs change - update location inputs
    elements.agreedRvms?.addEventListener('change', updateRvmLocationsUI);
    elements.agreedRvms?.addEventListener('input', updateRvmLocationsUI);

    // Capture location button
    elements.captureLocationBtn?.addEventListener('click', captureCurrentLocation);

    // Add location button
    elements.addLocationBtn?.addEventListener('click', addNewLocation);

    // Save profile button
    elements.saveProfileBtn?.addEventListener('click', saveVPProfile);
}

// ==================== MASTER-DETAIL LAYOUT ====================

/**
 * Setup event listeners for master-detail layout
 */
function setupMasterDetailListeners() {
    // Search input
    const searchInput = document.getElementById('vp-search-input');
    if (searchInput) {
        let _searchTimer;
        searchInput.addEventListener('input', () => {
            renderMasterVPList();
            clearTimeout(_searchTimer);
            if (searchInput.value.length >= 2) {
                _searchTimer = setTimeout(() => trackEvent('click', 'vps', 'Search', searchInput.value), 1200);
            }
        });
    }

    // Block filter
    const blockFilter = document.getElementById('block-filter');
    if (blockFilter) {
        blockFilter.addEventListener('change', () => {
            renderMasterVPList();
            if (blockFilter.value) trackEvent('click', 'vps', 'Filter Block', blockFilter.value);
        });
    }

    // Stage filter
    const stageFilter = document.getElementById('stage-filter');
    if (stageFilter) {
        stageFilter.addEventListener('change', renderMasterVPList);
    }
}

/**
 * Populate master panel filter dropdowns
 */
function populateMasterFilters() {
    // Populate block filter
    const blockFilter = document.getElementById('block-filter');
    if (blockFilter) {
        const blocks = [...new Set(vpData.filter(vp => !isULB(vp)).map(vp => vp.block))].filter(b => b).sort();
        blockFilter.innerHTML = '<option value="">All Blocks</option>' +
            blocks.map(b => `<option value="${b}">${b}</option>`).join('');
    }

    // Populate stage filter
    const stageFilter = document.getElementById('stage-filter');
    if (stageFilter) {
        stageFilter.innerHTML = '<option value="">All Stages</option>' +
            STAGES.map(s => `<option value="${s.value}">${s.number}. ${s.label}</option>`).join('');
    }
}

/**
 * Render VP cards in the master panel with search/filter
 */
function renderMasterVPList() {
    const listContainer = document.getElementById('master-vp-list');
    const countBadge = document.getElementById('vp-count-badge');
    if (!listContainer) return;

    // Get filter values
    const searchTerm = document.getElementById('vp-search-input')?.value.toLowerCase() || '';
    const blockFilter = document.getElementById('block-filter')?.value || '';
    const stageFilter = document.getElementById('stage-filter')?.value || '';

    // Filter VPs (exclude ULBs — they have their own tab)
    const filtered = vpData.filter(vp => !isULB(vp)).filter(vp => {
        const matchesSearch = !searchTerm ||
            vp.vpName.toLowerCase().includes(searchTerm) ||
            vp.block.toLowerCase().includes(searchTerm) ||
            (vp.vpCode && vp.vpCode.toLowerCase().includes(searchTerm));
        const matchesBlock = !blockFilter || vp.block === blockFilter;
        const matchesStage = !stageFilter || vp.currentStage === stageFilter;
        return matchesSearch && matchesBlock && matchesStage;
    });

    // Update count badge
    if (countBadge) {
        countBadge.textContent = filtered.length;
    }

    // Sort by block name, then VP name
    filtered.sort((a, b) => {
        if (a.block !== b.block) return a.block.localeCompare(b.block);
        return a.vpName.localeCompare(b.vpName);
    });

    // Render VP cards (limit to 100 for performance)
    const displayList = filtered.slice(0, 100);

    if (displayList.length === 0) {
        listContainer.innerHTML = `
            <div class="master-empty">
                <p>No VPs found</p>
                <span class="hint">Try adjusting filters</span>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = displayList.map(vp => {
        const displayStage = STAGE_MIGRATION[vp.currentStage] || vp.currentStage;
        const stageLabel = getStageLabel(vp.currentStage);
        const stageNum = getStageNumber(vp.currentStage);
        const isSelected = currentVP && currentVP.vpCode === vp.vpCode;

        return `
            <div class="vp-card-mini ${displayStage} ${isSelected ? 'selected' : ''}"
                 onclick="selectVPFromMaster('${vp.vpCode}')"
                 data-vpcode="${vp.vpCode}">
                <div class="vp-card-mini-header">
                    <span class="vp-card-mini-name">${vp.vpName}</span>
                    <span class="vp-card-mini-stage-num">${stageNum}</span>
                </div>
                <div class="vp-card-mini-meta">
                    <span class="vp-card-mini-block">${vp.block}</span>
                    <span class="vp-card-mini-stage">${stageLabel}</span>
                </div>
            </div>
        `;
    }).join('');

    // Show "more" indicator if truncated
    if (filtered.length > 100) {
        listContainer.innerHTML += `
            <div class="master-more-hint">
                Showing 100 of ${filtered.length} VPs. Use filters to narrow down.
            </div>
        `;
    }
}

/**
 * Select a VP from the master list
 */
function selectVPFromMaster(vpCode) {
    const vp = vpData.find(v => v.vpCode === vpCode);
    if (!vp) return;
    trackEvent('click', 'vps', 'Open VP', `${vp.vpName} (${vp.block})`);
    currentVP = vp;

    // Update visual selection in master list
    document.querySelectorAll('.vp-card-mini').forEach(card => {
        card.classList.remove('selected');
        if (card.dataset.vpcode === vpCode) {
            card.classList.add('selected');
        }
    });

    // Move the shared detail panel back into VPs tab if it was moved to ULBs
    const detailPanel = document.getElementById('detail-panel');
    const vpsLayout = document.querySelector('#vps-tab .master-detail-layout');
    if (detailPanel && vpsLayout && !vpsLayout.contains(detailPanel)) {
        vpsLayout.appendChild(detailPanel);
    }

    // Show VP details
    showVPDetails(vp);

    // Switch to detail panel on mobile
    showDetailPanel();
}

/**
 * Show master panel (for mobile back navigation)
 */
function showMasterPanel() {
    // Find the active tab's master-detail layout
    const activeTab = document.querySelector('.tab-content.active');
    const layout = activeTab ? activeTab.querySelector('.master-detail-layout') : document.querySelector('.master-detail-layout');
    if (layout) {
        layout.classList.remove('detail-active');
    }

    // Hide VP details and show empty state
    hideVPDetails();

    // Clear selection state in master list
    document.querySelectorAll('.vp-card-mini').forEach(card => {
        card.classList.remove('selected');
    });
}

/**
 * Show detail panel (for mobile VP selection)
 */
function showDetailPanel() {
    const activeTab = document.querySelector('.tab-content.active');
    const layout = activeTab ? activeTab.querySelector('.master-detail-layout') : document.querySelector('.master-detail-layout');
    if (layout) {
        layout.classList.add('detail-active');
    }
}

// ==================== ULB TAB FUNCTIONS ====================

/**
 * Populate ULB stage filter dropdown
 */
function populateULBFilters() {
    const stageFilter = document.getElementById('ulb-stage-filter');
    if (stageFilter) {
        stageFilter.innerHTML = '<option value="">All Stages</option>' +
            STAGES.map(s => `<option value="${s.value}">${s.number}. ${s.label}</option>`).join('');
    }
}

/**
 * Render ULB cards in the ULB master panel
 */
function renderULBMasterList() {
    const listContainer = document.getElementById('ulb-master-list');
    const countBadge = document.getElementById('ulb-count-badge');
    if (!listContainer) return;

    // Get filter values
    const searchTerm = document.getElementById('ulb-search-input')?.value.toLowerCase() || '';
    const blockFilter = document.getElementById('ulb-block-filter')?.value || '';
    const stageFilter = document.getElementById('ulb-stage-filter')?.value || '';

    // Filter to ULBs only, then apply search/filter
    const filtered = vpData.filter(vp => isULB(vp)).filter(vp => {
        const matchesSearch = !searchTerm ||
            vp.vpName.toLowerCase().includes(searchTerm) ||
            vp.block.toLowerCase().includes(searchTerm) ||
            (vp.vpCode && vp.vpCode.toLowerCase().includes(searchTerm));
        const matchesBlock = !blockFilter || vp.block === blockFilter;
        const matchesStage = !stageFilter || vp.currentStage === stageFilter;
        return matchesSearch && matchesBlock && matchesStage;
    });

    // Update count badge
    if (countBadge) {
        countBadge.textContent = filtered.length;
    }

    // Sort by zone (block), then ULB name
    filtered.sort((a, b) => {
        if (a.block !== b.block) return a.block.localeCompare(b.block);
        return a.vpName.localeCompare(b.vpName);
    });

    if (filtered.length === 0) {
        listContainer.innerHTML = `
            <div class="master-empty">
                <p>No ULBs found</p>
                <span class="hint">Try adjusting filters</span>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = filtered.map(vp => {
        const displayStage = STAGE_MIGRATION[vp.currentStage] || vp.currentStage;
        const stageLabel = getStageLabel(vp.currentStage);
        const stageNum = getStageNumber(vp.currentStage);
        const isSelected = currentVP && currentVP.vpCode === vp.vpCode;

        return `
            <div class="vp-card-mini ${displayStage} ${isSelected ? 'selected' : ''}"
                 onclick="selectULBFromMaster('${vp.vpCode}')"
                 data-vpcode="${vp.vpCode}">
                <div class="vp-card-mini-header">
                    <span class="vp-card-mini-name">${vp.vpName}</span>
                    <span class="vp-card-mini-stage-num">${stageNum}</span>
                </div>
                <div class="vp-card-mini-meta">
                    <span class="vp-card-mini-block">${vp.block}</span>
                    <span class="vp-card-mini-stage">${stageLabel}</span>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Select a ULB from the ULB master list — reuses detail panel
 */
function selectULBFromMaster(vpCode) {
    const vp = vpData.find(v => v.vpCode === vpCode);
    if (!vp) return;

    currentVP = vp;

    // Update visual selection in ULB master list
    document.querySelectorAll('#ulb-master-list .vp-card-mini').forEach(card => {
        card.classList.remove('selected');
        if (card.dataset.vpcode === vpCode) {
            card.classList.add('selected');
        }
    });

    // Move the shared detail panel into the ULBs tab if not already there
    const detailPanel = document.getElementById('detail-panel');
    const ulbsLayout = document.querySelector('#ulbs-tab .master-detail-layout');
    if (detailPanel && ulbsLayout && !ulbsLayout.contains(detailPanel)) {
        ulbsLayout.appendChild(detailPanel);
    }

    // Show VP details (reuse same detail view)
    showVPDetails(vp);

    // Switch to detail panel on mobile
    showDetailPanel();
}

/**
 * Setup ULB tab event listeners
 */
function setupULBListeners() {
    const searchInput = document.getElementById('ulb-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', renderULBMasterList);
    }

    const blockFilter = document.getElementById('ulb-block-filter');
    if (blockFilter) {
        blockFilter.addEventListener('change', renderULBMasterList);
    }

    const stageFilter = document.getElementById('ulb-stage-filter');
    if (stageFilter) {
        stageFilter.addEventListener('change', renderULBMasterList);
    }
}

// Make master-detail functions globally accessible
window.selectVPFromMaster = selectVPFromMaster;
window.selectULBFromMaster = selectULBFromMaster;
window.showMasterPanel = showMasterPanel;
window.showDetailPanel = showDetailPanel;

function showVPDetails(vp) {
    if (!vp) return;

    elements.vpName.textContent = vp.vpName;

    // Handle legacy stages and display milestone
    const displayStage = STAGE_MIGRATION[vp.currentStage] || vp.currentStage;
    elements.currentStage.textContent = getStageLabel(vp.currentStage);
    elements.currentStage.className = 'stage-badge ' + displayStage;

    // Render pending follow-up indicator
    renderPendingFollowup(vp);

    // Populate profile fields (editable)
    elements.secretaryName.value = vp.secretaryName || '';
    elements.secretaryPhone.value = vp.secretaryPhone || '';
    elements.sarpanchName.value = vp.sarpanchName || '';
    elements.sarpanchPhone.value = vp.sarpanchPhone || '';
    elements.vpEmail.value = vp.email || vp.vpEmail || '';
    elements.contractorName.value = vp.contractorName || '';
    elements.contractorPhone.value = vp.contractorPhone || '';
    elements.plannedRvms.value = vp.plannedRvms || 1;  // Default to 1
    elements.agreedRvms.value = vp.agreedRvms || '';

    // Cost & Operations fields
    elements.electricityBearer.value = vp.electricityBearer || '';
    elements.internetBearer.value = vp.internetBearer || '';
    elements.handlerHiredBy.value = vp.handlerHiredBy || '';
    elements.spaceType.value = vp.spaceType || '';

    // Load RVM locations
    rvmLocations = vp.rvmLocations || [];
    updateRvmLocationsUI();

    // Pre-select current stage in dropdown (use migrated value)
    elements.newStage.value = displayStage;

    // Hide empty state, show VP details
    const detailEmpty = document.getElementById('detail-empty');
    if (detailEmpty) detailEmpty.classList.add('hidden');
    elements.vpDetails.classList.remove('hidden');

    // Collapse all collapsible sections by default (#19)
    const sections = ['status-section', 'meetings-section', 'history-section', 'profile-section'];
    sections.forEach(id => {
        const section = document.getElementById(id);
        if (section) section.classList.add('collapsed');
    });

    // Render NOC tracking strip (#34)
    renderNocTracking(vp);

    // Render VP meetings for this VP (#21)
    renderVPMeetings(vp);

    // Render conversation history (#13)
    renderConversationHistory(vp);
}

/**
 * Render NOC tracking info strip (visible for stage >= 7)
 */
function renderNocTracking(vp) {
    const strip = document.getElementById('noc-tracking-strip');
    if (!strip) return;

    // Show only for stage 7 (email_sent) and beyond
    if (resolveStageNumber(vp) >= 7) {
        strip.classList.remove('hidden');

        // NOC Email Sent Date
        const emailSentEl = document.getElementById('noc-email-sent-date');
        if (emailSentEl) {
            emailSentEl.textContent = vp.nocEmailSentDate || '--';
        }

        // Email Read
        const emailReadEl = document.getElementById('noc-email-read');
        if (emailReadEl) {
            const readVal = (vp.emailRead || '').toLowerCase();
            if (readVal === 'yes') {
                emailReadEl.textContent = 'Yes';
                emailReadEl.className = 'noc-track-value noc-yes';
            } else if (readVal === 'no') {
                emailReadEl.textContent = 'No';
                emailReadEl.className = 'noc-track-value noc-no';
            } else {
                emailReadEl.textContent = '--';
                emailReadEl.className = 'noc-track-value';
            }
        }

        // Days Since Email (computed)
        const daysSinceEl = document.getElementById('noc-days-since');
        if (daysSinceEl) {
            if (vp.nocEmailSentDate) {
                const sentDate = new Date(vp.nocEmailSentDate);
                const today = new Date();
                const diffMs = today - sentDate;
                const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
                daysSinceEl.textContent = `${diffDays}d`;
                // Color code: green <= 3, yellow 4-7, red > 7
                if (diffDays <= 3) {
                    daysSinceEl.className = 'noc-track-value noc-ok';
                } else if (diffDays <= 7) {
                    daysSinceEl.className = 'noc-track-value noc-warn';
                } else {
                    daysSinceEl.className = 'noc-track-value noc-alert';
                }
            } else {
                daysSinceEl.textContent = '--';
                daysSinceEl.className = 'noc-track-value';
            }
        }

        // Signed NOC Date
        const signedEl = document.getElementById('noc-signed-date');
        if (signedEl) {
            if (vp.signedNocDate) {
                signedEl.textContent = vp.signedNocDate;
                signedEl.className = 'noc-track-value noc-yes';
            } else {
                signedEl.textContent = '--';
                signedEl.className = 'noc-track-value';
            }
        }
    } else {
        strip.classList.add('hidden');
    }
}

/**
 * Render pending follow-up indicator below the stage badge
 */
function renderPendingFollowup(vp) {
    const pendingEl = document.getElementById('pending-followup');
    if (!pendingEl) return;

    // Check for scheduled meetings for this VP
    const upcomingMeeting = meetingsData.find(m =>
        m.vpCode === vp.vpCode &&
        m.status === 'scheduled' &&
        new Date(m.eventDate) >= new Date()
    );

    // Also check followUpDate from VP data
    const followUpDate = vp.followUpDate;
    const hasFollowUp = followUpDate && new Date(followUpDate) >= new Date();

    if (upcomingMeeting) {
        const dateObj = new Date(upcomingMeeting.eventDate + 'T' + (upcomingMeeting.eventTime || '10:00'));
        const dateStr = dateObj.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
        const timeStr = dateObj.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });

        pendingEl.innerHTML = `
            <svg viewBox="0 0 24 24"><path fill="currentColor" d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V9h14v11z"/></svg>
            <span>Follow-up: ${dateStr}, ${timeStr}</span>
        `;
        pendingEl.classList.remove('hidden');
    } else if (hasFollowUp) {
        const dateObj = new Date(followUpDate);
        const dateStr = dateObj.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

        pendingEl.innerHTML = `
            <svg viewBox="0 0 24 24"><path fill="currentColor" d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V9h14v11z"/></svg>
            <span>Follow-up: ${dateStr}</span>
        `;
        pendingEl.classList.remove('hidden');
    } else {
        pendingEl.classList.add('hidden');
    }
}

function hideVPDetails() {
    currentVP = null;
    elements.vpDetails.classList.add('hidden');

    // Show empty state
    const detailEmpty = document.getElementById('detail-empty');
    if (detailEmpty) detailEmpty.classList.remove('hidden');
}

/**
 * Render meetings for the selected VP
 */
function renderVPMeetings(vp) {
    const meetingsList = document.getElementById('vp-meetings-list');
    const meetingsHint = document.getElementById('meetings-count-hint');
    if (!meetingsList) return;

    // Filter meetings for this VP
    const vpMeetings = meetingsData.filter(m =>
        m.vpCode === vp.vpCode && m.status !== 'cancelled'
    ).sort((a, b) => new Date(b.eventDate) - new Date(a.eventDate));

    // Update hint
    if (meetingsHint) {
        meetingsHint.textContent = vpMeetings.length > 0
            ? `${vpMeetings.length} meeting${vpMeetings.length > 1 ? 's' : ''}`
            : 'No meetings scheduled';
    }

    if (vpMeetings.length === 0) {
        meetingsList.innerHTML = `
            <div class="empty-state">
                <p>No meetings scheduled for this VP</p>
                <button class="btn btn-outline btn-small" onclick="openScheduleFollowup()">
                    Schedule Meeting
                </button>
            </div>
        `;
        return;
    }

    meetingsList.innerHTML = vpMeetings.map(m => {
        const dateObj = new Date(m.eventDate + 'T' + (m.eventTime || '10:00'));
        const dateStr = dateObj.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
        const timeStr = dateObj.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
        const isPast = dateObj < new Date();
        const statusClass = m.status === 'completed' ? 'completed' : (isPast ? 'past' : 'upcoming');

        const typeLabel = getEventTypeLabel(m.eventType, m.eventTitle);
        const titleClass = getMeetingTitleClass(m.eventTitle);

        return `
            <div class="vp-meeting-card ${statusClass} ${titleClass}">
                <div class="meeting-date-time">
                    <span class="meeting-date">${dateStr}</span>
                    <span class="meeting-time">${timeStr}</span>
                </div>
                <div class="meeting-details">
                    <span class="meeting-type-badge ${titleClass}">${typeLabel}</span>
                    ${m.assignedTo ? `<span class="meeting-assigned">Assigned: ${m.assignedTo}</span>` : ''}
                    ${m.notes ? `<span class="meeting-note">${m.notes.substring(0, 50)}${m.notes.length > 50 ? '...' : ''}</span>` : ''}
                </div>
                <div class="meeting-actions">
                    ${m.status !== 'completed' ? `<button class="btn-icon" onclick="editMeeting('${m.meetingId}')" title="Edit"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg></button>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Render comments section (past notes) for the selected VP
 * Format: "[timestamp|type|author] content\n---\n..."
 * Types: direct, meeting, legacy
 */
function renderConversationHistory(vp) {
    const historyContainer = document.getElementById('conversation-history');
    const historyHint = document.getElementById('history-count-hint');
    if (!historyContainer) return;

    // Prefill author from localStorage
    const commentAuthor = document.getElementById('comment-author');
    if (commentAuthor) {
        commentAuthor.value = localStorage.getItem('userName') || '';
    }

    // Parse meeting notes (stored as: "[timestamp|type|author] note\n---\n[older notes]")
    const notesRaw = vp.meetingNotes || '';
    if (!notesRaw.trim()) {
        if (historyHint) historyHint.textContent = 'No comments yet';
        historyContainer.innerHTML = `
            <div class="empty-state">
                <p>No comments yet</p>
                <p class="hint">Add a comment above or update status</p>
            </div>
        `;
        return;
    }

    // Split by "---" separator
    const entries = notesRaw.split('\n---\n').filter(e => e.trim());
    if (historyHint) {
        historyHint.textContent = `${entries.length} comment${entries.length > 1 ? 's' : ''}`;
    }

    // Parse each entry - support both old and new format
    const parsedEntries = entries.map(entry => {
        // New format: "[timestamp|type|author] content"
        const newMatch = entry.match(/^\[([^|]+)\|([^|]+)\|([^\]]*)\]\s*([\s\S]*)/);
        if (newMatch) {
            return {
                timestamp: newMatch[1].trim(),
                type: newMatch[2].trim(),
                author: newMatch[3].trim(),
                content: newMatch[4].trim()
            };
        }
        // Old format: "[timestamp] content"
        const oldMatch = entry.match(/^\[([^\]]+)\]\s*([\s\S]*)/);
        if (oldMatch) {
            return {
                timestamp: oldMatch[1].trim(),
                type: 'meeting',
                author: '',
                content: oldMatch[2].trim()
            };
        }
        // No timestamp at all (very old data)
        return { timestamp: '', type: 'legacy', author: '', content: entry.trim() };
    });

    historyContainer.innerHTML = parsedEntries.map((entry, idx) => {
        const icon = getCommentIcon(entry.type);
        const typeClass = `type-${entry.type || 'meeting'}`;
        const authorDisplay = entry.author || 'Team';
        const formattedTime = formatCommentTimestamp(entry.timestamp);
        const sourceLabel = getSourceLabel(entry.type);

        return `
            <div class="comment-card ${typeClass} ${idx === 0 ? 'latest' : ''}">
                <div class="comment-header">
                    <span class="comment-icon">${icon}</span>
                    <span class="comment-author">${authorDisplay}</span>
                    <span class="comment-timestamp">${formattedTime}</span>
                    ${sourceLabel ? `<span class="comment-source">${sourceLabel}</span>` : ''}
                </div>
                <div class="comment-content">${entry.content}</div>
            </div>
        `;
    }).join('');
}

/**
 * Get icon for comment type
 */
function getCommentIcon(type) {
    switch (type) {
        case 'direct': return '💬';
        case 'meeting': return '📅';
        case 'legacy': return '📜';
        default: return '💬';
    }
}

/**
 * Get source label for comment type
 */
function getSourceLabel(type) {
    switch (type) {
        case 'direct': return '';
        case 'meeting': return 'from Meeting';
        case 'legacy': return 'Legacy';
        default: return '';
    }
}

/**
 * Format timestamp for display
 */
function formatCommentTimestamp(timestamp) {
    if (!timestamp) return '';
    if (timestamp.includes('Legacy') || timestamp.includes('Pre-')) return timestamp;

    try {
        const date = new Date(timestamp);
        if (isNaN(date.getTime())) return timestamp;

        const now = new Date();
        const diffMs = now - date;
        const diffHours = diffMs / (1000 * 60 * 60);
        const diffDays = diffMs / (1000 * 60 * 60 * 24);

        if (diffHours < 1) return 'Just now';
        if (diffHours < 24) return `${Math.floor(diffHours)} hour${Math.floor(diffHours) > 1 ? 's' : ''} ago`;
        if (diffDays < 2) return 'Yesterday';
        if (diffDays < 7) return `${Math.floor(diffDays)} days ago`;

        return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
        return timestamp;
    }
}

/**
 * Post a direct comment without changing status
 */
async function postComment() {
    if (!currentVP) {
        showToast('Please select a VP first', 'error');
        return;
    }

    const commentInput = document.getElementById('new-comment-input');
    const authorInput = document.getElementById('comment-author');

    const content = commentInput?.value?.trim();
    const author = authorInput?.value?.trim();

    if (!content) {
        showToast('Please enter a comment', 'error');
        return;
    }

    if (!author) {
        showToast('Please enter your name', 'error');
        return;
    }

    // Save author name for future use
    localStorage.setItem('userName', author);

    try {
        const response = await fetch(`${API_BASE}/comment`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                vp_code: currentVP.vpCode,
                comment: content,
                author: author,
                comment_type: 'direct'
            })
        });

        if (response.ok) {
            // Clear input
            commentInput.value = '';

            // Reload VP data to show updated comments
            await loadVPData();

            // Re-select the current VP to refresh the view
            const updatedVP = vpData.find(v => v.vpCode === currentVP.vpCode);
            if (updatedVP) {
                currentVP = updatedVP;
                renderConversationHistory(updatedVP);
            }

            showToast('Comment posted', 'success');
        } else {
            const error = await response.json();
            showToast(error.detail || 'Failed to post comment', 'error');
        }
    } catch (error) {
        console.error('Error posting comment:', error);
        showToast('Error posting comment', 'error');
    }
}

// Expose postComment globally
window.postComment = postComment;

function getStageLabel(stageValue) {
    // Handle legacy stages
    const migratedValue = STAGE_MIGRATION[stageValue] || stageValue;
    const stage = STAGES.find(s => s.value === migratedValue);
    return stage ? stage.label : stageValue;
}

/**
 * Get the correct stage number, handling legacy stages
 */
function getStageNumber(stageValue) {
    const migratedValue = STAGE_MIGRATION[stageValue] || stageValue;
    const stage = STAGES.find(s => s.value === migratedValue);
    return stage ? stage.number : 1;
}

async function submitUpdate() {
    if (!currentVP) {
        showToast('Please select a VP first', 'error');
        return;
    }

    const newStage = elements.newStage.value;
    const meetingNotes = elements.meetingNotes.value.trim();
    const updatedBy = elements.updatedBy.value.trim();

    if (!newStage) {
        showToast('Please select a stage', 'error');
        return;
    }

    if (!updatedBy) {
        showToast('Please enter your name', 'error');
        return;
    }

    showLoading(true);

    try {
        // Update the Google Sheet directly
        const rowData = [
            currentVP.block,
            currentVP.vpCode,
            currentVP.vpName,
            currentVP.bdoName,
            currentVP.bdoPhone,
            currentVP.secretaryName,
            currentVP.secretaryPhone,
            currentVP.sarpanchName,
            currentVP.sarpanchPhone,
            currentVP.email,
            currentVP.vpContact,
            currentVP.website,
            currentVP.address,
            newStage,  // Current_Stage
            STAGES.find(s => s.value === newStage)?.number || '',  // Stage_Number
            new Date().toISOString().split('T')[0],  // Stage_Date
            meetingNotes || currentVP.meetingNotes,  // Meeting_Notes
            currentVP.followUpDate || '',  // Follow_Up_Date (keep existing, managed via Meetings)
            currentVP.locationGps || '',
            currentVP.address,
            '', '', '', '', '', '', '', '',  // Placeholder fields
            new Date().toISOString(),  // Last_Updated
            updatedBy  // Updated_By
        ];

        // Try to update via backend API
        trackEvent('click', 'vps', `Stage: ${currentVP.vpName||currentVP.vpCode}`, `${currentVP.block} → ${newStage}`);
        const response = await fetch(`${API_BASE}/update/stage`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                vp_code: currentVP.vpCode,
                block: currentVP.block,
                new_stage: newStage,
                meeting_notes: meetingNotes,
                updated_by: updatedBy
            })
        }).catch(() => null);

        if (response && response.ok) {
            showToast('Update saved successfully!', 'success');
        } else {
            // Fallback: Save to localStorage for sync later
            saveLocalUpdate({
                vpCode: currentVP.vpCode,
                ...rowData,
                timestamp: Date.now()
            });
            showToast('Saved locally. Will sync when online.', 'success');
        }

        // Update local data
        const vpIndex = vpData.findIndex(vp => vp.vpCode === currentVP.vpCode);
        if (vpIndex >= 0) {
            vpData[vpIndex].currentStage = newStage;
            vpData[vpIndex].stageNumber = STAGES.find(s => s.value === newStage)?.number || 1;
            vpData[vpIndex].meetingNotes = meetingNotes || vpData[vpIndex].meetingNotes;

            // Also update currentVP to reflect changes
            currentVP.currentStage = newStage;
            currentVP.stageNumber = vpData[vpIndex].stageNumber;
            if (meetingNotes) currentVP.meetingNotes = meetingNotes;

            // Update localStorage cache so list shows correct status
            localStorage.setItem('vpDataCache', JSON.stringify(vpData));

            // Re-render master list to reflect updated status
            renderMasterVPList();
        }

        // Clear form
        elements.meetingNotes.value = '';
        showVPDetails(currentVP);

    } catch (error) {
        console.error('Update error:', error);
        showToast('Error saving update. Please try again.', 'error');
    }

    showLoading(false);
}

function saveLocalUpdate(update) {
    const pendingUpdates = JSON.parse(localStorage.getItem('pendingUpdates') || '[]');
    pendingUpdates.push(update);
    localStorage.setItem('pendingUpdates', JSON.stringify(pendingUpdates));
}

async function loadDashboard() {
    setupDashboardTabs();
    loadProgressDashboard();
    loadRvmDashboard();
    loadCostDashboard();
}

function setupDashboardTabs() {
    document.querySelectorAll('.dash-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.dash-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const dashId = tab.dataset.dash;
            if (dashId !== 'activity') trackEvent('page_view', `dashboard:${dashId}`);
            document.querySelectorAll('.dash-content').forEach(c => c.classList.remove('active'));
            document.getElementById(`dash-${dashId}`).classList.add('active');

            // Lazy-load HoReCa dashboard when tab is clicked
            if (dashId === 'horeca') {
                loadDashHoReCa();
            }
            // Lazy-load RVM Deployment when tab is clicked
            if (dashId === 'ct') {
                loadRvmDeployment();
            }
            // Lazy-load Activity Log when tab is clicked
            if (dashId === 'activity') {
                trackEvent('page_view', 'activity');
                loadActivityLog();
            }

            localStorage.setItem('activeDashTab', dashId);
        });
    });

    // RBAC: hide HoReCa sub-tab for VP-only users
    applyDashboardRBAC();

    // Restore last active dashboard sub-tab
    const savedDash = localStorage.getItem('activeDashTab');
    if (savedDash) {
        const dashBtn = document.querySelector(`.dash-tab[data-dash="${savedDash}"]`);
        if (dashBtn && !dashBtn.classList.contains('rbac-hidden')) {
            dashBtn.click();
        }
    }
}

/**
 * Load HoReCa dashboard content inside the main Dashboard tab
 */
async function loadDashHoReCa() {
    const container = document.getElementById('dash-horeca-content');
    if (!container) return;
    if (container.dataset.loaded === 'true') return; // Already loaded

    try {
        const res = await fetch(`${API_BASE}/horeca/crm/summary`);
        if (!res.ok) throw new Error('Failed to load');
        const data = await res.json();
        container.dataset.loaded = 'true';
        renderDashHoReCa(container, data);
    } catch (e) {
        container.innerHTML = '<div class="hcrm-error">Failed to load HoReCa dashboard</div>';
    }
}

/**
 * Render HoReCa dashboard inside the main Dashboard tab.
 * Mirrors the existing renderHorecaDashboard() but targets a different container.
 */
function renderDashHoReCa(container, data) {
    const statusCounts = data.statusCounts || {};
    const byZone = data.byZone || {};
    const byType = data.byType || {};
    const recentUpdates = data.recentUpdates || [];
    const total = data.total || 0;

    const statusColors = {
        'No Status': '#a8a29e',
        'De-listed': '#dc2626',
        'Call not answered': '#ea580c',
        'Call answered': '#0d9488',
        'Pre-meeting mail to be sent': '#7c3aed',
        'Pre-meeting mail sent': '#6d28d9',
        'Meeting aligned': '#d97706',
        'Meeting done': '#16a34a',
        'Post-meeting mail to be sent': '#7c3aed',
        'Post meeting mail sent': '#7c3aed',
        'OB Form Opened': '#2563eb',
        'OB Form Filled': '#059669',
    };

    const statuses = [
        'No Status', 'De-listed', 'Call not answered', 'Call answered',
        'Pre-meeting mail to be sent', 'Pre-meeting mail sent',
        'Meeting aligned', 'Meeting done',
        'Post-meeting mail to be sent', 'Post meeting mail sent',
        'OB Form Opened', 'OB Form Filled',
    ];

    // Funnel
    let funnelHtml = '<div class="hcrm-funnel">';
    statuses.forEach(s => {
        const count = statusCounts[s] || 0;
        if (count > 0 || ['No Status', 'Meeting aligned', 'Meeting done', 'OB Form Filled'].includes(s)) {
            const color = statusColors[s] || '#a8a29e';
            funnelHtml += `<div class="hcrm-funnel-card" style="border-left: 3px solid ${color}">
                <div class="hcrm-funnel-count">${count}</div>
                <div class="hcrm-funnel-label">${s}</div>
            </div>`;
        }
    });
    funnelHtml += '</div>';

    // Type breakdown table
    const types = Object.keys(byType).sort((a, b) => (byType[b] || 0) - (byType[a] || 0));
    let typeTableHtml = '<div class="card"><h2>By Type</h2><div class="hcrm-table-scroll"><table class="hcrm-table"><thead><tr><th>Type</th><th class="num">Count</th><th class="num">%</th></tr></thead><tbody>';
    types.forEach(t => {
        const count = byType[t] || 0;
        const pct = total > 0 ? ((count / total) * 100).toFixed(1) : '0';
        typeTableHtml += `<tr><td>${t}</td><td class="num">${count}</td><td class="num">${pct}%</td></tr>`;
    });
    typeTableHtml += '</tbody></table></div></div>';

    // Zone breakdown table (top 20)
    const zones = Object.entries(byZone).sort((a, b) => b[1] - a[1]).slice(0, 20);
    let zoneTableHtml = '<div class="card"><h2>Top Zones</h2><div class="hcrm-table-scroll"><table class="hcrm-table"><thead><tr><th>Zone</th><th class="num">Count</th></tr></thead><tbody>';
    zones.forEach(([zone, count]) => {
        zoneTableHtml += `<tr><td>${zone}</td><td class="num">${count}</td></tr>`;
    });
    zoneTableHtml += '</tbody></table></div></div>';

    // Recent activity
    let recentHtml = '<div class="card"><h2>Recent Activity</h2><div class="hcrm-recent-list">';
    recentUpdates.slice(0, 20).forEach(r => {
        const name = r.name || r.Name || 'Unknown';
        const status = r.outreach_status || '';
        const updatedBy = r.updated_by || '';
        const lastUpdated = r.last_updated || '';
        let timeAgo = '';
        if (lastUpdated) {
            const diff = Date.now() - new Date(lastUpdated).getTime();
            const hours = Math.floor(diff / 3600000);
            timeAgo = hours < 1 ? 'Just now' : hours < 24 ? `${hours}h ago` : `${Math.floor(hours/24)}d ago`;
        }
        const statusClass = HCRM_STATUS_COLORS[status] || 'hcrm-status-none';
        recentHtml += `<div class="hcrm-recent-item">
            <span class="hcrm-recent-name">${escapeHtml(name)}</span>
            <span class="hcrm-card-status ${statusClass}">${escapeHtml(status || 'No Status')}</span>
            <div class="hcrm-recent-meta">${escapeHtml(updatedBy)}${timeAgo ? ' · ' + timeAgo : ''}</div>
        </div>`;
    });
    recentHtml += '</div></div>';

    container.innerHTML = `
        <div class="card"><h2>HoReCa Outreach Funnel</h2>${funnelHtml}</div>
        ${typeTableHtml}
        ${zoneTableHtml}
        ${recentHtml}
    `;
}

/**
 * Hide/show dashboard sub-tabs based on RBAC role
 */
function applyDashboardRBAC() {
    if (!currentUser) return;
    const role = currentUser.role;
    const horecaTab = document.querySelector('.dash-tab-horeca');
    if (horecaTab) {
        const showHoreca = role === 'admin' || role === 'horeca';
        horecaTab.classList.toggle('rbac-hidden', !showHoreca);
    }
    // Hide VP-specific sub-tabs (Progress, RVM, Cost) for horeca-only users
    if (role === 'horeca') {
        document.querySelectorAll('.dash-tab[data-dash="progress"], .dash-tab[data-dash="rvm"], .dash-tab[data-dash="cost"]').forEach(btn => {
            btn.classList.add('rbac-hidden');
        });
        const horecaBtn = document.querySelector('.dash-tab[data-dash="horeca"]');
        if (horecaBtn) horecaBtn.click();
    }
    // Activity tab: superadmin only
    const activityTab = document.querySelector('.dash-tab-activity');
    if (activityTab) {
        activityTab.style.display = currentUser.email === 'ashwin.singh@recykal.com' ? '' : 'none';
    }
}

/**
 * Render Today's Activity dashboard
 */
function renderTodayActivity() {
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];

    // Update date label
    const dateLabel = document.getElementById('today-date-label');
    if (dateLabel) {
        dateLabel.textContent = today.toLocaleDateString('en-IN', {
            weekday: 'long',
            day: 'numeric',
            month: 'short',
            year: 'numeric'
        });
    }

    // Collect today's activities
    const activities = [];

    // 1. VP Updates made today (based on lastUpdated)
    const vpUpdatesToday = vpData.filter(vp => {
        if (!vp.lastUpdated) return false;
        const updateDate = vp.lastUpdated.split('T')[0];
        return updateDate === todayStr;
    });

    vpUpdatesToday.forEach(vp => {
        activities.push({
            type: 'vp_update',
            icon: '📝',
            title: `${vp.vpName}`,
            subtitle: `Stage: ${getStageLabel(vp.currentStage)}`,
            block: vp.block,
            timestamp: vp.lastUpdated,
            user: vp.updatedBy || 'Team'
        });
    });

    // 2. Meetings scheduled/completed today
    const meetingsToday = meetingsData.filter(m => m.eventDate === todayStr);
    meetingsToday.forEach(m => {
        activities.push({
            type: 'meeting',
            icon: m.status === 'completed' ? '✅' : '📅',
            title: `${m.vpName}`,
            subtitle: `${m.eventTime || '10:00'} - ${getEventTypeLabel(m.eventType)}`,
            block: m.block,
            timestamp: m.eventDate,
            user: m.assignedTo || 'Team',
            status: m.status
        });
    });

    // 3. BDO Updates today (if BDO data has lastUpdated)
    // (BDO-Tracker doesn't have lastUpdated column, so skip for now)

    // Calculate stats
    const statsContainer = document.getElementById('today-stats');
    const vpCount = vpUpdatesToday.length;
    const meetingCount = meetingsToday.length;
    const completedCount = meetingsToday.filter(m => m.status === 'completed').length;

    if (statsContainer) {
        statsContainer.innerHTML = `
            <div class="today-stat-card">
                <span class="today-stat-icon">📝</span>
                <span class="today-stat-value">${vpCount}</span>
                <span class="today-stat-label">VPs Updated</span>
            </div>
            <div class="today-stat-card">
                <span class="today-stat-icon">📅</span>
                <span class="today-stat-value">${meetingCount}</span>
                <span class="today-stat-label">Meetings Today</span>
            </div>
            <div class="today-stat-card">
                <span class="today-stat-icon">✅</span>
                <span class="today-stat-value">${completedCount}</span>
                <span class="today-stat-label">Completed</span>
            </div>
            <div class="today-stat-card">
                <span class="today-stat-icon">📊</span>
                <span class="today-stat-value">${activities.length}</span>
                <span class="today-stat-label">Total Activities</span>
            </div>
        `;
    }

    // Sort activities by timestamp (most recent first)
    activities.sort((a, b) => {
        const timeA = a.timestamp || '';
        const timeB = b.timestamp || '';
        return timeB.localeCompare(timeA);
    });

    // Render activity feed
    const feedContainer = document.getElementById('today-activity-feed');
    if (feedContainer) {
        if (activities.length === 0) {
            feedContainer.innerHTML = `
                <div class="empty-state">
                    <p>No activity recorded today yet</p>
                    <p class="hint">Updates to VPs and meetings will appear here</p>
                </div>
            `;
        } else {
            feedContainer.innerHTML = activities.map(activity => `
                <div class="activity-item activity-${activity.type}">
                    <span class="activity-icon">${activity.icon}</span>
                    <div class="activity-content">
                        <div class="activity-title">${activity.title}</div>
                        <div class="activity-subtitle">${activity.subtitle}</div>
                        <div class="activity-meta">
                            <span class="activity-block">${activity.block}</span>
                            <span class="activity-user">by ${activity.user}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }
    }
}

function loadProgressDashboard() {
    // Filter to VP-only data (exclude ULBs) for VP pipeline
    const vpOnly = vpData.filter(vp => !isULB(vp));

    // Calculate stats using resolveStageNumber (handles enum values, labels, and legacy)
    const total = vpOnly.length;
    const meetingsDone = vpOnly.filter(vp => resolveStageNumber(vp) >= 3).length;
    const locationsFinalized = vpOnly.filter(vp => resolveStageNumber(vp) >= 6).length;
    const devicesInstalled = vpOnly.filter(vp => resolveStageNumber(vp) >= 15).length;

    // Calculate BDO stats for holistic funnel
    const totalBlocks = bdoData.length || 12;
    const blocksUnlocked = bdoData.filter(b =>
        ['meeting_done', 'communication_sent'].includes(b.currentStage)
    ).length;

    // Calculate VPs Unlocked (VPs in blocks where BDO meeting is done)
    const unlockedBlockNames = bdoData
        .filter(b => ['meeting_done', 'communication_sent'].includes(b.currentStage))
        .map(b => b.block);
    const vpsUnlocked = vpOnly.filter(vp => unlockedBlockNames.includes(vp.block)).length;

    // Branch stats: VPs currently AT each panch stage (not cumulative)
    const atFirstMeetingDone = vpOnly.filter(vp => resolveStageNumber(vp) === 3).length;
    const atPanchScheduled = vpOnly.filter(vp => resolveStageNumber(vp) === 4).length;
    const atPanchDone = vpOnly.filter(vp => resolveStageNumber(vp) === 5).length;

    // Render holistic funnel using resolveStageNumber for accurate counts
    renderHolisticFunnel({
        totalBlocks,
        blocksUnlocked,
        totalVPs: total,
        vpsUnlocked,
        contacted: vpOnly.filter(vp => resolveStageNumber(vp) >= 2).length,
        meetingsDone,
        // Branch data
        atFirstMeetingDone,
        atPanchScheduled,
        atPanchDone,
        inPanchPath: atPanchScheduled + atPanchDone,
        //
        locationsFinalized,
        emailSent: vpOnly.filter(vp => resolveStageNumber(vp) >= 7).length,
        nocReceived: vpOnly.filter(vp => resolveStageNumber(vp) >= 9).length,
        agreementSent: vpOnly.filter(vp => resolveStageNumber(vp) >= 10).length,
        agreementSigned: vpOnly.filter(vp => resolveStageNumber(vp) >= 11).length,
        devicesInstalled
    });

    // Render machine install status from DRS-Tracker data
    renderMachineInstalls();

    // Render BDO section within Progress
    renderBDOInProgress();

    // Setup stage filter for block progress
    setupBlockStageFilter();

    // Gamified Block-wise progress
    renderBlockProgress();

    // Render ULB pipeline
    renderULBFunnel();
}

/**
 * Render holistic funnel — single horizontal pipeline with overlay sub-labels
 * on key blocks to show the panch/direct split without a separate branch section.
 */
function renderHolisticFunnel(stats) {
    const funnelContainer = document.getElementById('holistic-funnel');
    if (!funnelContainer) return;

    // Panch branch stats (stages 4+5)
    const inPanch = stats.atPanchScheduled + stats.atPanchDone;
    // VPs in panch pipeline — track codes to avoid double-counting with F/U
    const vpOnly = vpData.filter(vp => !isULB(vp));
    const vpCodesInPanch = new Set(
        vpOnly.filter(vp => resolveStageNumber(vp) === 4 || resolveStageNumber(vp) === 5)
              .map(vp => vp.vpCode)
    );

    // Follow-up coverage: VPs at stage 3 (not in panch) with a FUTURE follow-up
    const todayStr = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
    const vpsAtStage3 = vpOnly.filter(vp =>
        resolveStageNumber(vp) === 3 && !vpCodesInPanch.has(vp.vpCode)
    );
    const vpCodesAtStage3 = new Set(vpsAtStage3.map(vp => vp.vpCode));
    let followUpCount = 0;
    vpCodesAtStage3.forEach(vpCode => {
        const hasUpcomingFollowUp = meetingsData.some(m =>
            m.vpCode === vpCode &&
            m.status === 'scheduled' &&
            m.eventDate >= todayStr // only today or future
        );
        if (hasUpcomingFollowUp) followUpCount++;
    });

    // Build 1st Meeting sub-label
    const meetingSubs = [];
    if (inPanch > 0) meetingSubs.push(`${inPanch} Panch sched`);
    meetingSubs.push(`${followUpCount} F/U sched`);
    const meetingSub = meetingSubs.join(' · ');

    // For Location OK breakdown: try to infer how many came via panch
    const vpCodesAt6Plus = new Set(
        vpOnly.filter(vp => resolveStageNumber(vp) >= 6).map(vp => vp.vpCode)
    );
    let viaPanchCount = 0;
    vpCodesAt6Plus.forEach(vpCode => {
        const hasPanchEvidence = meetingsData.some(m =>
            m.vpCode === vpCode &&
            m.notes && m.notes.toLowerCase().includes('panch')
        );
        if (hasPanchEvidence) viaPanchCount++;
    });
    const viaDirectCount = stats.locationsFinalized - viaPanchCount;

    // Build Location OK sub-label
    let locationSub = '';
    if (stats.locationsFinalized > 0) {
        if (viaPanchCount > 0) {
            locationSub = `Direct: ${viaDirectCount} · Panch: ${viaPanchCount}`;
        } else {
            locationSub = inPanch > 0 ? `${inPanch} still in Panch` : '';
        }
    }

    const row1 = [
        { label: 'Blocks', value: stats.totalBlocks, icon: '🏛️', cls: 'step-blocks' },
        { label: 'Blocks Unlocked', value: stats.blocksUnlocked, icon: '🔓', cls: 'step-unlocked' },
        { label: 'VPs Accessible', value: stats.vpsUnlocked, icon: '📍', cls: 'step-vps' },
        { label: 'Contacted', value: stats.contacted, icon: '📞', cls: 'step-contacted' },
        { label: '1st Meeting', value: stats.meetingsDone, icon: '🤝', cls: 'step-meetings',
          sub: meetingSub },
    ];

    const row2 = [
        { label: 'Location OK', value: stats.locationsFinalized, icon: '📍', cls: 'step-location',
          sub: locationSub },
        { label: 'Email Sent', value: stats.emailSent, icon: '📧', cls: 'step-email' },
        { label: 'NOC Received', value: stats.nocReceived, icon: '📄', cls: 'step-noc' },
        { label: 'Agr Sent', value: stats.agreementSent, icon: '📨', cls: 'step-agrsent' },
        { label: 'Agr Signed', value: stats.agreementSigned, icon: '✍️', cls: 'step-agreement' },
        { label: 'Installed', value: stats.devicesInstalled, icon: '✅', cls: 'step-installed' },
    ];

    const renderStep = (step, total) => {
        // Calculate fill percentage relative to total blocks
        const maxVal = stats.totalBlocks || 1;
        const pct = Math.round((step.value / maxVal) * 100);
        return `
        <div class="funnel-step ${step.cls}">
            <div class="funnel-step-icon">${step.icon}</div>
            <div class="funnel-step-value">${step.value}</div>
            <div class="funnel-step-label">${step.label}</div>
            ${step.sub ? `<div class="funnel-step-sub">${step.sub}</div>` : ''}
            <div class="funnel-step-bar"><div class="funnel-step-bar-fill" style="width: ${pct}%"></div></div>
        </div>`;
    };

    const renderChevron = () => `<div class="funnel-chevron"><svg width="16" height="24" viewBox="0 0 16 24"><path d="M2 2 L12 12 L2 22" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>`;

    const renderRow = (steps) =>
        steps.map((step, i) => renderStep(step) + (i < steps.length - 1 ? renderChevron() : '')).join('');

    funnelContainer.innerHTML = `
        <div class="funnel-flow">${renderRow(row1)}</div>
        <div class="funnel-row-connector">
            <svg width="24" height="20" viewBox="0 0 24 20"><path d="M12 2 L12 18 M8 14 L12 18 L16 14" stroke="var(--gray-400)" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="funnel-flow">${renderRow(row2)}</div>
    `;
}

/**
 * Render ULB deployment pipeline funnel
 */
function renderULBFunnel() {
    const funnelContainer = document.getElementById('ulb-funnel');
    if (!funnelContainer) return;

    const ulbData = vpData.filter(vp => isULB(vp));
    const total = ulbData.length;

    if (total === 0) {
        funnelContainer.innerHTML = '<div class="master-empty"><p>No ULB data</p></div>';
        return;
    }

    const contacted = ulbData.filter(vp => resolveStageNumber(vp) >= 2).length;
    const meetingsDone = ulbData.filter(vp => resolveStageNumber(vp) >= 3).length;
    const locationsFinalized = ulbData.filter(vp => resolveStageNumber(vp) >= 6).length;
    const emailSent = ulbData.filter(vp => resolveStageNumber(vp) >= 7).length;
    const nocReceived = ulbData.filter(vp => resolveStageNumber(vp) >= 9).length;
    const agreementSigned = ulbData.filter(vp => resolveStageNumber(vp) >= 11).length;
    const installed = ulbData.filter(vp => resolveStageNumber(vp) >= 15).length;

    const steps = [
        { label: 'Total ULBs', value: total, icon: '🏢', cls: 'step-blocks' },
        { label: 'Contacted', value: contacted, icon: '📞', cls: 'step-contacted' },
        { label: '1st Meeting', value: meetingsDone, icon: '🤝', cls: 'step-meetings' },
        { label: 'Location OK', value: locationsFinalized, icon: '📍', cls: 'step-location' },
        { label: 'Email Sent', value: emailSent, icon: '📧', cls: 'step-email' },
        { label: 'NOC Received', value: nocReceived, icon: '📄', cls: 'step-noc' },
        { label: 'Agreement', value: agreementSigned, icon: '✍️', cls: 'step-agreement' },
        { label: 'Installed', value: installed, icon: '✅', cls: 'step-installed' },
    ];

    const renderStep = (step) => `
        <div class="funnel-step ${step.cls}">
            <div class="funnel-step-icon">${step.icon}</div>
            <div class="funnel-step-value">${step.value}</div>
            <div class="funnel-step-label">${step.label}</div>
        </div>`;

    const renderArrow = () => `<div class="funnel-arrow">→</div>`;

    funnelContainer.innerHTML = `
        <div class="funnel-flow">${steps.map((step, i) => renderStep(step) + (i < steps.length - 1 ? renderArrow() : '')).join('')}</div>
    `;
}

/**
 * Render Machine Installation Status section in the Progress dashboard.
 * Data source: vpData (DRS-Tracker) — installDate, machineLive, agreedRvms, stage fields.
 */
function renderMachineInstalls() {
    const el = document.getElementById('machine-install-section');
    if (!el) return;

    const vpOnly = vpData.filter(vp => !isULB(vp));
    const infraDone   = vpOnly.filter(vp => resolveStageNumber(vp) >= 13);
    const deployed    = vpOnly.filter(vp => resolveStageNumber(vp) >= 14);
    const installed   = vpOnly.filter(vp => resolveStageNumber(vp) >= 15 || (vp.installDate && vp.installDate.trim()));
    const withDate    = vpOnly.filter(vp => vp.installDate && vp.installDate.trim()).sort((a, b) => b.installDate.localeCompare(a.installDate));

    // Machine counts (sum agreedRvms, default 1 per VP)
    const machinesDeployed  = deployed.reduce((s, vp) => s + (vp.agreedRvms || 1), 0);
    const machinesInstalled = installed.reduce((s, vp) => s + (vp.agreedRvms || 1), 0);
    const totalPlan = vpOnly.reduce((s, vp) => s + (vp.plannedRvms || 1), 0);

    // Block-wise breakdown (only blocks with at least one infra/deploy entry)
    const blocks = [...new Set(deployed.map(vp => vp.block))].sort();
    const blockRows = blocks.map(block => {
        const d = deployed.filter(vp => vp.block === block).length;
        const ins = installed.filter(vp => vp.block === block).length;
        const inf = infraDone.filter(vp => vp.block === block).length;
        return `<tr>
            <td style="font-weight:600">${block}</td>
            <td>${inf}</td>
            <td>${d}</td>
            <td style="color:#0b6b4f;font-weight:600">${ins}</td>
        </tr>`;
    }).join('');

    // Recent installs list (VPs with installDate set)
    const recentRows = withDate.slice(0, 10).map(vp => {
        const live = vp.machineLive === 'Yes' || vp.machineLive === 'Done'
            ? '<span style="color:#0b6b4f;font-size:11px">Live</span>'
            : '<span style="color:#a0aaba;font-size:11px">Pending</span>';
        return `<tr>
            <td style="color:var(--muted);font-size:12px">${vp.installDate}</td>
            <td><b>${vp.vpName || vp.vpCode}</b></td>
            <td style="color:var(--muted)">${vp.block}</td>
            <td>${live}</td>
        </tr>`;
    }).join('');

    el.innerHTML = `
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
            <div class="dep-kpi" style="flex:1;min-width:120px;border-left:4px solid #8b6914">
                <div class="dep-kv">${infraDone.length}</div>
                <div class="dep-kl">Infra Ready</div>
                <div class="dep-kn" style="font-size:11px;color:var(--muted)">VPs at infra complete</div>
            </div>
            <div class="dep-kpi" style="flex:1;min-width:120px;border-left:4px solid #2f6fb0">
                <div class="dep-kv">${deployed.length}</div>
                <div class="dep-kl">Device Deployed</div>
                <div class="dep-kn" style="font-size:11px;color:var(--muted)">${machinesDeployed} machines</div>
            </div>
            <div class="dep-kpi" style="flex:1;min-width:120px;border-left:4px solid #0b6b4f">
                <div class="dep-kv">${installed.length}</div>
                <div class="dep-kl">Installed</div>
                <div class="dep-kn" style="font-size:11px;color:var(--muted)">${machinesInstalled} of ${totalPlan} machines</div>
            </div>
        </div>
        ${blocks.length > 0 ? `
        <div style="overflow-x:auto;margin-bottom:16px">
            <table class="cp-table" style="font-size:13px;width:100%">
                <thead><tr>
                    <th>Block</th>
                    <th>Infra Ready</th>
                    <th>Deployed</th>
                    <th>Installed</th>
                </tr></thead>
                <tbody>${blockRows}</tbody>
            </table>
        </div>` : '<div style="color:var(--muted);font-size:13px;padding:8px 0">No deployment data yet</div>'}
        ${withDate.length > 0 ? `
        <div style="font-size:13px;font-weight:600;margin-bottom:6px;color:var(--text)">Recent Installs</div>
        <div style="overflow-x:auto">
            <table class="cp-table" style="font-size:13px;width:100%">
                <thead><tr>
                    <th>Install Date</th><th>Location</th><th>Block</th><th>Machine Live</th>
                </tr></thead>
                <tbody>${recentRows}</tbody>
            </table>
        </div>` : ''}
    `;
}

/**
 * Render BDO progress section within Dashboard Progress tab
 */
function renderBDOInProgress() {
    const statsContainer = document.getElementById('bdo-stats-inline');
    const gridContainer = document.getElementById('bdo-grid-inline');

    if (!statsContainer || !gridContainer) return;

    // Calculate BDO stats
    const total = bdoData.length;
    const meetingsDone = bdoData.filter(b =>
        ['meeting_done', 'communication_sent'].includes(b.currentStage)
    ).length;
    const communicationsSent = bdoData.filter(b =>
        b.currentStage === 'communication_sent'
    ).length;

    // Render compact stats
    statsContainer.innerHTML = `
        <div class="bdo-stat-inline">
            <span class="bdo-stat-value">${total}</span>
            <span class="bdo-stat-label">Total</span>
        </div>
        <div class="bdo-stat-inline highlight">
            <span class="bdo-stat-value">${meetingsDone}</span>
            <span class="bdo-stat-label">Meetings Done</span>
        </div>
        <div class="bdo-stat-inline success">
            <span class="bdo-stat-value">${communicationsSent}</span>
            <span class="bdo-stat-label">Comms Sent</span>
        </div>
    `;

    // Render compact BDO cards
    gridContainer.innerHTML = bdoData.map(bdo => {
        const stage = BDO_STAGES.find(s => s.value === bdo.currentStage) || BDO_STAGES[0];
        const stageClass = bdo.currentStage || 'yet_to_meet';
        return `
            <div class="bdo-card-compact bdo-${stageClass}" onclick="openBDOModal('${bdo.block}')">
                <div class="bdo-card-block">${bdo.block}</div>
                <div class="bdo-card-stage ${stageClass}">${stage.number}. ${stage.label}</div>
            </div>
        `;
    }).join('') || '<div class="bdo-empty">No BDO data. Initialize first.</div>';
}

/**
 * Setup stage filter for block progress
 */
function setupBlockStageFilter() {
    const filterSelect = document.getElementById('block-stage-filter');
    if (!filterSelect) return;

    // Populate stage options
    filterSelect.innerHTML = '<option value="">All Stages</option>' +
        STAGES.map(s => `<option value="${s.value}">${s.number}. ${s.label}</option>`).join('');

    // Add change listener
    filterSelect.onchange = () => renderBlockProgress();
}

/**
 * Render block-wise VP progress with optional stage filter
 */
function renderBlockProgress() {
    const filterValue = document.getElementById('block-stage-filter')?.value || '';

    // Filter VP data if a stage is selected
    const vpOnly = vpData.filter(vp => !isULB(vp));
    const filteredVpData = filterValue
        ? vpOnly.filter(vp => vp.currentStage === filterValue)
        : vpOnly;

    // Calculate block stats
    const blockStats = {};
    vpOnly.forEach(vp => {
        if (!blockStats[vp.block]) {
            blockStats[vp.block] = { total: 0, done: 0, filtered: 0 };
        }
        blockStats[vp.block].total++;
        if (resolveStageNumber(vp) >= 3) blockStats[vp.block].done++;
    });

    // Count filtered items per block
    if (filterValue) {
        filteredVpData.forEach(vp => {
            if (blockStats[vp.block]) {
                blockStats[vp.block].filtered++;
            }
        });
    }

    // Sort by percentage and assign ranks
    const sortedBlocks = Object.entries(blockStats)
        .map(([block, stats]) => ({
            block,
            ...stats,
            percent: stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0
        }))
        .sort((a, b) => b.percent - a.percent || b.done - a.done);

    const blockProgressContainer = document.getElementById('block-progress');
    if (!blockProgressContainer) return;

    blockProgressContainer.innerHTML = sortedBlocks.map((stats, index) => {
        const progressClass = getProgressClass(stats.percent);
        const badge = getBadge(stats.percent);
        const rankClass = index < 3 ? `rank-${index + 1}` : '';
        const rankBadge = index < 3 ? `<span class="block-rank">${index === 0 ? '🥇' : index === 1 ? '🥈' : '🥉'}</span>` : '';
        const filterCount = filterValue ? `<span class="filter-count">${stats.filtered} at stage</span>` : '';

        return `
            <div class="block-card ${progressClass} ${rankClass}" onclick="openBlockModal('${stats.block}')" data-block="${stats.block}">
                ${rankBadge}
                <div class="block-card-header">
                    <span class="block-name">${stats.block}</span>
                    <span class="block-badge">${badge}</span>
                </div>
                <div class="block-stats">
                    <span class="block-count">${stats.done}/${stats.total}</span>
                    <span class="block-percent">${stats.percent}%</span>
                </div>
                ${filterCount}
                <div class="block-progress-bar">
                    <div class="block-progress-fill" style="width: ${stats.percent}%"></div>
                </div>
            </div>
        `;
    }).join('');
}

// Block Modal Functions
let currentModalBlock = null;

function openBlockModal(blockName) {
    currentModalBlock = blockName;
    const blockVps = vpData.filter(vp => vp.block === blockName);

    // Calculate stats
    const total = blockVps.length;
    const done = blockVps.filter(vp => resolveStageNumber(vp) >= 3).length;
    const percent = total > 0 ? Math.round((done / total) * 100) : 0;
    const badge = getBadge(percent);

    // Update modal header and stats
    document.getElementById('modal-block-name').textContent = blockName;
    document.getElementById('modal-block-badge').textContent = badge;
    document.getElementById('modal-total').textContent = total;
    document.getElementById('modal-done').textContent = done;
    document.getElementById('modal-percent').textContent = percent + '%';

    // Render VP list
    renderModalVpList(blockVps);

    // Setup search
    const searchInput = document.getElementById('modal-search');
    searchInput.value = '';
    searchInput.oninput = () => {
        const query = searchInput.value.toLowerCase();
        const filtered = blockVps.filter(vp =>
            vp.vpName.toLowerCase().includes(query) ||
            vp.currentStage.toLowerCase().includes(query)
        );
        renderModalVpList(filtered);
    };

    // Show modal
    document.getElementById('block-modal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function renderModalVpList(vps) {
    // Sort by stage number (descending - most progress first)
    const sorted = [...vps].sort((a, b) => resolveStageNumber(b) - resolveStageNumber(a));

    document.getElementById('modal-vp-list').innerHTML = sorted.map(vp => {
        const sn = resolveStageNumber(vp);
        const stageClass = getStageColorClass(sn);
        const stageLabel = getStageLabel(vp.currentStage);

        return `
            <div class="vp-modal-item" onclick="selectVpFromModal('${vp.vpCode}')">
                <span class="vp-stage-dot ${stageClass}"></span>
                <div class="vp-modal-info">
                    <div class="vp-modal-name">${vp.vpName}</div>
                    <div class="vp-modal-stage">${sn}. ${stageLabel}</div>
                </div>
                <span class="vp-modal-arrow">›</span>
            </div>
        `;
    }).join('') || '<div style="text-align: center; color: var(--gray-500); padding: 20px;">No VPs found</div>';
}

function getStageColorClass(stageNumber) {
    // Updated for 15-stage model
    if (stageNumber >= 13) return 'stage-complete';  // infra_complete and above
    if (stageNumber >= 6) return 'stage-high';       // location_finalized and above
    if (stageNumber >= 3) return 'stage-medium';     // first_meeting_done and above
    return 'stage-low';
}

function closeBlockModal() {
    document.getElementById('block-modal').classList.add('hidden');
    document.body.style.overflow = '';
    currentModalBlock = null;
}

function selectVpFromModal(vpCode) {
    closeBlockModal();

    const vp = vpData.find(v => v.vpCode === vpCode);
    if (vp) {
        // Switch to VPs tab
        document.querySelector('.nav-item[data-tab="vps"]').click();

        // Select in master list
        selectVPFromMaster(vpCode);
    }
}

// Close modal when clicking overlay
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        closeBlockModal();
    }
});

// Close modal with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeBlockModal();
    }
});

// Make functions globally accessible
window.openBlockModal = openBlockModal;
window.closeBlockModal = closeBlockModal;
window.selectVpFromModal = selectVpFromModal;

function getProgressClass(percent) {
    if (percent === 0) return 'progress-0';
    if (percent >= 100) return 'progress-complete';
    if (percent >= 60) return 'progress-high';
    if (percent >= 30) return 'progress-medium';
    return 'progress-low';
}

function getBadge(percent) {
    if (percent >= 100) return '🏆';
    if (percent >= 75) return '🔥';
    if (percent >= 50) return '💪';
    if (percent >= 25) return '🚀';
    if (percent > 0) return '✨';
    return '💤';
}

function loadRvmDashboard() {
    // Calculate RVM stats
    let totalPlanned = 0;
    let totalAgreed = 0;
    const blockRvmStats = {};

    vpData.forEach(vp => {
        const planned = vp.plannedRvms || 1;
        const agreed = vp.agreedRvms || 0;

        totalPlanned += planned;
        totalAgreed += agreed;

        if (!blockRvmStats[vp.block]) {
            blockRvmStats[vp.block] = { planned: 0, agreed: 0 };
        }
        blockRvmStats[vp.block].planned += planned;
        blockRvmStats[vp.block].agreed += agreed;
    });

    const conversionRate = totalPlanned > 0 ? Math.round((totalAgreed / totalPlanned) * 100) : 0;
    const pending = totalPlanned - totalAgreed;

    // Update summary stats
    document.getElementById('total-planned').textContent = totalPlanned;
    document.getElementById('total-agreed').textContent = totalAgreed;
    document.getElementById('rvm-conversion').textContent = conversionRate + '%';
    document.getElementById('rvm-pending').textContent = pending;

    // Block-wise RVM bars
    const maxPlanned = Math.max(...Object.values(blockRvmStats).map(s => s.planned), 1);

    const rvmBlockHtml = Object.entries(blockRvmStats)
        .sort((a, b) => b[1].agreed - a[1].agreed)
        .map(([block, stats]) => {
            const plannedWidth = (stats.planned / maxPlanned) * 100;
            const agreedWidth = stats.planned > 0 ? (stats.agreed / stats.planned) * plannedWidth : 0;

            return `
                <div class="rvm-block-item">
                    <div class="rvm-block-header">
                        <span class="rvm-block-name">${block}</span>
                        <span class="rvm-block-nums">${stats.agreed}/${stats.planned} RVMs</span>
                    </div>
                    <div class="rvm-bar-container">
                        <div class="rvm-bar-planned" style="width: ${plannedWidth}%"></div>
                        <div class="rvm-bar-agreed" style="width: ${agreedWidth}%">${stats.agreed > 0 ? stats.agreed : ''}</div>
                    </div>
                </div>
            `;
        }).join('');

    document.getElementById('rvm-block-chart').innerHTML = rvmBlockHtml;

    // Machine deployment map — uses VP/ULB GPS data
    loadLeaflet(() => initRvmDeployMap());
}

function initRvmDeployMap() {
    const container = document.getElementById('rvm-deploy-map');
    if (!container || !window.L) return;
    if (rvmDeployMapInstance) { rvmDeployMapInstance.remove(); rvmDeployMapInstance = null; }
    container.innerHTML = '<div id="rvm-leaflet-map" style="width:100%;height:360px;border-radius:8px"></div>';

    const map = L.map('rvm-leaflet-map', { zoomControl: true, zoomSnap: 0.5 });
    rvmDeployMapInstance = map;
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OSM &copy; CARTO', maxZoom: 19
    }).addTo(map);

    const bounds = [];
    vpData.forEach(vp => {
        const stage = vp.stageNumber || 0;
        if (stage < 14) return;
        const locations = Array.isArray(vp.rvmLocations) ? vp.rvmLocations : [];
        locations.forEach(loc => {
            if (!loc || !loc.lat || !loc.lng || isNaN(+loc.lat) || isNaN(+loc.lng)) return;
            const isInstalled = stage >= 15;
            const color = isInstalled ? '#22c55e' : '#3b82f6';
            const label = isInstalled ? 'Machine Installed' : 'Machine Deployed';
            const marker = L.circleMarker([+loc.lat, +loc.lng], {
                radius: 9, color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.9
            }).addTo(map);
            marker.bindPopup(`<div style="min-width:180px;font-size:13px;line-height:1.8">
                <div style="font-size:15px;font-weight:700;margin-bottom:2px">${vp.name || vp.vpName || '—'}</div>
                <div style="color:#888;font-size:12px;margin-bottom:6px">${vp.block || ''}</div>
                <div style="padding:4px 8px;border-radius:5px;background:${color}18;color:${color};font-weight:600;font-size:12px">${label}</div>
            </div>`, { maxWidth: 240 });
            bounds.push([+loc.lat, +loc.lng]);
        });
    });

    if (bounds.length) {
        map.fitBounds(bounds, { padding: [30, 30] });
    } else {
        map.setView([15.2993, 74.1240], 10);
    }
}

function loadCostDashboard() {
    // Count cost distributions
    const costStats = {
        electricity: { VP: 0, Recykal: 0, Shared: 0, Unknown: 0 },
        internet: { VP: 0, Recykal: 0, Shared: 0, Unknown: 0 },
        handler: { VP: 0, Recykal: 0, Unknown: 0 },
        space: { Free: 0, Rental: 0, Unknown: 0 }
    };

    vpData.forEach(vp => {
        // Electricity
        if (vp.electricityBearer === 'VP') costStats.electricity.VP++;
        else if (vp.electricityBearer === 'Recykal') costStats.electricity.Recykal++;
        else if (vp.electricityBearer === 'Shared') costStats.electricity.Shared++;
        else costStats.electricity.Unknown++;

        // Internet
        if (vp.internetBearer === 'VP') costStats.internet.VP++;
        else if (vp.internetBearer === 'Recykal') costStats.internet.Recykal++;
        else if (vp.internetBearer === 'Shared') costStats.internet.Shared++;
        else costStats.internet.Unknown++;

        // Handler
        if (vp.handlerHiredBy === 'VP') costStats.handler.VP++;
        else if (vp.handlerHiredBy === 'Recykal') costStats.handler.Recykal++;
        else costStats.handler.Unknown++;

        // Space
        if (vp.spaceType === 'Free') costStats.space.Free++;
        else if (vp.spaceType === 'Rental') costStats.space.Rental++;
        else costStats.space.Unknown++;
    });

    const total = vpData.length || 1;

    // Render cost breakdowns
    document.getElementById('cost-electricity').innerHTML = renderCostBreakdown(costStats.electricity, total, ['VP', 'Recykal', 'Shared']);
    document.getElementById('cost-internet').innerHTML = renderCostBreakdown(costStats.internet, total, ['VP', 'Recykal', 'Shared']);
    document.getElementById('cost-handler').innerHTML = renderCostBreakdown(costStats.handler, total, ['VP', 'Recykal']);
    document.getElementById('cost-space').innerHTML = renderCostBreakdown(costStats.space, total, ['Free', 'Rental']);

    // Cost summary
    const vpBearsCost = costStats.electricity.VP + costStats.internet.VP;
    const recykalBearsCost = costStats.electricity.Recykal + costStats.internet.Recykal;
    const freeSpace = costStats.space.Free;
    const vpHandlers = costStats.handler.VP;

    document.getElementById('cost-summary').innerHTML = `
        <div class="cost-summary-item">
            <span class="cost-summary-value">${vpBearsCost}</span>
            <span class="cost-summary-label">VP Bears Cost</span>
        </div>
        <div class="cost-summary-item">
            <span class="cost-summary-value">${recykalBearsCost}</span>
            <span class="cost-summary-label">Recykal Bears Cost</span>
        </div>
        <div class="cost-summary-item">
            <span class="cost-summary-value">${freeSpace}</span>
            <span class="cost-summary-label">Free Space</span>
        </div>
        <div class="cost-summary-item">
            <span class="cost-summary-value">${vpHandlers}</span>
            <span class="cost-summary-label">VP Hires Handler</span>
        </div>
    `;
}

function renderCostBreakdown(stats, total, keys) {
    const colorMap = {
        'VP': 'vp',
        'Recykal': 'recykal',
        'Shared': 'shared',
        'Free': 'free',
        'Rental': 'rental',
        'Unknown': 'unknown'
    };

    return keys.map(key => {
        const count = stats[key] || 0;
        const percent = Math.round((count / total) * 100);
        return `
            <div class="cost-item">
                <span class="cost-dot ${colorMap[key]}"></span>
                <span class="cost-label">${key}</span>
                <span class="cost-value">${count} (${percent}%)</span>
            </div>
        `;
    }).join('') + `
        <div class="cost-item" style="opacity: 0.5;">
            <span class="cost-dot unknown"></span>
            <span class="cost-label">Not Set</span>
            <span class="cost-value">${stats.Unknown || 0}</span>
        </div>
    `;
}

function renderVPList() {
    const searchTerm = elements.searchInput.value.toLowerCase();
    const filterStage = elements.filterStage.value;

    const filtered = vpData.filter(vp => {
        const matchesSearch = !searchTerm ||
            vp.vpName.toLowerCase().includes(searchTerm) ||
            vp.block.toLowerCase().includes(searchTerm);
        const matchesStage = !filterStage || vp.currentStage === filterStage;
        return matchesSearch && matchesStage;
    });

    elements.vpList.innerHTML = filtered.slice(0, 50).map(vp => `
        <div class="vp-list-item" onclick="selectVPFromList('${vp.vpCode}')">
            <div class="vp-info">
                <div class="vp-name">${vp.vpName}</div>
                <div class="vp-block">${vp.block}</div>
            </div>
            <span class="stage-badge ${vp.currentStage}">${getStageLabel(vp.currentStage)}</span>
        </div>
    `).join('') || '<div class="card">No VPs found</div>';
}

function selectVPFromList(vpCode) {
    const vp = vpData.find(v => v.vpCode === vpCode);
    if (vp) {
        // Switch to VPs tab
        document.querySelector('.nav-item[data-tab="vps"]').click();

        // Select in master list
        selectVPFromMaster(vpCode);
    }
}

function showToast(message, type = 'info') {
    elements.toastMessage.textContent = message;
    elements.toast.className = 'toast ' + type;
    elements.toast.classList.remove('hidden');

    setTimeout(() => {
        elements.toast.classList.add('hidden');
    }, 3000);
}

function showLoading(show) {
    if (show) {
        elements.loading.classList.remove('hidden');
    } else {
        elements.loading.classList.add('hidden');
    }
}

// ==================== RVM LOCATIONS & GPS ====================

function updateRvmLocationsUI() {
    // Always show RVM locations section (no longer tied to agreed RVMs count)
    if (!elements.rvmLocationsList) return;

    if (rvmLocations.length === 0) {
        elements.rvmLocationsList.innerHTML = '<div class="no-locations">No locations captured yet. Click "Add Location" to start.</div>';
        return;
    }

    // Render location inputs
    elements.rvmLocationsList.innerHTML = rvmLocations.map((loc, index) => {
        const hasCoords = loc.lat && loc.lng;
        const coordsText = hasCoords
            ? `${loc.lat.toFixed(6)}, ${loc.lng.toFixed(6)}`
            : 'Not captured';
        const coordsClass = hasCoords ? 'location-coords' : 'location-coords empty';

        return `
            <div class="location-item">
                <span class="location-number">${index + 1}</span>
                <span class="${coordsClass}">${coordsText}</span>
                <button type="button" class="btn-capture" onclick="captureLocationFor(${index})">
                    ${hasCoords ? 'Update' : 'Capture'}
                </button>
                <button type="button" class="btn-clear" onclick="removeLocation(${index})">Remove</button>
            </div>
        `;
    }).join('');
}

function addNewLocation() {
    // Add a new empty location slot
    rvmLocations.push({ lat: null, lng: null });
    updateRvmLocationsUI();
    // Automatically capture GPS for the new slot
    captureLocationFor(rvmLocations.length - 1);
}

function captureCurrentLocation() {
    // Find first empty slot or add a new one
    const emptyIndex = rvmLocations.findIndex(loc => !loc.lat || !loc.lng);
    if (emptyIndex >= 0) {
        captureLocationFor(emptyIndex);
    } else {
        // No empty slots, add a new one and capture
        addNewLocation();
    }
}

function removeLocation(index) {
    rvmLocations.splice(index, 1);
    updateRvmLocationsUI();
}

function captureLocationFor(index) {
    if (!navigator.geolocation) {
        showToast('GPS not supported in this browser', 'error');
        return;
    }

    showToast('Getting location...', 'info');

    navigator.geolocation.getCurrentPosition(
        (position) => {
            rvmLocations[index] = {
                lat: position.coords.latitude,
                lng: position.coords.longitude,
                accuracy: position.coords.accuracy,
                timestamp: new Date().toISOString()
            };
            updateRvmLocationsUI();
            showToast(`Location ${index + 1} captured!`, 'success');
        },
        (error) => {
            console.error('GPS Error:', error);
            let message = 'Could not get location. ';
            switch (error.code) {
                case error.PERMISSION_DENIED:
                    message += 'Please allow location access.';
                    break;
                case error.POSITION_UNAVAILABLE:
                    message += 'Location unavailable.';
                    break;
                case error.TIMEOUT:
                    message += 'Request timed out.';
                    break;
            }
            showToast(message, 'error');
        },
        {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 0
        }
    );
}

function clearLocation(index) {
    rvmLocations[index] = { lat: null, lng: null };
    updateRvmLocationsUI();
}

// Make functions globally accessible
window.captureLocationFor = captureLocationFor;
window.clearLocation = clearLocation;
window.removeLocation = removeLocation;
window.addNewLocation = addNewLocation;

// ==================== VP PROFILE ====================

async function saveVPProfile() {
    if (!currentVP) {
        showToast('Please select a VP first', 'error');
        return;
    }

    showLoading(true);

    const profileData = {
        vp_code: currentVP.vpCode,
        block: currentVP.block,
        secretary_name: elements.secretaryName?.value || '',
        secretary_phone: elements.secretaryPhone?.value || '',
        sarpanch_name: elements.sarpanchName?.value || '',
        sarpanch_phone: elements.sarpanchPhone?.value || '',
        vp_email: elements.vpEmail?.value || '',
        contractor_name: elements.contractorName?.value || '',
        contractor_phone: elements.contractorPhone?.value || '',
        planned_rvms: parseInt(elements.plannedRvms?.value) || 1,
        agreed_rvms: parseInt(elements.agreedRvms?.value) || 0,
        rvm_locations: rvmLocations.filter(loc => loc.lat && loc.lng),
        // Cost & Operations
        electricity_bearer: elements.electricityBearer?.value || '',
        internet_bearer: elements.internetBearer?.value || '',
        handler_hired_by: elements.handlerHiredBy?.value || '',
        space_type: elements.spaceType?.value || '',
        updated_by: elements.updatedBy?.value || 'Unknown'
    };

    try {
        const response = await fetch(`${API_BASE}/update/profile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profileData)
        }).catch(() => null);

        if (response && response.ok) {
            // Update local data
            const vpIndex = vpData.findIndex(vp => vp.vpCode === currentVP.vpCode);
            if (vpIndex >= 0) {
                vpData[vpIndex] = {
                    ...vpData[vpIndex],
                    secretaryName: profileData.secretary_name,
                    secretaryPhone: profileData.secretary_phone,
                    sarpanchName: profileData.sarpanch_name,
                    sarpanchPhone: profileData.sarpanch_phone,
                    email: profileData.vp_email,
                    contractorName: profileData.contractor_name,
                    contractorPhone: profileData.contractor_phone,
                    plannedRvms: profileData.planned_rvms,
                    agreedRvms: profileData.agreed_rvms,
                    rvmLocations: profileData.rvm_locations,
                    electricityBearer: profileData.electricity_bearer,
                    internetBearer: profileData.internet_bearer,
                    handlerHiredBy: profileData.handler_hired_by,
                    spaceType: profileData.space_type,
                };
                currentVP = vpData[vpIndex];
            }
            showToast('Profile saved successfully!', 'success');
        } else {
            // Save locally for later sync
            saveLocalProfileUpdate(profileData);
            showToast('Profile saved locally. Will sync when online.', 'success');
        }
    } catch (error) {
        console.error('Profile save error:', error);
        saveLocalProfileUpdate(profileData);
        showToast('Profile saved locally. Will sync when online.', 'success');
    }

    showLoading(false);
}

function saveLocalProfileUpdate(profileData) {
    const pendingProfiles = JSON.parse(localStorage.getItem('pendingProfiles') || '[]');
    // Remove existing entry for same VP
    const filtered = pendingProfiles.filter(p => p.vp_code !== profileData.vp_code);
    filtered.push({ ...profileData, timestamp: Date.now() });
    localStorage.setItem('pendingProfiles', JSON.stringify(filtered));
}

// ==================== VOICE RECORDING ====================

function setupVoiceRecording() {
    if (!elements.voiceRecordBtn) return;

    elements.voiceRecordBtn.addEventListener('click', toggleRecording);
    elements.stopRecordingBtn?.addEventListener('click', stopRecording);

    // Check if browser supports audio recording
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        elements.voiceRecordBtn.style.display = 'none';
        console.warn('Voice recording not supported in this browser');
    }
}

async function toggleRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            stream.getTracks().forEach(track => track.stop());
            await processVoiceRecording(audioBlob);
        };

        mediaRecorder.start(100); // Collect data every 100ms
        recordingStartTime = Date.now();

        // Update UI
        elements.voiceRecordBtn.classList.add('recording');
        elements.voiceRecordBtn.querySelector('.record-text').textContent = 'Stop';
        elements.recordingStatus?.classList.remove('hidden');
        elements.voiceLanguage?.classList.remove('hidden');

        // Start timer
        recordingTimer = setInterval(updateRecordingTime, 1000);

        showToast('Recording... Speak now', 'info');

    } catch (error) {
        console.error('Error starting recording:', error);
        showToast('Could not access microphone. Please allow permission.', 'error');
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }

    // Reset UI
    elements.voiceRecordBtn.classList.remove('recording');
    elements.voiceRecordBtn.querySelector('.record-text').textContent = 'Record';
    elements.recordingStatus?.classList.add('hidden');

    // Stop timer
    if (recordingTimer) {
        clearInterval(recordingTimer);
        recordingTimer = null;
    }
    if (elements.recordingTime) {
        elements.recordingTime.textContent = '00:00';
    }
}

function updateRecordingTime() {
    if (!recordingStartTime || !elements.recordingTime) return;

    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const seconds = (elapsed % 60).toString().padStart(2, '0');
    elements.recordingTime.textContent = `${minutes}:${seconds}`;

    // Auto-stop after 2 minutes
    if (elapsed >= 120) {
        stopRecording();
        showToast('Recording stopped (2 min limit)', 'info');
    }
}

async function processVoiceRecording(audioBlob) {
    showLoading(true);
    showToast('Processing voice note...', 'info');

    try {
        const language = elements.voiceLangSelect?.value || 'hi-IN';

        // Create form data for upload
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');
        formData.append('language', language);

        if (currentVP) {
            formData.append('village_panchayat_name', currentVP.vpName);
            formData.append('block_name', currentVP.block);
        }

        // Send to backend for processing
        const response = await fetch(`${API_BASE}/update/voice`, {
            method: 'POST',
            body: formData
        }).catch(() => null);

        if (response && response.ok) {
            const result = await response.json();

            // Update meeting notes with transcription
            if (result.transcript) {
                const existingNotes = elements.meetingNotes.value;
                const newNote = existingNotes
                    ? `${existingNotes}\n\n[Voice] ${result.transcript}`
                    : `[Voice] ${result.transcript}`;
                elements.meetingNotes.value = newNote;
            }

            // Auto-fill extracted data
            if (result.extracted_data) {
                autoFillExtractedData(result.extracted_data);
            }

            showToast('Voice note processed!', 'success');
        } else {
            // Fallback: Use Web Speech API for local transcription
            await localTranscription(audioBlob);
        }

    } catch (error) {
        console.error('Voice processing error:', error);
        showToast('Could not process voice note. Try typing instead.', 'error');
    }

    showLoading(false);
}

async function localTranscription(audioBlob) {
    // Fallback using browser's Web Speech API (if available)
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        showToast('Voice processing requires server connection', 'error');
        return;
    }

    showToast('Local transcription not fully supported. Please type your notes.', 'info');
}

function autoFillExtractedData(data) {
    // Auto-suggest stage based on AI extraction
    if (data.suggested_stage && elements.newStage) {
        elements.newStage.value = data.suggested_stage;
        showToast(`Suggested stage: ${getStageLabel(data.suggested_stage)}`, 'info');
    }
}

// Initialize voice recording on page load
document.addEventListener('DOMContentLoaded', () => {
    setupVoiceRecording();
});

// Make selectVPFromList available globally
window.selectVPFromList = selectVPFromList;

// ==================== BDO TRACKER ====================

async function loadBDOData() {
    showLoading(true);
    try {
        const response = await fetch(`${API_BASE}/bdo/all`).catch(() => null);
        if (response && response.ok) {
            bdoData = await response.json();
            console.log(`Loaded ${bdoData.length} BDO records`);
        } else {
            // Use cached data
            bdoData = JSON.parse(localStorage.getItem('bdoDataCache') || '[]');
            if (bdoData.length === 0) {
                showToast('BDO data not found. Initialize BDO tracker first.', 'error');
            }
        }
        localStorage.setItem('bdoDataCache', JSON.stringify(bdoData));
    } catch (error) {
        console.error('Error loading BDO data:', error);
        bdoData = JSON.parse(localStorage.getItem('bdoDataCache') || '[]');
    }
    showLoading(false);
}

function renderBDOTracker() {
    // Calculate stats
    const total = bdoData.length;
    const meetingsDone = bdoData.filter(b =>
        ['meeting_done', 'communication_sent'].includes(b.currentStage)
    ).length;
    const communicationsSent = bdoData.filter(b =>
        b.currentStage === 'communication_sent'
    ).length;

    // Render stats
    document.getElementById('bdo-stats').innerHTML = `
        <div class="stat-card">
            <div class="stat-value">${total}</div>
            <div class="stat-label">Total Blocks</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${meetingsDone}</div>
            <div class="stat-label">Meetings Done</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${communicationsSent}</div>
            <div class="stat-label">Communications Sent</div>
        </div>
    `;

    // Render BDO cards
    document.getElementById('bdo-list').innerHTML = bdoData.map(bdo => {
        const stage = BDO_STAGES.find(s => s.value === bdo.currentStage) || BDO_STAGES[0];
        const stageClass = bdo.currentStage || 'yet_to_meet';
        return `
            <div class="bdo-card bdo-${stageClass}" onclick="openBDOModal('${bdo.block}')">
                <div class="bdo-block">${bdo.block}</div>
                <div class="bdo-name">${bdo.bdoName || 'Not set'}</div>
                <div class="bdo-phone">${bdo.bdoPhone || '-'}</div>
                <div class="bdo-stage-badge ${stageClass}">${stage.label}</div>
            </div>
        `;
    }).join('') || '<div style="text-align: center; color: var(--gray-500); padding: 20px;">No BDO data found. Click to initialize.</div>';
}

function openBDOModal(block) {
    const bdo = bdoData.find(b => b.block === block);
    if (!bdo) return;

    currentBDOBlock = block;
    document.getElementById('bdo-modal-title').textContent = `Update ${block} BDO`;
    document.getElementById('bdo-modal-name').textContent = bdo.bdoName || 'Not set';
    document.getElementById('bdo-modal-phone').textContent = bdo.bdoPhone || '-';
    document.getElementById('bdo-stage-select').value = bdo.currentStage || 'yet_to_meet';
    document.getElementById('bdo-modal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function closeBDOModal() {
    document.getElementById('bdo-modal').classList.add('hidden');
    document.body.style.overflow = '';
    currentBDOBlock = null;
}

async function submitBDOUpdate() {
    if (!currentBDOBlock) return;

    const newStage = document.getElementById('bdo-stage-select').value;
    showLoading(true);

    try {
        const response = await fetch(`${API_BASE}/bdo/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                block: currentBDOBlock,
                new_stage: newStage
            })
        }).catch(() => null);

        if (response && response.ok) {
            // Update local data
            const idx = bdoData.findIndex(b => b.block === currentBDOBlock);
            if (idx >= 0) {
                bdoData[idx].currentStage = newStage;
                localStorage.setItem('bdoDataCache', JSON.stringify(bdoData));
            }

            renderBDOTracker();
            closeBDOModal();
            showToast('BDO status updated!', 'success');
        } else {
            showToast('Failed to update. Please try again.', 'error');
        }
    } catch (error) {
        console.error('BDO update error:', error);
        showToast('Error updating BDO status', 'error');
    }

    showLoading(false);
}

// Close BDO modal when clicking overlay
document.addEventListener('click', (e) => {
    if (e.target.id === 'bdo-modal') {
        closeBDOModal();
    }
});

// Make BDO functions globally accessible
window.openBDOModal = openBDOModal;
window.closeBDOModal = closeBDOModal;
window.submitBDOUpdate = submitBDOUpdate;

// ==================== Collapsible Sections ====================

/**
 * Toggle collapsible section
 * @param {string} section - 'status', 'meetings', 'history', or 'profile'
 */
function toggleSection(section) {
    const sectionEl = document.getElementById(`${section}-section`);
    if (sectionEl) {
        sectionEl.classList.toggle('collapsed');
    }
}

// Make toggle function globally accessible
window.toggleSection = toggleSection;

// ==================== MEETING MANAGER ====================

/**
 * Load all meetings from backend
 */
async function loadMeetingsData() {
    showLoading(true);
    try {
        const response = await fetch(`${API_BASE}/meetings/all`).catch(() => null);
        if (response && response.ok) {
            meetingsData = await response.json();
            localStorage.setItem('meetingsDataCache', JSON.stringify(meetingsData));
        } else {
            meetingsData = JSON.parse(localStorage.getItem('meetingsDataCache') || '[]');
        }
    } catch (error) {
        console.error('Error loading meetings:', error);
        meetingsData = JSON.parse(localStorage.getItem('meetingsDataCache') || '[]');
    }
    showLoading(false);
}

/**
 * Render the Meetings tab
 */
function renderMeetingsTab() {
    renderMeetingsStats();
    populateMeetingsFilters();
    renderWeekScroller();
    renderDayMeetings();
    renderNeedsScheduling();
}

/**
 * Render meetings statistics
 */
function renderMeetingsStats() {
    const today = new Date().toISOString().split('T')[0];

    // RBAC: filter to user's meetings
    const visibleMeetings = (currentUser && currentUser.role !== 'admin')
        ? meetingsData.filter(m => m.assignedTo === currentUser.name)
        : meetingsData;

    const scheduled = visibleMeetings.filter(m => m.status === 'scheduled').length;
    const upcoming = visibleMeetings.filter(m =>
        m.status === 'scheduled' && m.eventDate >= today
    ).length;
    const completed = visibleMeetings.filter(m => m.status === 'completed').length;

    document.getElementById('meetings-stats').innerHTML = `
        <div class="meetings-stat">
            <span class="meetings-stat-value">${upcoming}</span>
            <span class="meetings-stat-label">Upcoming</span>
        </div>
        <div class="meetings-stat">
            <span class="meetings-stat-value">${scheduled}</span>
            <span class="meetings-stat-label">Scheduled</span>
        </div>
        <div class="meetings-stat">
            <span class="meetings-stat-value">${completed}</span>
            <span class="meetings-stat-label">Completed</span>
        </div>
    `;
}

/**
 * Populate meetings filter dropdowns
 */
function populateMeetingsFilters() {
    const blockSelect = document.getElementById('meetings-filter-block');
    if (blockSelect) {
        const blocks = [...new Set(vpData.map(vp => vp.block))].filter(b => b).sort();
        // Add HoReCa block option
        const allBlocks = [...blocks];
        if (!allBlocks.includes('HoReCa')) allBlocks.push('HoReCa');
        blockSelect.innerHTML = '<option value="">All Blocks</option>' +
            allBlocks.map(b => `<option value="${b}">${b}</option>`).join('');
    }

    // Add filter event listeners
    document.getElementById('meetings-filter-block')?.addEventListener('change', renderDayMeetings);
    document.getElementById('meetings-filter-type')?.addEventListener('change', renderDayMeetings);
    document.getElementById('meetings-filter-status')?.addEventListener('change', renderDayMeetings);
}

/**
 * Get the Monday of a week given offset from current week
 */
function getWeekMonday(weekOffset) {
    const now = new Date();
    const day = now.getDay(); // 0=Sun, 1=Mon...
    const diffToMonday = day === 0 ? -6 : 1 - day;
    const monday = new Date(now);
    monday.setDate(now.getDate() + diffToMonday + (weekOffset * 7));
    monday.setHours(0, 0, 0, 0);
    return monday;
}

/**
 * Format date as YYYY-MM-DD
 */
function toDateStr(date) {
    return date.toISOString().split('T')[0];
}

/**
 * Render horizontal week scroller with day pills
 */
function renderWeekScroller() {
    const monday = getWeekMonday(meetingsWeekOffset);
    const today = toDateStr(new Date());

    // Set default selected date
    if (!meetingsSelectedDate) {
        meetingsSelectedDate = today;
    }

    // Check if selected date is in this week, otherwise select Monday (or today if current week)
    const weekStart = toDateStr(monday);
    const sundayDate = new Date(monday);
    sundayDate.setDate(monday.getDate() + 6);
    const weekEnd = toDateStr(sundayDate);

    if (meetingsSelectedDate < weekStart || meetingsSelectedDate > weekEnd) {
        meetingsSelectedDate = meetingsWeekOffset === 0 ? today : weekStart;
    }

    // Week label
    const weekLabel = document.getElementById('week-label');
    if (weekLabel) {
        if (meetingsWeekOffset === 0) {
            weekLabel.textContent = 'This Week';
        } else if (meetingsWeekOffset === -1) {
            weekLabel.textContent = 'Last Week';
        } else if (meetingsWeekOffset === 1) {
            weekLabel.textContent = 'Next Week';
        } else {
            const endDate = new Date(monday);
            endDate.setDate(monday.getDate() + 6);
            weekLabel.textContent = `${monday.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} - ${endDate.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`;
        }
    }

    // Get visible meetings for dot indicators
    const visibleMeetings = getVisibleMeetings();

    // Count meetings per date
    const meetingsByDate = {};
    visibleMeetings.forEach(m => {
        if (!meetingsByDate[m.eventDate]) meetingsByDate[m.eventDate] = { vp: 0, horeca: 0 };
        if ((m.vpCode || '').startsWith('HORECA:')) {
            meetingsByDate[m.eventDate].horeca++;
        } else {
            meetingsByDate[m.eventDate].vp++;
        }
    });

    // Render 7 day pills
    const scroller = document.getElementById('date-scroller');
    if (!scroller) return;

    const dayAbbrs = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    let pillsHtml = '';

    for (let i = 0; i < 7; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        const dateStr = toDateStr(d);
        const isToday = dateStr === today;
        const isSelected = dateStr === meetingsSelectedDate;
        const counts = meetingsByDate[dateStr] || { vp: 0, horeca: 0 };

        let dotsHtml = '';
        if (counts.vp > 0) dotsHtml += '<span class="day-dot"></span>';
        if (counts.horeca > 0) dotsHtml += '<span class="day-dot horeca"></span>';

        pillsHtml += `
            <div class="date-pill ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''}" onclick="selectDay('${dateStr}')">
                <span class="day-abbr">${dayAbbrs[i]}</span>
                <span class="day-num">${d.getDate()}</span>
                <div class="day-dot-row">${dotsHtml}</div>
            </div>
        `;
    }

    scroller.innerHTML = pillsHtml;
}

/**
 * Navigate to a different week
 */
function navigateWeek(direction) {
    meetingsWeekOffset += direction;
    renderWeekScroller();
    renderDayMeetings();
}

/**
 * Select a specific day
 */
function selectDay(dateStr) {
    meetingsSelectedDate = dateStr;
    renderWeekScroller();
    renderDayMeetings();
}

/**
 * Get meetings visible to current user (RBAC filtered, excluding cancelled)
 */
function getVisibleMeetings() {
    return meetingsData.filter(m => {
        if (m.status === 'cancelled') return false;
        if (currentUser && currentUser.role !== 'admin') {
            if (m.assignedTo !== currentUser.name) return false;
        }
        return true;
    });
}

/**
 * Render meetings for the selected day, grouped by time blocks
 */
function renderDayMeetings() {
    const blockFilter = document.getElementById('meetings-filter-block')?.value || '';
    const typeFilter = document.getElementById('meetings-filter-type')?.value || '';
    const statusFilter = document.getElementById('meetings-filter-status')?.value || '';

    const today = toDateStr(new Date());
    const selectedDate = meetingsSelectedDate || today;

    let filtered = getVisibleMeetings().filter(m => {
        // Date filter: only selected day
        if (m.eventDate !== selectedDate) return false;

        // Block filter
        if (blockFilter && m.block !== blockFilter) return false;

        // Type filter
        if (typeFilter && m.eventType !== typeFilter) return false;

        // Status filter
        if (statusFilter && m.status !== statusFilter) return false;

        return true;
    });

    // Sort by time
    filtered.sort((a, b) => (a.eventTime || '10:00').localeCompare(b.eventTime || '10:00'));

    const listContainer = document.getElementById('meetings-list');
    if (!listContainer) return;

    if (filtered.length === 0) {
        const dateObj = new Date(selectedDate + 'T00:00:00');
        const dateLabel = selectedDate === today ? 'today' :
            dateObj.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' });

        listContainer.innerHTML = `
            <div class="day-empty">
                <svg viewBox="0 0 24 24"><path fill="currentColor" d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V9h14v11zM7 11h5v5H7z"/></svg>
                <p>No meetings ${dateLabel}</p>
                <button class="btn btn-primary btn-small" onclick="openScheduleMeetingModal()">Schedule Meeting</button>
            </div>
        `;
        return;
    }

    // Group by time blocks: Morning (before 12), Afternoon (12-17), Evening (17+)
    const blocks = { morning: [], afternoon: [], evening: [] };
    filtered.forEach(m => {
        const hour = parseInt((m.eventTime || '10:00').split(':')[0]);
        if (hour < 12) blocks.morning.push(m);
        else if (hour < 17) blocks.afternoon.push(m);
        else blocks.evening.push(m);
    });

    let html = '';
    const blockLabels = { morning: 'Morning', afternoon: 'Afternoon', evening: 'Evening' };

    for (const [block, meetings] of Object.entries(blocks)) {
        if (meetings.length === 0) continue;
        html += `
            <div class="time-block">
                <div class="time-block-header">${blockLabels[block]} (${meetings.length})</div>
                <div class="time-block-meetings">
                    ${meetings.map(m => renderMeetingCard(m, today)).join('')}
                </div>
            </div>
        `;
    }

    listContainer.innerHTML = html;
}

/**
 * Render "Needs Scheduling" section for HoReCa with "Meeting aligned" status
 */
async function renderNeedsScheduling() {
    const container = document.getElementById('meetings-needs-scheduling');
    if (!container) return;

    // Only show for admin and horeca roles
    if (currentUser && !['admin', 'horeca'].includes(currentUser.role)) {
        container.classList.add('hidden');
        return;
    }

    try {
        // Fetch HoReCa records with "Meeting aligned" status
        if (!needsSchedulingCache) {
            const response = await fetch(`${API_BASE}/horeca/crm?status=Meeting+aligned&page_size=100`).catch(() => null);
            if (response && response.ok) {
                const data = await response.json();
                needsSchedulingCache = data.records || [];
            } else {
                needsSchedulingCache = [];
            }
        }

        // Cross-reference with meetings: find those without a scheduled meeting
        const scheduledHorecaPlaceIds = new Set(
            meetingsData
                .filter(m => m.status === 'scheduled' && (m.vpCode || '').startsWith('HORECA:'))
                .map(m => (m.vpCode || '').replace('HORECA:', ''))
        );

        const unscheduled = needsSchedulingCache.filter(record => {
            const placeId = record.place_id || record.Place_ID || '';
            return placeId && !scheduledHorecaPlaceIds.has(placeId);
        });

        if (unscheduled.length === 0) {
            container.classList.add('hidden');
            return;
        }

        container.classList.remove('hidden');
        document.getElementById('needs-scheduling-count').textContent = unscheduled.length;

        const listEl = document.getElementById('needs-scheduling-list');
        listEl.innerHTML = unscheduled.map(record => {
            const placeId = record.place_id || record.Place_ID || '';
            const name = record.name || record.Name || 'Unknown';
            const city = record.city || record.City || '';
            const type = record.type || record.Type || '';

            return `
                <div class="needs-scheduling-card">
                    <div class="nsc-name" title="${name}">${name}</div>
                    <div class="nsc-meta">${type}${city ? ' · ' + city : ''}</div>
                    <button class="btn-schedule-nudge" onclick="openHorecaMeetingFromNudge('${placeId}', '${name.replace(/'/g, "\\'")}')">Schedule</button>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading needs scheduling:', error);
        container.classList.add('hidden');
    }
}

/**
 * Open meeting modal pre-filled for a HoReCa from the needs scheduling nudge
 */
function openHorecaMeetingFromNudge(placeId, name) {
    // Use the existing HoReCa meeting scheduling flow
    if (typeof openScheduleMeetingModalForHoreca === 'function') {
        openScheduleMeetingModalForHoreca(placeId, name);
    } else {
        // Fallback: open regular modal and set context to horeca
        openScheduleMeetingModal();
        setTimeout(() => {
            const contextEl = document.getElementById('meeting-context');
            const placeIdEl = document.getElementById('meeting-horeca-place-id');
            const nameEl = document.getElementById('meeting-horeca-name');
            if (contextEl) contextEl.value = 'horeca';
            if (placeIdEl) placeIdEl.value = placeId;
            if (nameEl) nameEl.value = name;

            // Show HoReCa fields, hide VP fields
            document.getElementById('meeting-vp-group')?.classList.add('hidden');
            const horecaGroup = document.getElementById('meeting-horeca-group');
            if (horecaGroup) {
                horecaGroup.classList.remove('hidden');
                const horecaLabel = horecaGroup.querySelector('.horeca-name-display');
                if (horecaLabel) horecaLabel.textContent = name;
            }

            // Switch to HoReCa meeting titles
            const titleSelect = document.getElementById('meeting-title');
            if (titleSelect) {
                titleSelect.innerHTML = `
                    <option value="First Meeting">First Meeting</option>
                    <option value="Follow-up">Follow-up</option>
                    <option value="Onboarding Discussion">Onboarding Discussion</option>
                    <option value="Site Visit">Site Visit</option>
                    <option value="custom">Custom...</option>
                `;
            }
        }, 100);
    }
}

/**
 * Render a single meeting card
 */
function renderMeetingCard(meeting, today) {
    const isPast = meeting.eventDate < today;
    const typeLabel = getEventTypeLabel(meeting.eventType, meeting.eventTitle);
    const titleClass = getMeetingTitleClass(meeting.eventTitle);
    const formattedTime = meeting.eventTime || '10:00';
    const isHoreca = (meeting.vpCode || '').startsWith('HORECA:');
    const sourceBadge = isHoreca
        ? '<span class="source-badge horeca">HoReCa</span>'
        : '<span class="source-badge vp">VP</span>';

    return `
        <div class="meeting-item ${meeting.eventType} ${titleClass} ${isPast ? 'past' : ''} ${meeting.status === 'cancelled' ? 'cancelled' : ''}">
            <div class="meeting-item-header">
                <span class="meeting-time-badge">${formattedTime}</span>
                ${sourceBadge}
                <span class="meeting-vp-name">${meeting.vpName || 'Unknown VP'}</span>
                <span class="meeting-type-badge ${titleClass}">${typeLabel}</span>
            </div>
            <div class="meeting-details">
                <span class="meeting-detail">
                    <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/></svg>
                    ${meeting.block}
                </span>
                ${meeting.assignedTo ? `
                <span class="meeting-detail">
                    <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
                    ${meeting.assignedTo}
                </span>
                ` : ''}
            </div>
            ${meeting.notes ? `<div class="meeting-notes-preview">${meeting.notes.substring(0, 80)}${meeting.notes.length > 80 ? '...' : ''}</div>` : ''}
            ${!isPast ? `
            <div class="meeting-actions">
                <button class="btn btn-secondary btn-small" onclick="editMeeting('${meeting.meetingId}')">Edit</button>
                <button class="btn btn-secondary btn-small" onclick="markMeetingComplete('${meeting.meetingId}')">Done</button>
                <button class="btn btn-secondary btn-small" onclick="deleteMeeting('${meeting.meetingId}')" style="color: var(--danger);">Cancel</button>
            </div>
            ` : ''}
        </div>
    `;
}

/**
 * Toggle meeting date group expansion
 */
function toggleMeetingDateGroup(header) {
    const group = header.closest('.meeting-date-group');
    if (group) {
        group.classList.toggle('expanded');
    }
}

// Expose meeting functions globally
window.toggleMeetingDateGroup = toggleMeetingDateGroup;
window.navigateWeek = navigateWeek;
window.selectDay = selectDay;
window.openHorecaMeetingFromNudge = openHorecaMeetingFromNudge;

/**
 * Get human-readable event type label
 */
function getEventTypeLabel(eventType, eventTitle = '') {
    // If eventTitle is provided, use it
    if (eventTitle) {
        return eventTitle;
    }
    // Fallback to generic labels
    const labels = {
        'calendar_event': 'Meeting',
        'task_reminder': 'Task',
        'milestone': 'Milestone',
    };
    return labels[eventType] || eventType;
}

/**
 * Get CSS class for meeting title color
 */
function getMeetingTitleClass(eventTitle) {
    const titleClasses = {
        'First Meeting': 'title-first-meeting',
        'Panch Meeting': 'title-panch-meeting',
        'Follow-up': 'title-followup',
        'Location Survey': 'title-location-survey',
        'NOC Discussion': 'title-noc-discussion',
        'Agreement Signing': 'title-agreement',
        'Infra Check': 'title-infra-check',
        'Device Installation': 'title-device-install',
    };
    return titleClasses[eventTitle] || 'title-default';
}

/**
 * Format date for display
 */
function formatMeetingDate(dateStr) {
    if (!dateStr) return 'No date';
    const date = new Date(dateStr + 'T00:00:00');
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);

    if (dateStr === today.toISOString().split('T')[0]) return 'Today';
    if (dateStr === tomorrow.toISOString().split('T')[0]) return 'Tomorrow';

    return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

/**
 * Open schedule meeting modal
 */
function openScheduleMeetingModal(prefillVp = null) {
    try {
        currentMeetingId = null;
        document.getElementById('meeting-modal-title').textContent = 'Schedule Meeting';

        // Populate VP dropdown with stage info for duration lookup
        const vpSelect = document.getElementById('meeting-vp-select');
        if (!vpSelect) {
            console.error('meeting-vp-select not found');
            showToast('Error: Modal elements not found', 'error');
            return;
        }

        vpSelect.innerHTML = '<option value="">-- Select VP --</option>' +
            vpData.map(vp => `<option value="${vp.vpCode}" data-block="${vp.block}" data-name="${vp.vpName}" data-stage="${vp.currentStage}">${vp.vpName} (${vp.block})</option>`).join('');

        // Pre-select VP if provided
        if (prefillVp) {
            vpSelect.value = prefillVp.vpCode;
        }

        // Set default date to tomorrow
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        document.getElementById('meeting-date').value = tomorrow.toISOString().split('T')[0];

        // Reset other fields
        document.getElementById('meeting-time').value = '10:00';
        document.getElementById('meeting-event-type').value = 'calendar_event';
        document.getElementById('meeting-assigned').value = '';
        document.getElementById('meeting-notes-input').value = '';

        // Set duration based on VP's current stage
        updateDurationForSelectedVP();

        // Show duration options for calendar events
        toggleMeetingOptions();

        // Reset meeting title to default
        document.getElementById('meeting-title').value = 'First Meeting';
        document.getElementById('meeting-title-custom').classList.add('hidden');
        document.getElementById('meeting-title-custom').value = '';

        // Add event listeners
        document.getElementById('meeting-event-type').onchange = toggleMeetingOptions;
        document.getElementById('meeting-title').onchange = toggleMeetingTitleCustom;
        vpSelect.onchange = updateDurationForSelectedVP;

        document.getElementById('meeting-modal').classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    } catch (error) {
        console.error('Error opening schedule meeting modal:', error);
        showToast('Error opening modal: ' + error.message, 'error');
    }
}

/**
 * Update duration dropdown based on selected VP's current stage
 */
function updateDurationForSelectedVP() {
    const vpSelect = document.getElementById('meeting-vp-select');
    const durationSelect = document.getElementById('meeting-duration');

    const selectedOption = vpSelect.options[vpSelect.selectedIndex];
    const stage = selectedOption?.dataset?.stage || 'yet_to_meet';

    // Get recommended duration from stage mapping
    const duration = STAGE_DURATION_MAP[stage] || 5;

    // Set the duration dropdown
    durationSelect.value = duration.toString();

    // If exact value not in dropdown, find closest
    if (durationSelect.value !== duration.toString()) {
        // Find closest option
        const options = Array.from(durationSelect.options).map(o => parseInt(o.value));
        const closest = options.reduce((prev, curr) =>
            Math.abs(curr - duration) < Math.abs(prev - duration) ? curr : prev
        );
        durationSelect.value = closest.toString();
    }
}

/**
 * Toggle meeting options visibility based on event type
 * - Duration: only for calendar_event
 * - Notifications: for calendar_event and task_reminder (not milestones)
 */
function toggleMeetingOptions() {
    const eventType = document.getElementById('meeting-event-type').value;

    // Duration only for calendar events
    const durationGroup = document.getElementById('meeting-duration-group');
    if (durationGroup) {
        durationGroup.classList.toggle('hidden', eventType !== 'calendar_event');
    }
}

/**
 * Toggle custom title input based on meeting title selection
 */
function toggleMeetingTitleCustom() {
    const titleSelect = document.getElementById('meeting-title');
    const customInput = document.getElementById('meeting-title-custom');

    if (titleSelect.value === 'custom') {
        customInput.classList.remove('hidden');
        customInput.focus();
    } else {
        customInput.classList.add('hidden');
        customInput.value = '';
    }
}

/**
 * Close meeting modal
 */
function closeMeetingModal() {
    document.getElementById('meeting-modal').classList.add('hidden');
    document.body.style.overflow = '';
    currentMeetingId = null;

    // Reset context back to VP
    document.getElementById('meeting-context').value = 'vp';
    document.getElementById('meeting-horeca-place-id').value = '';
    document.getElementById('meeting-vp-group').classList.remove('hidden');
    document.getElementById('meeting-horeca-group').classList.add('hidden');

    // Restore VP meeting titles
    const titleSelect = document.getElementById('meeting-title');
    titleSelect.innerHTML = `
        <option value="First Meeting">First Meeting</option>
        <option value="Panch Meeting">Panch Meeting</option>
        <option value="Follow-up">Follow-up</option>
        <option value="Location Survey">Location Survey</option>
        <option value="NOC Discussion">NOC Discussion</option>
        <option value="Agreement Signing">Agreement Signing</option>
        <option value="Infra Check">Infra Check</option>
        <option value="Device Installation">Device Installation</option>
        <option value="custom">Custom...</option>
    `;
}

/**
 * Submit meeting (create or update)
 */
async function submitMeeting() {
    const context = document.getElementById('meeting-context').value || 'vp';
    const isHoreca = context === 'horeca';

    if (!isHoreca) {
        const vpSelect = document.getElementById('meeting-vp-select');
        // Validate VP selection
        if (!vpSelect.value || vpSelect.value === '') {
            showToast('Please select a Village Panchayat', 'error');
            return;
        }
    }

    const eventDate = document.getElementById('meeting-date').value;
    if (!eventDate) {
        showToast('Please select a date', 'error');
        return;
    }

    const eventType = document.getElementById('meeting-event-type').value;
    const eventTime = document.getElementById('meeting-time').value || '10:00';
    const duration = eventType === 'calendar_event' ? parseInt(document.getElementById('meeting-duration').value) : 1;

    // Notifications disabled (calendar removed)
    const sendNotifications = false;

    // Get meeting title (use custom input if selected)
    const titleSelect = document.getElementById('meeting-title');
    const titleCustom = document.getElementById('meeting-title-custom');
    const eventTitle = titleSelect.value === 'custom' ? (titleCustom.value || 'Meeting') : titleSelect.value;

    let meetingData;

    if (isHoreca) {
        const horecaPlaceId = document.getElementById('meeting-horeca-place-id').value;
        const horecaName = document.getElementById('meeting-horeca-name').value;

        if (!horecaPlaceId) {
            showToast('HoReCa record not set', 'error');
            return;
        }

        meetingData = {
            vp_code: `HORECA:${horecaPlaceId}`,
            vp_name: horecaName || 'HoReCa',
            block: 'HoReCa',
            event_type: eventType,
            event_date: eventDate,
            event_time: eventTime,
            duration_minutes: duration,
            assigned_to: document.getElementById('meeting-assigned').value || '',
            notes: document.getElementById('meeting-notes-input').value || '',
            event_title: eventTitle,
            horeca_place_id: horecaPlaceId,
            horeca_name: horecaName,
        };
    } else {
        const vpSelect = document.getElementById('meeting-vp-select');
        const selectedOption = vpSelect.options[vpSelect.selectedIndex];
        const vp = vpData.find(v => v.vpCode === vpSelect.value);

        if (!vp) {
            showToast('VP not found. Please reload and try again.', 'error');
            return;
        }

        meetingData = {
            vp_code: vpSelect.value,
            vp_name: vp.vpName || selectedOption.dataset.name || 'Unknown VP',
            block: vp.block || selectedOption.dataset.block || 'Unknown',
            event_type: eventType,
            event_date: eventDate,
            event_time: eventTime,
            duration_minutes: duration,
            assigned_to: document.getElementById('meeting-assigned').value || '',
            notes: document.getElementById('meeting-notes-input').value || '',
            secretary_name: vp.secretaryName || '',
            secretary_phone: String(vp.secretaryPhone || ''),
            event_title: eventTitle,
        };

        if (!meetingData.vp_code || !meetingData.vp_name || !meetingData.block) {
            showToast('Missing VP data. Please select a VP from the dropdown.', 'error');
            console.error('Invalid meeting data:', meetingData);
            return;
        }
    }

    console.log('Submitting meeting data:', meetingData);
    showLoading(true);

    try {
        const response = await fetch(`${API_BASE}/meetings/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(meetingData)
        });

        if (response.ok) {
            const result = await response.json();
            trackEvent('click', 'meetings', 'Meeting Created', `${meetingData.event_type}: ${meetingData.vp_name}`);

            // Add to local data
            meetingsData.push({
                meetingId: result.meeting_id,
                vpCode: meetingData.vp_code,
                vpName: meetingData.vp_name,
                block: meetingData.block,
                eventType: meetingData.event_type,
                eventDate: meetingData.event_date,
                eventTime: meetingData.event_time,
                assignedTo: meetingData.assigned_to,
                calendarEventId: result.calendar_event_id || '',
                status: 'scheduled',
                notes: meetingData.notes,
                eventTitle: meetingData.event_title,  // Store meeting title
            });
            localStorage.setItem('meetingsDataCache', JSON.stringify(meetingsData));

            closeMeetingModal();
            needsSchedulingCache = null; // Invalidate cache
            renderMeetingsTab();
            renderEscalationTab();
            updateTabBadges();

            // Refresh VP meetings section if viewing the same VP (#30 fix)
            if (currentVP && currentVP.vpCode === meetingData.vp_code) {
                renderVPMeetings(currentVP);
                renderPendingFollowup(currentVP);
            }

            // Refresh HoReCa meetings section if in HoReCa context
            if (isHoreca && currentHoreca) {
                renderHorecaMeetings(currentHoreca);
            }

            showToast('Meeting scheduled!', 'success');
        } else {
            // Get error details from response
            try {
                const errorData = await response.json();
                const errorMsg = errorData.detail || errorData.message || 'Failed to schedule meeting';
                console.error('Meeting creation failed:', errorMsg);
                showToast(errorMsg.substring(0, 100), 'error');
            } catch {
                showToast('Failed to schedule meeting', 'error');
            }
        }
    } catch (error) {
        console.error('Meeting creation error:', error);
        showToast('Error scheduling meeting', 'error');
    }

    showLoading(false);
}

/**
 * Open schedule follow-up from VP details (always available)
 */
function openScheduleFollowup() {
    if (!currentVP) {
        showToast('Please select a VP first', 'error');
        return;
    }
    openScheduleMeetingModal(currentVP);
}

/**
 * Edit an existing meeting
 */
function editMeeting(meetingId) {
    const meeting = meetingsData.find(m => m.meetingId === meetingId);
    if (!meeting) {
        console.error('Meeting not found:', meetingId);
        return;
    }

    currentMeetingId = meetingId;
    document.getElementById('meeting-modal-title').textContent = 'Edit Meeting';

    // Populate form with meeting data
    const vpSelect = document.getElementById('meeting-vp-select');
    vpSelect.innerHTML = '<option value="">-- Select VP --</option>' +
        vpData.map(vp => `<option value="${vp.vpCode}" data-block="${vp.block}" data-name="${vp.vpName}">${vp.vpName} (${vp.block})</option>`).join('');
    vpSelect.value = meeting.vpCode;

    document.getElementById('meeting-date').value = meeting.eventDate;
    document.getElementById('meeting-time').value = meeting.eventTime || '10:00';
    document.getElementById('meeting-event-type').value = meeting.eventType;
    document.getElementById('meeting-assigned').value = meeting.assignedTo || '';
    document.getElementById('meeting-notes-input').value = meeting.notes || '';

    // Set meeting title if available
    const titleSelect = document.getElementById('meeting-title');
    const titleCustom = document.getElementById('meeting-title-custom');
    if (meeting.eventTitle) {
        const titleExists = Array.from(titleSelect.options).some(opt => opt.value === meeting.eventTitle);
        if (titleExists) {
            titleSelect.value = meeting.eventTitle;
            titleCustom.classList.add('hidden');
        } else {
            titleSelect.value = 'custom';
            titleCustom.value = meeting.eventTitle;
            titleCustom.classList.remove('hidden');
        }
    } else {
        titleSelect.value = 'First Meeting';
        titleCustom.classList.add('hidden');
    }

    // Toggle visibility based on event type
    toggleMeetingOptions();

    document.getElementById('meeting-modal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

/**
 * Mark meeting as complete
 */
async function markMeetingComplete(meetingId) {
    showLoading(true);
    try {
        const response = await fetch(`${API_BASE}/meetings/update`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                meeting_id: meetingId,
                status: 'completed'
            })
        });

        if (response.ok) {
            const idx = meetingsData.findIndex(m => m.meetingId === meetingId);
            if (idx >= 0) {
                meetingsData[idx].status = 'completed';
                localStorage.setItem('meetingsDataCache', JSON.stringify(meetingsData));
            }
            renderMeetingsTab();
            renderEscalationTab();
            updateTabBadges();
            showToast('Meeting marked as complete', 'success');
        }
    } catch (error) {
        showToast('Failed to update meeting', 'error');
    }
    showLoading(false);
}

/**
 * Delete/cancel a meeting
 */
async function deleteMeeting(meetingId) {
    if (!confirm('Cancel this meeting?')) return;

    showLoading(true);
    try {
        const response = await fetch(`${API_BASE}/meetings/${meetingId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            const idx = meetingsData.findIndex(m => m.meetingId === meetingId);
            if (idx >= 0) {
                meetingsData[idx].status = 'cancelled';
                localStorage.setItem('meetingsDataCache', JSON.stringify(meetingsData));
            }
            renderMeetingsTab();
            renderEscalationTab();
            updateTabBadges();
            showToast('Meeting cancelled', 'success');
        }
    } catch (error) {
        showToast('Failed to cancel meeting', 'error');
    }
    showLoading(false);
}

/**
 * Render today's activity - actions taken today grouped by VP
 */
function renderTodayActivity() {
    const container = document.getElementById('today-activity-list');
    const dateEl = document.getElementById('today-date');
    if (!container) return;

    const now = new Date();
    const todayStr = now.toISOString().split('T')[0];

    // Display today's date
    if (dateEl) {
        dateEl.textContent = now.toLocaleDateString('en-IN', {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
        });
    }

    // Cutoff time: 6 AM today (for development - ignore actions before 6 AM)
    const cutoffTime = new Date(todayStr + 'T06:00:00');

    // RBAC: determine what to show
    const userRole = currentUser ? currentUser.role : 'admin';
    const showVPActivity = userRole === 'admin' || userRole === 'vp';
    const showHorecaActivity = userRole === 'admin' || userRole === 'horeca';

    // Collect all activities from today
    const activities = [];

    // 1. VP Stage updates today (check lastUpdated field)
    if (showVPActivity) vpData.forEach(vp => {
        if (!vp.lastUpdated) return;

        try {
            const updateTime = new Date(vp.lastUpdated);
            if (updateTime >= cutoffTime && updateTime.toISOString().split('T')[0] === todayStr) {
                activities.push({
                    type: 'stage_update',
                    vpCode: vp.vpCode,
                    vpName: vp.vpName,
                    block: vp.block,
                    description: `Stage updated to: ${STAGES.find(s => s.value === vp.currentStage)?.label || vp.currentStage}`,
                    timestamp: updateTime,
                    user: vp.updatedBy || 'Team'
                });
            }
        } catch (e) { /* ignore invalid dates */ }
    });

    // 2. Meetings created today (filtered by role)
    meetingsData.forEach(m => {
        if (!m.createdAt) return;
        // Role filter: vp sees non-HORECA meetings, horeca sees only HORECA meetings
        const isHorecaMeeting = (m.vpCode || '').startsWith('HORECA:');
        if (userRole === 'vp' && isHorecaMeeting) return;
        if (userRole === 'horeca' && !isHorecaMeeting) return;

        try {
            const createTime = new Date(m.createdAt);
            if (createTime >= cutoffTime && createTime.toISOString().split('T')[0] === todayStr) {
                activities.push({
                    type: 'meeting_created',
                    vpCode: m.vpCode,
                    vpName: m.vpName,
                    block: m.block,
                    description: `Meeting scheduled: ${m.eventTitle || 'Meeting'} on ${m.eventDate}`,
                    timestamp: createTime,
                    user: m.assignedTo || 'Team'
                });
            }
        } catch (e) { /* ignore invalid dates */ }
    });

    // 3. Comments added today (parse from meeting notes)
    if (showVPActivity) vpData.forEach(vp => {
        if (!vp.meetingNotes) return;

        const notes = vp.meetingNotes.split('\n---\n');
        notes.forEach(note => {
            // Parse format: [timestamp|type|author] content
            const match = note.match(/^\[([^\]]+)\]\s*(.*)$/s);
            if (!match) return;

            const meta = match[1].split('|');
            if (meta.length < 3) return;

            const timestampStr = meta[0].trim();
            const noteType = meta[1].trim();
            const author = meta[2].trim();
            const content = match[2].trim();

            // Parse timestamp (format: YYYY-MM-DD HH:MM)
            try {
                const noteDate = timestampStr.split(' ')[0];
                if (noteDate === todayStr) {
                    const noteTime = new Date(timestampStr.replace(' ', 'T') + ':00');
                    if (noteTime >= cutoffTime) {
                        activities.push({
                            type: noteType === 'direct' ? 'comment' : 'note',
                            vpCode: vp.vpCode,
                            vpName: vp.vpName,
                            block: vp.block,
                            description: content.substring(0, 100) + (content.length > 100 ? '...' : ''),
                            timestamp: noteTime,
                            user: author
                        });
                    }
                }
            } catch (e) { /* ignore invalid timestamps */ }
        });
    });

    // Sort by timestamp (newest first)
    activities.sort((a, b) => b.timestamp - a.timestamp);

    // Group by VP
    const groupedByVP = {};
    activities.forEach(activity => {
        const key = activity.vpCode || 'other';
        if (!groupedByVP[key]) {
            groupedByVP[key] = {
                vpName: activity.vpName,
                block: activity.block,
                activities: []
            };
        }
        groupedByVP[key].activities.push(activity);
    });

    // Render
    if (Object.keys(groupedByVP).length === 0) {
        container.innerHTML = `
            <div class="card empty-state">
                <p>No activity recorded today (after 6 AM)</p>
                <p class="hint">Updates to VPs, meetings scheduled, and comments will appear here</p>
            </div>
        `;
        return;
    }

    container.innerHTML = Object.entries(groupedByVP).map(([vpCode, data]) => `
        <div class="card today-vp-card">
            <div class="today-vp-header">
                <span class="today-vp-name">${data.vpName || 'Unknown VP'}</span>
                <span class="today-vp-block">${data.block || ''}</span>
                <span class="today-activity-count">${data.activities.length} action${data.activities.length > 1 ? 's' : ''}</span>
            </div>
            <div class="today-activities">
                ${data.activities.map(a => `
                    <div class="today-activity-item ${a.type}">
                        <span class="activity-icon">${getActivityIcon(a.type)}</span>
                        <div class="activity-content">
                            <span class="activity-description">${a.description}</span>
                            <span class="activity-meta">${a.timestamp.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} by ${a.user}</span>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

/**
 * Get icon for activity type
 */
function getActivityIcon(type) {
    const icons = {
        'stage_update': '📊',
        'meeting_created': '📅',
        'comment': '💬',
        'note': '📝',
        'meeting': '🏛️'
    };
    return icons[type] || '📌';
}

// Make meeting functions globally accessible
window.openScheduleMeetingModal = openScheduleMeetingModal;
window.closeMeetingModal = closeMeetingModal;
window.submitMeeting = submitMeeting;
window.openScheduleFollowup = openScheduleFollowup;
window.editMeeting = editMeeting;
window.markMeetingComplete = markMeetingComplete;
window.deleteMeeting = deleteMeeting;

// ==================== Escalation Tab ====================

// Stages to track for escalation and their thresholds (in working days)
const ESCALATION_STAGES = {
    'first_meeting_done': { label: 'First Meeting Done', threshold: 3 },
    'follow_up_required': { label: 'First Meeting Done', threshold: 3 }, // legacy
    'panch_meeting_done': { label: 'Panch Meeting Done', threshold: 3 },
    'email_sent': { label: 'Email Sent', threshold: 3 },
    'noc_received': { label: 'NOC Received', threshold: 3 },
    'service_agreement_sent': { label: 'Agreement Sent', threshold: 3 },
};

/**
 * Check if a date is the 2nd Saturday of its month
 */
function isSecondSaturday(date) {
    if (date.getDay() !== 6) return false; // Not a Saturday
    const dayOfMonth = date.getDate();
    return dayOfMonth >= 8 && dayOfMonth <= 14;
}

/**
 * Count working days between two dates (excludes Sundays and 2nd Saturdays)
 */
function countWorkingDays(startDate, endDate) {
    let count = 0;
    const current = new Date(startDate);
    current.setHours(0, 0, 0, 0);
    const end = new Date(endDate);
    end.setHours(0, 0, 0, 0);

    while (current < end) {
        current.setDate(current.getDate() + 1);
        const day = current.getDay();

        // Skip Sundays
        if (day === 0) continue;

        // Skip 2nd Saturdays
        if (isSecondSaturday(current)) continue;

        count++;
    }
    return count;
}

/**
 * Get severity level based on working days stuck
 */
function getEscalationSeverity(workingDays) {
    if (workingDays > 3) return { level: 'red', label: `${workingDays}d`, icon: '🔴' };
    if (workingDays === 3) return { level: 'orange', label: '3d', icon: '🟠' };
    if (workingDays === 2) return { level: 'yellow', label: '2d', icon: '🟡' };
    return null; // No escalation needed
}

/**
 * Render the Escalation tab
 */
function renderEscalationTab() {
    const container = document.getElementById('escalation-list');
    const summaryEl = document.getElementById('escalation-summary');
    if (!container) return;

    const today = new Date();
    const escalations = [];

    // Build set of VP codes that have an UPCOMING follow-up (today or later)
    const todayStr = new Date().toISOString().split('T')[0];
    const vpsWithUpcomingFollowUp = new Set();
    meetingsData.forEach(m => {
        if (m.status === 'scheduled' && m.vpCode && m.eventDate >= todayStr) {
            vpsWithUpcomingFollowUp.add(m.vpCode);
        }
    });

    vpData.forEach(vp => {
        const stage = vp.currentStage;
        const config = ESCALATION_STAGES[stage];
        if (!config) return; // Stage not tracked for escalation

        // Skip VPs with an UPCOMING meeting — they are being actively managed.
        // Missed meetings (past date) don't count.
        if (vpsWithUpcomingFollowUp.has(vp.vpCode)) return;

        // Use stageDate as the timer basis
        if (!vp.stageDate) return;

        const stageDate = new Date(vp.stageDate);
        if (isNaN(stageDate.getTime())) return;

        const workingDays = countWorkingDays(stageDate, today);
        const severity = getEscalationSeverity(workingDays);
        if (!severity) return; // Not yet at threshold

        // Build reason description
        const vpMeetings = meetingsData.filter(m => m.vpCode === vp.vpCode);
        const missedMeetings = vpMeetings.filter(m => m.status === 'scheduled' && m.eventDate < todayStr);
        const completedMeetings = vpMeetings.filter(m => m.status === 'completed');
        const hasPanchScheduled = resolveStageNumber(vp) === 4 || resolveStageNumber(vp) === 5;

        let reason = '';
        if (resolveStageNumber(vp) === 3) {
            // First Meeting Done — why stuck?
            if (missedMeetings.length > 0) {
                const lastMissed = missedMeetings.sort((a, b) => b.eventDate.localeCompare(a.eventDate))[0];
                const missedDate = new Date(lastMissed.eventDate).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
                reason = `Follow-up was scheduled for ${missedDate} but was missed. No upcoming follow-up or Panch meeting scheduled.`;
            } else {
                reason = `No Panch meeting or follow-up call scheduled since last update.`;
            }
        } else if (stage === 'panch_meeting_done') {
            reason = `Panch meeting completed but location not yet finalized.`;
        } else if (stage === 'email_sent') {
            reason = `Confirmation email sent, awaiting NOC from Panchayat.`;
        } else if (stage === 'noc_received') {
            reason = `NOC received but service agreement not yet sent.`;
        } else if (stage === 'service_agreement_sent') {
            reason = `Agreement sent, awaiting signature from Panchayat.`;
        }

        escalations.push({
            vp,
            stage,
            stageLabel: config.label,
            stageDate: vp.stageDate,
            workingDays,
            severity,
            reason,
            meetingHistory: vpMeetings.sort((a, b) => (b.eventDate || '').localeCompare(a.eventDate || '')),
        });
    });

    // Sort: red first, then orange, then yellow; within same severity by days desc
    const severityOrder = { red: 0, orange: 1, yellow: 2 };
    escalations.sort((a, b) => {
        const severityDiff = severityOrder[a.severity.level] - severityOrder[b.severity.level];
        if (severityDiff !== 0) return severityDiff;
        return b.workingDays - a.workingDays;
    });

    // Update summary
    if (summaryEl) {
        const redCount = escalations.filter(e => e.severity.level === 'red').length;
        const orangeCount = escalations.filter(e => e.severity.level === 'orange').length;
        const yellowCount = escalations.filter(e => e.severity.level === 'yellow').length;
        summaryEl.innerHTML = `${escalations.length} VP${escalations.length !== 1 ? 's' : ''} need attention`;
        if (escalations.length > 0) {
            summaryEl.innerHTML += ` <span class="escalation-counts">🔴 ${redCount} 🟠 ${orangeCount} 🟡 ${yellowCount}</span>`;
        }
    }

    // Get filter values
    const stageFilter = document.getElementById('escalation-stage-filter');
    const severityFilter = document.getElementById('escalation-severity-filter');

    let filtered = escalations;
    if (stageFilter && stageFilter.value) {
        filtered = filtered.filter(e => e.stage === stageFilter.value);
    }
    if (severityFilter && severityFilter.value) {
        filtered = filtered.filter(e => e.severity.level === severityFilter.value);
    }

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="padding: 40px 20px; text-align: center;">
                <p style="font-size: 32px; margin-bottom: 8px;">✅</p>
                <p style="color: #64748b;">${escalations.length === 0 ? 'No VPs need escalation right now' : 'No matches for selected filters'}</p>
            </div>
        `;
        return;
    }

    // Group by working days stuck (descending)
    const grouped = {};
    filtered.forEach(esc => {
        const key = esc.workingDays;
        if (!grouped[key]) grouped[key] = [];
        grouped[key].push(esc);
    });
    const sortedDays = Object.keys(grouped).map(Number).sort((a, b) => b - a);

    // Render card helper
    const renderCard = (esc) => {
        const dateStr = new Date(esc.stageDate).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

        // Meeting history (last 3)
        let historyHtml = '';
        if (esc.meetingHistory.length > 0) {
            const recent = esc.meetingHistory.slice(0, 3);
            historyHtml = `
                <div class="escalation-history">
                    <span class="history-label">History:</span>
                    ${recent.map(m => {
                        const mDate = m.eventDate ? new Date(m.eventDate).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '—';
                        const statusCls = m.status === 'completed' ? 'done' : m.status === 'scheduled' && m.eventDate < todayStr ? 'missed' : 'upcoming';
                        const statusIcon = statusCls === 'done' ? '✓' : statusCls === 'missed' ? '✗' : '◦';
                        const noteSnippet = m.notes ? m.notes.substring(0, 40) + (m.notes.length > 40 ? '…' : '') : '';
                        return `<span class="history-item history-${statusCls}">${statusIcon} ${mDate}${noteSnippet ? ' — ' + noteSnippet : ''}</span>`;
                    }).join('')}
                </div>`;
        }

        return `
            <div class="escalation-card escalation-${esc.severity.level}" onclick="navigateToVP('${esc.vp.vpCode}', '${esc.vp.block}')">
                <div class="escalation-flag">
                    <span class="escalation-icon">${esc.severity.icon}</span>
                    <span class="escalation-days">${esc.workingDays}d</span>
                </div>
                <div class="escalation-info">
                    <div class="escalation-vp-name">${esc.vp.vpName}</div>
                    <div class="escalation-meta">
                        <span class="escalation-block">${esc.vp.block}</span>
                        <span class="escalation-stage-badge">${esc.stageLabel}</span>
                    </div>
                    <div class="escalation-reason">Last update ${dateStr}. ${esc.reason}</div>
                    ${historyHtml}
                </div>
                <div class="escalation-date">
                    <span class="escalation-since">Since</span>
                    <span class="escalation-date-value">${dateStr}</span>
                </div>
            </div>`;
    };

    container.innerHTML = sortedDays.map((days, idx) => {
        const items = grouped[days];
        const severity = items[0].severity;
        const isOpen = idx === 0; // most severe group open by default
        return `
            <div class="escalation-group">
                <div class="escalation-group-header escalation-group-${severity.level}${isOpen ? ' open' : ''}" onclick="toggleEscalationGroup(this)">
                    <span class="chevron">&#9654;</span>
                    ${severity.icon} ${days} working day${days !== 1 ? 's' : ''} stuck
                    <span class="escalation-group-count">${items.length} VP${items.length !== 1 ? 's' : ''}</span>
                </div>
                <div class="escalation-group-cards${isOpen ? '' : ' collapsed'}">
                    ${items.map(renderCard).join('')}
                </div>
            </div>`;
    }).join('');
}

/**
 * Navigate to a VP from escalation card click
 */
function navigateToVP(vpCode, block) {
    // Switch to VPs tab
    const vpsTab = document.querySelector('.nav-item[data-tab="vps"]');
    if (vpsTab) vpsTab.click();

    // Find and select the VP
    const vp = vpData.find(v => v.vpCode === vpCode && v.block === block);
    if (vp) {
        currentVP = vp;
        showVPDetails(vp);

        // Show detail panel on mobile
        showDetailPanel();

        // Highlight in master list
        document.querySelectorAll('.master-vp-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.vpCode === vpCode) {
                item.classList.add('active');
                item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        });
    }
}

// Setup escalation filter listeners
document.addEventListener('DOMContentLoaded', () => {
    const stageFilter = document.getElementById('escalation-stage-filter');
    const severityFilter = document.getElementById('escalation-severity-filter');
    if (stageFilter) stageFilter.addEventListener('change', renderEscalationTab);
    if (severityFilter) severityFilter.addEventListener('change', renderEscalationTab);
});

// Make escalation functions globally accessible
window.navigateToVP = navigateToVP;

function toggleEscalationGroup(header) {
    header.classList.toggle('open');
    const cards = header.nextElementSibling;
    cards.classList.toggle('collapsed');
}
window.toggleEscalationGroup = toggleEscalationGroup;

// ==================== HoReCa Data Tab ====================

// State
let horecaData = null;
let horecaGeoHex8 = null;
let horecaGeoHex7 = null;
let horecaGeoTaluka = null;
let horecaLoaded = false;
let horecaMapInstance = null;
let horecaPage = 1;
const HORECA_PAGE_SIZE = 50;

// Layer references
let hrcTalukaLayer = null;
let hrcMesoLayer = null;
let hrcHexLayer = null;
let hrcPointLayer = null;

async function initHoReCaTab() {
    // Setup sub-tabs
    setupHoReCaSubTabs();

    // Init CRM (default sub-tab) on first visit
    if (!horecaCrmLoaded) {
        initHoReCaCRM();
    }
}

function setupHoReCaSubTabs() {
    document.querySelectorAll('.horeca-sub-tab').forEach(tab => {
        tab.removeEventListener('click', handleHoReCaSubTabClick);
        tab.addEventListener('click', handleHoReCaSubTabClick);
    });
}

function handleHoReCaSubTabClick() {
    document.querySelectorAll('.horeca-sub-tab').forEach(t => t.classList.remove('active'));
    this.classList.add('active');
    const subId = this.dataset.horeca;
    document.querySelectorAll('.horeca-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`horeca-${subId}`).classList.add('active');

    // Invalidate map size when switching to map tab
    if (subId === 'map' && horecaMapInstance) {
        setTimeout(() => horecaMapInstance.invalidateSize(), 100);
    }

    // Lazy-load static data for Map/Explorer/Summary
    if ((subId === 'map' || subId === 'explorer' || subId === 'summary') && !horecaLoaded) {
        loadHoReCaStaticData();
    }

    // Init map if switching to map and data is loaded
    if (subId === 'map' && !horecaMapInstance && horecaLoaded) {
        initHoReCaMap();
    }

    // CRM tab
    if (subId === 'crm' && !horecaCrmLoaded) {
        initHoReCaCRM();
    }

    // Board tab
    if (subId === 'board') {
        initHoReCaBoard();
    }

    // Dashboard tab
    if (subId === 'hdashboard') {
        initHoReCaDashboard();
    }
}

async function loadHoReCaStaticData() {
    if (horecaLoaded) return;
    try {
        const [records, hex8, hex7, taluka] = await Promise.all([
            fetch('/static/data/horeca/horeca_records.json').then(r => r.json()),
            fetch('/static/data/horeca/horeca_hex8.geojson').then(r => r.json()),
            fetch('/static/data/horeca/horeca_hex7.geojson').then(r => r.json()),
            fetch('/static/data/horeca/horeca_taluka.geojson').then(r => r.json()),
        ]);
        horecaData = records;
        horecaGeoHex8 = hex8;
        horecaGeoHex7 = hex7;
        horecaGeoTaluka = taluka;
        horecaLoaded = true;

        populateHoReCaFilters();
        renderHoReCaExplorer();
        renderHoReCaSummary();
    } catch (e) {
        console.error('Failed to load HoReCa data:', e);
        document.getElementById('hrc-summary-content').innerHTML =
            '<div class="card"><p>Failed to load HoReCa data. Ensure data files exist in /data/horeca/.</p></div>';
    }
}

// ── Leaflet dynamic loading ──
function loadLeaflet(callback) {
    if (window.L) { callback(); return; }
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(link);

    const script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.onload = callback;
    document.head.appendChild(script);
}

// ── Map ──
function initHoReCaMap() {
    loadLeaflet(() => {
        const map = L.map('horeca-leaflet-map', {
            zoomControl: true,
            zoomSnap: 0.25,
            zoomDelta: 0.5,
            wheelDebounceTime: 80,
            wheelPxPerZoomLevel: 120
        });
        horecaMapInstance = map;

        // CartoDB Voyager (warmer aesthetic)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OSM &copy; CARTO',
            maxZoom: 19
        }).addTo(map);

        // Layer 1: Taluka boundaries
        hrcTalukaLayer = L.geoJSON(horecaGeoTaluka, {
            style: { color: '#64748b', weight: 2, fillOpacity: 0, opacity: 0.6, dashArray: '6, 4' },
            onEachFeature: (feature, layer) => {
                layer.bindTooltip(feature.properties.name, { permanent: false, direction: 'center' });
            }
        }).addTo(map);

        // Layer 2: Meso zones (res-7) — colored by density classification
        const MESO_COLORS = { HD: '#dc2626', MD: '#f59e0b', LD: '#3b82f6', Dead: '#9ca3af' };
        const MESO_OPACITY = { HD: 0.50, MD: 0.42, LD: 0.35, Dead: 0.20 };
        hrcMesoLayer = L.geoJSON(horecaGeoHex7, {
            style: function(feature) {
                const dens = feature.properties.density || 'Dead';
                const color = MESO_COLORS[dens] || '#9ca3af';
                const fillOp = MESO_OPACITY[dens] || 0.20;
                return { color: color, weight: 2.5, fillColor: color, fillOpacity: fillOp, opacity: 0.8 };
            },
            onEachFeature: (feature, layer) => {
                const p = feature.properties;
                layer.bindTooltip(`${p.name} — ${p.count}`, {
                    permanent: false,
                    direction: 'center',
                    className: 'horeca-meso-label'
                });
                layer.bindPopup(`
                    <div class="horeca-popup">
                        <div class="popup-name">${p.name}</div>
                        <div class="popup-kv"><span>HoReCas</span><span>${p.count}</span></div>
                        <div class="popup-kv"><span>Micro zones</span><span>${p.micro_count}</span></div>
                        <div class="popup-kv"><span>Avg score</span><span>${p.avg_score}</span></div>
                    </div>
                `, { maxWidth: 220 });
                layer.on('mouseover', function(e) { const d = feature.properties.density||'Dead'; this.setStyle({ fillOpacity: (MESO_OPACITY[d]||0.20) + 0.15, weight: 3.5 }); });
                layer.on('mouseout', function() { hrcMesoLayer.resetStyle(this); });
            }
        });
        // Off by default

        // Layer 3: Micro zones (res-8) — blue choropleth
        hrcHexLayer = buildHoReCaHexLayer(horecaGeoHex8);
        hrcHexLayer.addTo(map);

        // Layer 4: HoReCa points
        hrcPointLayer = buildHoReCaPointLayer();
        hrcPointLayer.addTo(map);

        // Fit bounds
        if (hrcHexLayer.getLayers().length > 0) {
            map.fitBounds(hrcHexLayer.getBounds().pad(0.05));
        }

        updateHoReCaMapStats();

        // Wire controls
        document.getElementById('hrc-toggle-taluka').addEventListener('change', function() {
            this.checked ? map.addLayer(hrcTalukaLayer) : map.removeLayer(hrcTalukaLayer);
        });
        document.getElementById('hrc-toggle-meso').addEventListener('change', function() {
            this.checked ? map.addLayer(hrcMesoLayer) : map.removeLayer(hrcMesoLayer);
        });
        document.getElementById('hrc-toggle-hex').addEventListener('change', function() {
            this.checked ? map.addLayer(hrcHexLayer) : map.removeLayer(hrcHexLayer);
        });
        document.getElementById('hrc-toggle-points').addEventListener('change', function() {
            this.checked ? map.addLayer(hrcPointLayer) : map.removeLayer(hrcPointLayer);
        });
        document.querySelectorAll('.hrc-density').forEach(cb => {
            cb.addEventListener('change', applyHoReCaMapFilters);
        });
    });
}

function getHoReCaHexColor(count) {
    if (count >= 10) return '#1e40af';
    if (count >= 7) return '#2563eb';
    if (count >= 5) return '#3b82f6';
    if (count >= 3) return '#60a5fa';
    if (count >= 2) return '#93c5fd';
    return '#bfdbfe';
}

function buildHoReCaHexLayer(data) {
    return L.geoJSON(data, {
        style: function(feature) {
            return {
                fillColor: getHoReCaHexColor(feature.properties.count),
                weight: 1,
                opacity: 0.8,
                color: '#fff',
                fillOpacity: 0.65
            };
        },
        onEachFeature: (feature, layer) => {
            const p = feature.properties;
            const topList = p.top_horecas ? p.top_horecas.split(' | ').map(n => `<li>${n}</li>`).join('') : '';
            layer.bindPopup(`
                <div class="horeca-popup">
                    <div class="popup-name">#${p.rank} ${p.name}</div>
                    <div class="popup-kv"><span>HoReCas</span><span>${p.count}</span></div>
                    <div class="popup-kv"><span>Zone score</span><span>${p.score}</span></div>
                    <div class="popup-kv"><span>Avg priority</span><span>${p.avg_priority}</span></div>
                    <div class="popup-divider"></div>
                    <div class="popup-kv"><span>High priority</span><span>${p.high_priority}</span></div>
                    <div class="popup-kv"><span>Contactable</span><span>${p.contactable}</span></div>
                    <div class="popup-kv"><span>Alcohol</span><span>${p.alcohol}</span></div>
                    ${topList ? `<div class="popup-divider"></div><div style="font-size:11px;color:#555"><strong>Top:</strong><ul style="margin:2px 0 0 14px">${topList}</ul></div>` : ''}
                </div>
            `, { maxWidth: 260 });
            layer.on('mouseover', function() { this.setStyle({ fillOpacity: 0.9, weight: 2 }); });
            layer.on('mouseout', function() { hrcHexLayer.resetStyle(this); });
        }
    });
}

function getHoReCaPointColor(type) {
    const t = (type || '').toLowerCase();
    if (t.includes('restaurant')) return '#2563eb';
    if (t.includes('bar') || t.includes('shack')) return '#dc2626';
    if (t.includes('hotel') || t.includes('resort')) return '#7c3aed';
    if (t.includes('cafe')) return '#10b981';
    return '#f59e0b'; // lodging, homestay, guesthouse
}

function buildHoReCaPointLayer() {
    const features = horecaData.map(r => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [r.lng, r.lat] },
        properties: r
    }));

    return L.geoJSON({ type: 'FeatureCollection', features }, {
        pointToLayer: (feature, latlng) => {
            const p = feature.properties;
            return L.circleMarker(latlng, {
                radius: 4,
                fillColor: getHoReCaPointColor(p.type),
                color: '#fff',
                weight: 0.8,
                fillOpacity: 0.8
            });
        },
        onEachFeature: (feature, layer) => {
            const p = feature.properties;
            const phone = p.phone ? `<div class="popup-kv"><span>Phone</span><span>${p.phone}</span></div>` : '';
            const gmap = p.gmap ? `<a href="${p.gmap}" target="_blank" style="color:#2563eb;font-size:11px;display:block;margin-top:4px">Google Maps &rarr;</a>` : '';
            layer.bindPopup(`
                <div class="horeca-popup">
                    <div class="popup-name">${p.name}</div>
                    <div class="popup-kv"><span>Type</span><span>${p.type}</span></div>
                    <div class="popup-kv"><span>Priority</span><span>${p.pscore}</span></div>
                    <div class="popup-kv"><span>Rating</span><span>${p.rat} (${p.trat})</span></div>
                    <div class="popup-kv"><span>Alcohol</span><span>${p.alc}</span></div>
                    <div class="popup-kv"><span>Contact</span><span>${p.cont}</span></div>
                    ${phone}
                    <div class="popup-divider"></div>
                    <div class="popup-kv"><span>Zone</span><span>${p.zname}</span></div>
                    ${gmap}
                </div>
            `, { maxWidth: 260 });
        }
    });
}

function applyHoReCaMapFilters() {
    if (!horecaMapInstance) return;

    const ranges = [];
    document.querySelectorAll('.hrc-density').forEach(cb => {
        if (cb.checked) ranges.push({ min: +cb.dataset.min, max: +cb.dataset.max });
    });

    const hexOn = document.getElementById('hrc-toggle-hex').checked;
    const pointsOn = document.getElementById('hrc-toggle-points').checked;

    // Rebuild hex layer
    horecaMapInstance.removeLayer(hrcHexLayer);
    const filtered = {
        type: 'FeatureCollection',
        features: horecaGeoHex8.features.filter(f => {
            const c = f.properties.count;
            return ranges.some(r => c >= r.min && c <= r.max);
        })
    };
    hrcHexLayer = buildHoReCaHexLayer(filtered);
    if (hexOn) hrcHexLayer.addTo(horecaMapInstance);

    // Rebuild point layer filtering by visible zones
    const visibleZoneIds = new Set(filtered.features.map(f => f.properties.id));
    horecaMapInstance.removeLayer(hrcPointLayer);

    const pointFeatures = horecaData
        .filter(r => visibleZoneIds.has(r.h8))
        .map(r => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [r.lng, r.lat] },
            properties: r
        }));

    hrcPointLayer = L.geoJSON({ type: 'FeatureCollection', features: pointFeatures }, {
        pointToLayer: (feature, latlng) => {
            return L.circleMarker(latlng, {
                radius: 4,
                fillColor: getHoReCaPointColor(feature.properties.type),
                color: '#fff',
                weight: 0.8,
                fillOpacity: 0.8
            });
        },
        onEachFeature: (feature, layer) => {
            const p = feature.properties;
            layer.bindPopup(`
                <div class="horeca-popup">
                    <div class="popup-name">${p.name}</div>
                    <div class="popup-kv"><span>Type</span><span>${p.type}</span></div>
                    <div class="popup-kv"><span>Priority</span><span>${p.pscore}</span></div>
                    <div class="popup-kv"><span>Alcohol</span><span>${p.alc}</span></div>
                </div>
            `, { maxWidth: 220 });
        }
    });
    if (pointsOn) hrcPointLayer.addTo(horecaMapInstance);

    updateHoReCaMapStats(visibleZoneIds.size, pointFeatures.length);
}

function updateHoReCaMapStats(zoneCount, pointCount) {
    const el = document.getElementById('horeca-map-stats');
    if (!el) return;
    const total = horecaData ? horecaData.length : 0;
    const visible = pointCount !== undefined ? pointCount : total;
    const zones = zoneCount !== undefined ? zoneCount : (horecaGeoHex8 ? horecaGeoHex8.features.length : 0);
    el.textContent = `${visible.toLocaleString()} of ${total.toLocaleString()} HoReCas · ${zones} zones`;
}

// ── Explorer ──
function populateHoReCaFilters() {
    if (!horecaData) return;

    const types = [...new Set(horecaData.map(r => r.type))].sort();
    const alcSignals = [...new Set(horecaData.map(r => r.alc))].sort();
    const cities = [...new Set(horecaData.map(r => r.city))].sort();
    const sizes = [...new Set(horecaData.map(r => r.size))].sort();
    const contacts = [...new Set(horecaData.map(r => r.cont))].sort();

    fillSelect('hrc-filter-type', types, 'All Types');
    fillSelect('hrc-filter-alc', alcSignals, 'Alcohol');
    fillSelect('hrc-filter-city', cities, 'All Cities');
    fillSelect('hrc-filter-size', sizes, 'Size');
    fillSelect('hrc-filter-cont', contacts, 'Contact');

    // Wire filter events
    ['hrc-search', 'hrc-filter-type', 'hrc-filter-alc', 'hrc-filter-city', 'hrc-filter-size', 'hrc-filter-cont'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', () => {
            horecaPage = 1;
            renderHoReCaExplorer();
        });
    });
}

function fillSelect(id, values, defaultLabel) {
    const sel = document.getElementById(id);
    if (!sel) return;
    sel.innerHTML = `<option value="">${defaultLabel}</option>` +
        values.filter(v => v).map(v => `<option value="${v}">${v}</option>`).join('');
}

function getFilteredHoReCa() {
    if (!horecaData) return [];

    const search = (document.getElementById('hrc-search')?.value || '').toLowerCase();
    const type = document.getElementById('hrc-filter-type')?.value || '';
    const alc = document.getElementById('hrc-filter-alc')?.value || '';
    const city = document.getElementById('hrc-filter-city')?.value || '';
    const size = document.getElementById('hrc-filter-size')?.value || '';
    const cont = document.getElementById('hrc-filter-cont')?.value || '';

    return horecaData.filter(r => {
        if (search && !r.name.toLowerCase().includes(search)) return false;
        if (type && r.type !== type) return false;
        if (alc && r.alc !== alc) return false;
        if (city && r.city !== city) return false;
        if (size && r.size !== size) return false;
        if (cont && r.cont !== cont) return false;
        return true;
    });
}

function renderHoReCaExplorer() {
    const filtered = getFilteredHoReCa();
    const totalPages = Math.max(1, Math.ceil(filtered.length / HORECA_PAGE_SIZE));
    if (horecaPage > totalPages) horecaPage = totalPages;

    const start = (horecaPage - 1) * HORECA_PAGE_SIZE;
    const pageItems = filtered.slice(start, start + HORECA_PAGE_SIZE);

    // Info line
    const info = document.getElementById('hrc-explorer-info');
    if (info) info.textContent = `${filtered.length.toLocaleString()} results · Page ${horecaPage} of ${totalPages}`;

    // Cards
    const grid = document.getElementById('hrc-card-grid');
    if (!grid) return;

    grid.innerHTML = pageItems.map((r, i) => {
        const idx = start + i;
        const typeClass = getHoReCaTypeClass(r.type);
        const alcBadgeClass = r.alc === 'Confirmed' ? 'badge-alc-confirmed' :
                              r.alc === 'Possible' || r.alc === 'Likely' || r.alc === 'Inferred' ? 'badge-alc-possible' :
                              'badge-alc-unknown';
        const statusBadge = r.status === 'OPERATIONAL' ?
            '<span class="horeca-badge badge-status-active">Active</span>' :
            '<span class="horeca-badge badge-status-inactive">Closed</span>';

        return `
        <div class="horeca-card ${typeClass}">
            <div class="horeca-card-top">
                <div>
                    <div class="horeca-card-name">${escapeHtml(r.name)}</div>
                    <div class="horeca-card-city">${escapeHtml(r.city)}</div>
                </div>
                <div class="horeca-card-score">
                    <span class="score-value">${r.pscore}</span>
                    <span class="score-rank">#${r.prank}</span>
                </div>
            </div>
            <div class="horeca-card-meta">
                <span class="horeca-badge badge-type">${escapeHtml(r.type)}</span>
                <span class="horeca-badge ${alcBadgeClass}">${escapeHtml(r.alc)}</span>
                ${r.rat ? `<span class="horeca-badge badge-rating">${r.rat} ★ (${r.trat})</span>` : ''}
                ${statusBadge}
            </div>
            <div class="horeca-card-details" id="hrc-detail-${idx}">
                ${r.phone ? `<div class="horeca-card-detail-row"><span>Phone</span><span>${escapeHtml(r.phone)}</span></div>` : ''}
                <div class="horeca-card-detail-row"><span>Address</span><span>${escapeHtml(r.addr || '-')}</span></div>
                <div class="horeca-card-detail-row"><span>Size</span><span>${escapeHtml(r.size || '-')}</span></div>
                <div class="horeca-card-detail-row"><span>Contactability</span><span>${escapeHtml(r.cont || '-')}</span></div>
                <div class="horeca-card-detail-row"><span>Zone</span><span>#${r.zrank} ${escapeHtml(r.zname)}</span></div>
                ${r.gmap ? `<div class="horeca-card-detail-row"><span>Maps</span><span><a href="${r.gmap}" target="_blank">Open &rarr;</a></span></div>` : ''}
                ${r.web ? `<div class="horeca-card-detail-row"><span>Website</span><span><a href="${r.web}" target="_blank">Visit &rarr;</a></span></div>` : ''}
            </div>
            <button class="horeca-card-toggle" onclick="toggleHoReCaCard(${idx})">View More</button>
        </div>`;
    }).join('');

    // Pagination
    const pag = document.getElementById('hrc-pagination');
    if (pag) {
        pag.innerHTML = `
            <button ${horecaPage <= 1 ? 'disabled' : ''} onclick="horecaPage--;renderHoReCaExplorer()">Prev</button>
            <span class="page-info">${horecaPage} / ${totalPages}</span>
            <button ${horecaPage >= totalPages ? 'disabled' : ''} onclick="horecaPage++;renderHoReCaExplorer()">Next</button>
        `;
    }
}

function getHoReCaTypeClass(type) {
    const t = (type || '').toLowerCase();
    if (t.includes('restaurant')) return 'type-restaurant';
    if (t.includes('bar') || t.includes('shack')) return 'type-bar';
    if (t.includes('hotel') || t.includes('resort')) return 'type-hotel';
    if (t.includes('cafe')) return 'type-cafe';
    if (t.includes('homestay') || t.includes('villa')) return 'type-homestay';
    if (t.includes('guesthouse')) return 'type-guesthouse';
    if (t.includes('lodging')) return 'type-lodging';
    return '';
}

function toggleHoReCaCard(idx) {
    const details = document.getElementById(`hrc-detail-${idx}`);
    if (!details) return;
    const isOpen = details.classList.toggle('open');
    const btn = details.nextElementSibling;
    if (btn) btn.textContent = isOpen ? 'Hide' : 'View More';
}
window.toggleHoReCaCard = toggleHoReCaCard;
window.horecaPage = horecaPage;

// Expose for pagination onclick
Object.defineProperty(window, 'horecaPage', {
    get() { return horecaPage; },
    set(v) { horecaPage = v; }
});
window.renderHoReCaExplorer = renderHoReCaExplorer;

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Summary ──
const QUAD_LABELS = {
    Q1: 'Q1 — North East (Interior North)',
    Q2: 'Q2 — North West (Tourist North)',
    Q3: 'Q3 — South West (Tourist South)',
    Q4: 'Q4 — South East (Interior South)',
};
const QUAD_SHORT = { Q1: 'NE', Q2: 'NW', Q3: 'SW', Q4: 'SE' };
const DENSITY_ORDER = ['HD', 'MD', 'LD', 'Dead'];
const DENSITY_LABELS = { HD: 'High Density (50+)', MD: 'Medium Density (10–49)', LD: 'Low Density (4–9)', Dead: 'Dead (≤3)' };
const DENSITY_COLORS = { HD: '#dc2626', MD: '#f59e0b', LD: '#3b82f6', Dead: '#9ca3af' };

function renderHoReCaSummary() {
    if (!horecaData) return;
    const container = document.getElementById('hrc-summary-content');
    if (!container) return;

    const data = horecaData;
    const total = data.length;
    const alcTotal = data.filter(r => r.alcseg === 'Alcohol').length;
    const avgPriority = (data.reduce((s, r) => s + r.pscore, 0) / total).toFixed(1);
    const highContact = data.filter(r => r.cont === 'High').length;
    const mesoZones = horecaGeoHex7 ? horecaGeoHex7.features.map(f => f.properties) : [];
    const activeZones = mesoZones.filter(z => z.density !== 'Dead');

    // Helper: density dot
    const dDot = (d, sz) => `<span style="display:inline-block;width:${sz||10}px;height:${sz||10}px;border-radius:2px;background:${DENSITY_COLORS[d]};margin-right:6px"></span>`;

    // Helper: collapsible section
    let collapseId = 0;
    const collapseOpen = (title, summary, open) => {
        const id = `hrc-collapse-${collapseId++}`;
        return `<details class="hrc-collapsible"${open ? ' open' : ''}><summary class="hrc-collapse-header"><span class="hrc-collapse-title">${title}</span><span class="hrc-collapse-summary">${summary}</span><svg class="hrc-collapse-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg></summary><div class="hrc-collapse-body">`;
    };
    const collapseClose = () => `</div></details>`;

    // Helper: total row for density tables
    const densityTotalRow = (recs, zones, colspan) => {
        const tAlc = recs.filter(r => r.alcseg === 'Alcohol').length;
        const tAvg = recs.length ? (recs.reduce((s,r) => s + r.pscore, 0) / recs.length).toFixed(1) : '-';
        return `<tr style="background:var(--gray-50);font-weight:700;border-top:2px solid var(--gray-300)"><td>Total</td><td class="num">${zones.length}</td><td class="num">${recs.length.toLocaleString()}</td><td class="num">100%</td><td class="num">${tAlc.toLocaleString()}</td><td class="num">${(recs.length - tAlc).toLocaleString()}</td><td class="num">${tAvg}</td></tr>`;
    };

    // ── Top stat cards ──
    let html = `
    <div class="horeca-stat-cards">
        <div class="horeca-stat-card"><div class="stat-value">${total.toLocaleString()}</div><div class="stat-label">Total HoReCas</div></div>
        <div class="horeca-stat-card"><div class="stat-value">${mesoZones.length}</div><div class="stat-label">Total Zones</div></div>
        <div class="horeca-stat-card"><div class="stat-value">${activeZones.length}</div><div class="stat-label">Active Zones</div></div>
        <div class="horeca-stat-card"><div class="stat-value">${alcTotal.toLocaleString()}</div><div class="stat-label">Alcohol (Phase 1)</div></div>
        <div class="horeca-stat-card"><div class="stat-value">${avgPriority}</div><div class="stat-label">Avg Priority</div></div>
    </div>`;

    // ── 1. Quadrant Overview (always open) ──
    html += `<div class="horeca-summary-table-wrapper"><h3>Quadrant Overview</h3>
        <p class="hrc-table-note">Goa split into 4 quadrants — NH66 highway (lng 73.90°) East–West · District boundary (lat 15.40°) North–South</p>
        <table class="horeca-summary-table"><thead><tr>
            <th>Quadrant</th><th class="num">Zones</th><th class="num">Active</th><th class="num">HoReCas</th><th class="num">Alcohol</th><th class="num">Non-Alc</th><th class="num">Avg Priority</th>
        </tr></thead><tbody>`;
    // Total row first
    const totalAlc = data.filter(r => r.alcseg === 'Alcohol').length;
    html += `<tr style="background:var(--gray-50);font-weight:700"><td>All Goa</td><td class="num">${mesoZones.length}</td><td class="num">${activeZones.length}</td><td class="num">${total.toLocaleString()}</td><td class="num">${totalAlc.toLocaleString()}</td><td class="num">${(total - totalAlc).toLocaleString()}</td><td class="num">${avgPriority}</td></tr>`;
    for (const q of ['Q2','Q3','Q4','Q1']) {
        const qZones = mesoZones.filter(z => z.quad === q);
        const qActive = qZones.filter(z => z.density !== 'Dead');
        const qRecs = data.filter(r => r.quad === q);
        const qAlc = qRecs.filter(r => r.alcseg === 'Alcohol').length;
        const qAvg = qRecs.length ? (qRecs.reduce((s,r) => s + r.pscore, 0) / qRecs.length).toFixed(1) : '-';
        html += `<tr><td><strong>${q}</strong> ${QUAD_SHORT[q]}</td><td class="num">${qZones.length}</td><td class="num">${qActive.length}</td><td class="num">${qRecs.length.toLocaleString()}</td><td class="num">${qAlc.toLocaleString()}</td><td class="num">${(qRecs.length - qAlc).toLocaleString()}</td><td class="num">${qAvg}</td></tr>`;
    }
    html += `</tbody></table></div>`;

    // ── 2. Density Classification — Goa Level ──
    html += `<div class="horeca-summary-table-wrapper"><h3>Density Classification — All Goa</h3>
        <p class="hrc-table-note">HD = ≥50 HoReCas/zone · MD = 10–49 · LD = 4–9 · Dead = ≤3 (excluded from routing)</p>
        <table class="horeca-summary-table"><thead><tr>
            <th>Density</th><th class="num">Zones</th><th class="num">HoReCas</th><th class="num">%</th><th class="num">Alcohol</th><th class="num">Non-Alc</th><th class="num">Avg Priority</th>
        </tr></thead><tbody>`;
    html += densityTotalRow(data, mesoZones, 7);
    for (const d of DENSITY_ORDER) {
        const dZones = mesoZones.filter(z => z.density === d);
        const dRecs = data.filter(r => r.zdens === d);
        const dAlc = dRecs.filter(r => r.alcseg === 'Alcohol').length;
        const pct = total ? ((dRecs.length / total) * 100).toFixed(1) : '0';
        const dAvg = dRecs.length ? (dRecs.reduce((s,r) => s + r.pscore, 0) / dRecs.length).toFixed(1) : '-';
        const deadStyle = d === 'Dead' ? ' style="color:var(--gray-400)"' : '';
        html += `<tr${deadStyle}><td>${dDot(d)}${DENSITY_LABELS[d]}</td><td class="num">${dZones.length}</td><td class="num">${dRecs.length.toLocaleString()}</td><td class="num">${pct}%</td><td class="num">${dAlc.toLocaleString()}</td><td class="num">${(dRecs.length - dAlc).toLocaleString()}</td><td class="num">${dAvg}</td></tr>`;
    }
    html += `</tbody></table></div>`;

    // ── 3. Density Classification — Per Quadrant (collapsible) ──
    for (const q of ['Q2','Q3','Q4','Q1']) {
        const qZones = mesoZones.filter(z => z.quad === q);
        const qRecs = data.filter(r => r.quad === q);
        if (qRecs.length === 0) continue;
        const qActive = qZones.filter(z => z.density !== 'Dead').length;
        html += collapseOpen(`${QUAD_LABELS[q]} — Density`, `${qZones.length} zones · ${qRecs.length.toLocaleString()} HoReCas · ${qActive} active`, q === 'Q2');
        html += `<table class="horeca-summary-table"><thead><tr>
            <th>Density</th><th class="num">Zones</th><th class="num">HoReCas</th><th class="num">%</th><th class="num">Alcohol</th><th class="num">Non-Alc</th><th class="num">Avg Priority</th>
        </tr></thead><tbody>`;
        html += densityTotalRow(qRecs, qZones, 7);
        for (const d of DENSITY_ORDER) {
            const dZones = qZones.filter(z => z.density === d);
            const dRecs = qRecs.filter(r => r.zdens === d);
            if (dZones.length === 0 && dRecs.length === 0) continue;
            const dAlc = dRecs.filter(r => r.alcseg === 'Alcohol').length;
            const pct = qRecs.length ? ((dRecs.length / qRecs.length) * 100).toFixed(1) : '0';
            const dAvg = dRecs.length ? (dRecs.reduce((s,r) => s + r.pscore, 0) / dRecs.length).toFixed(1) : '-';
            const deadStyle = d === 'Dead' ? ' style="color:var(--gray-400)"' : '';
            html += `<tr${deadStyle}><td>${dDot(d)}${DENSITY_LABELS[d]}</td><td class="num">${dZones.length}</td><td class="num">${dRecs.length.toLocaleString()}</td><td class="num">${pct}%</td><td class="num">${dAlc.toLocaleString()}</td><td class="num">${(dRecs.length - dAlc).toLocaleString()}</td><td class="num">${dAvg}</td></tr>`;
        }
        html += `</tbody></table>`;
        html += collapseClose();
    }

    // ── 4. Segmentation Matrix — Alcohol Only (Quad × Density), collapsible per quadrant ──
    html += `<div class="horeca-summary-table-wrapper"><h3>Segmentation Matrix — Phase 1 (Alcohol Only)</h3>
        <p class="hrc-table-note">Quadrant × Density for Alcohol segment only (Confirmed + Likely + Inferred). Sorted by execution priority.</p>`;

    for (const q of ['Q2','Q3','Q4','Q1']) {
        const qAlcRecs = data.filter(r => r.quad === q && r.alcseg === 'Alcohol');
        if (qAlcRecs.length === 0) continue;
        const qAlcZones = new Set(qAlcRecs.map(r => r.h7)).size;
        const qHighC = qAlcRecs.filter(r => r.cont === 'High').length;

        html += collapseOpen(`${q} ${QUAD_SHORT[q]} — Alcohol`, `${qAlcRecs.length.toLocaleString()} HoReCas · ${qAlcZones} zones · ${qHighC} high contact`, q === 'Q2');
        html += `<table class="horeca-summary-table"><thead><tr>
            <th>Density</th><th class="num">Zones</th><th class="num">HoReCas</th><th class="num">High Contact</th><th class="num">Avg Priority</th>
        </tr></thead><tbody>`;
        // Total row
        const qAlcAvg = (qAlcRecs.reduce((s,r) => s + r.pscore, 0) / qAlcRecs.length).toFixed(1);
        html += `<tr style="background:var(--gray-50);font-weight:700"><td>Total</td><td class="num">${qAlcZones}</td><td class="num">${qAlcRecs.length.toLocaleString()}</td><td class="num">${qHighC.toLocaleString()}</td><td class="num">${qAlcAvg}</td></tr>`;
        for (const d of ['HD','MD','LD']) {
            const sRecs = qAlcRecs.filter(r => r.zdens === d);
            if (sRecs.length === 0) continue;
            const sZones = new Set(sRecs.map(r => r.h7)).size;
            const sHighC = sRecs.filter(r => r.cont === 'High').length;
            const sAvg = (sRecs.reduce((s,r) => s + r.pscore, 0) / sRecs.length).toFixed(1);
            html += `<tr><td>${dDot(d, 8)}${DENSITY_LABELS[d]}</td><td class="num">${sZones}</td><td class="num">${sRecs.length.toLocaleString()}</td><td class="num">${sHighC.toLocaleString()}</td><td class="num">${sAvg}</td></tr>`;
        }
        html += `</tbody></table>`;
        html += collapseClose();
    }
    html += `</div>`;

    // ── 5. Detailed HoReCa List per Segment (Quad × Density × Alcohol) ──
    html += `<div class="horeca-summary-table-wrapper"><h3>Detailed HoReCa List — By Segment</h3>
        <p class="hrc-table-note">Each segment shows individual HoReCas ranked by Priority Score within that segment.</p>`;

    for (const q of ['Q2','Q3','Q4','Q1']) {
        for (const d of ['HD','MD','LD']) {
            const segRecs = data.filter(r => r.quad === q && r.zdens === d && r.alcseg === 'Alcohol')
                .sort((a,b) => a.segrank - b.segrank);
            if (segRecs.length === 0) continue;
            const segHighC = segRecs.filter(r => r.cont === 'High').length;
            const segAvg = (segRecs.reduce((s,r) => s + r.pscore, 0) / segRecs.length).toFixed(1);

            html += collapseOpen(
                `${q} ${QUAD_SHORT[q]} · ${dDot(d, 8)}${d} · Alcohol`,
                `${segRecs.length.toLocaleString()} HoReCas · Avg ${segAvg} · ${segHighC} high contact`,
                false
            );
            html += `<div class="hrc-seg-list">`;
            segRecs.forEach((r, i) => {
                const alcBadge = r.alc === 'Confirmed' ? 'badge-alc-confirmed' : r.alc === 'Likely' ? 'badge-alc-confirmed' : 'badge-alc-possible';
                html += `<div class="hrc-seg-item">
                    <span class="hrc-seg-rank">${i + 1}</span>
                    <div class="hrc-seg-info">
                        <div class="hrc-seg-name">${escapeHtml(r.name)}</div>
                        <div class="hrc-seg-meta">${escapeHtml(r.city || '')} · ${escapeHtml(r.type)} · ${r.alc}${r.rat ? ' · ★' + r.rat : ''}</div>
                    </div>
                    <div class="hrc-seg-right">
                        <span class="hrc-seg-score">${r.pscore}</span>
                        <span class="hrc-seg-contact ${r.cont === 'High' ? 'contact-high' : r.cont === 'Medium' ? 'contact-med' : 'contact-low'}">${r.cont}</span>
                    </div>
                </div>`;
            });
            html += `</div>`;
            html += collapseClose();
        }
    }
    html += `</div>`;

    // ── 6. Further Insights — Good to Have (collapsible wrapper) ──
    html += collapseOpen('Further Insights — Good to Have', 'Active zones per quadrant, breakdowns by type, alcohol signal, size, contactability', false);

    // Active zones per quadrant
    for (const q of ['Q2','Q3','Q4','Q1']) {
        const qRecs = data.filter(r => r.quad === q && r.zdens !== 'Dead');
        if (qRecs.length === 0) continue;
        const zoneMap = {};
        qRecs.forEach(r => {
            const key = r.h7;
            if (!zoneMap[key]) zoneMap[key] = { name: '', count: 0, alc: 0, highC: 0, totalP: 0, density: '' };
            zoneMap[key].count++;
            zoneMap[key].name = r.zname || r.city;
            zoneMap[key].density = r.zdens;
            if (r.alcseg === 'Alcohol') zoneMap[key].alc++;
            if (r.cont === 'High') zoneMap[key].highC++;
            zoneMap[key].totalP += r.pscore;
        });
        const zoneList = Object.values(zoneMap)
            .map(z => ({ ...z, avg: (z.totalP / z.count).toFixed(1) }))
            .sort((a, b) => {
                const dOrder = { HD: 0, MD: 1, LD: 2 };
                if (dOrder[a.density] !== dOrder[b.density]) return dOrder[a.density] - dOrder[b.density];
                return b.count - a.count;
            });
        html += `<div class="horeca-summary-table-wrapper" style="box-shadow:none;padding:12px 0"><h3>${QUAD_LABELS[q]} — Active Zones</h3>
            <table class="horeca-summary-table"><thead><tr>
                <th>Zone</th><th>Density</th><th class="num">HoReCas</th><th class="num">Alcohol</th><th class="num">High Contact</th><th class="num">Avg Priority</th>
            </tr></thead><tbody>`;
        zoneList.forEach(z => {
            html += `<tr><td>${escapeHtml(z.name)}</td><td>${dDot(z.density, 8)}${z.density}</td><td class="num">${z.count}</td><td class="num">${z.alc}</td><td class="num">${z.highC}</td><td class="num">${z.avg}</td></tr>`;
        });
        html += `</tbody></table></div>`;
    }

    // Breakdown tables
    html += buildBreakdownTable('By HoReCa Type', groupBy(data, 'type'), ['Type', 'Count', '%', 'Avg Priority'], total);
    html += buildBreakdownTable('By Alcohol Signal', groupBy(data, 'alc'), ['Signal', 'Count', '%', 'Avg Priority'], total);
    html += buildBreakdownTable('By Size Tier', groupBy(data, 'size'), ['Tier', 'Count', '%', 'Avg Priority'], total);
    html += buildBreakdownTable('By Contactability', groupBy(data, 'cont'), ['Level', 'Count', '%', 'Avg Priority'], total);

    html += collapseClose();

    container.innerHTML = html;
}

function groupBy(data, key) {
    const groups = {};
    data.forEach(r => {
        const val = r[key] || 'Unknown';
        if (!groups[val]) groups[val] = { count: 0, totalPriority: 0 };
        groups[val].count++;
        groups[val].totalPriority += r.pscore;
    });
    return Object.entries(groups)
        .map(([k, v]) => ({ label: k, count: v.count, avgPriority: (v.totalPriority / v.count).toFixed(1) }))
        .sort((a, b) => b.count - a.count);
}

function buildBreakdownTable(title, rows, headers, total) {
    let html = `<div class="horeca-summary-table-wrapper"><h3>${title}</h3><table class="horeca-summary-table"><thead><tr>`;
    headers.forEach(h => { html += `<th${h !== headers[0] ? ' class="num"' : ''}>${h}</th>`; });
    html += '</tr></thead><tbody>';
    rows.forEach(r => {
        const pct = ((r.count / total) * 100).toFixed(1);
        html += `<tr><td>${escapeHtml(r.label)}</td><td class="num">${r.count}</td><td class="num">${pct}%</td><td class="num">${r.avgPriority}</td></tr>`;
    });
    html += '</tbody></table></div>';
    return html;
}

// ==================== HoReCa CRM ====================

let horecaCrmData = [];
// ── HoReCa Board (Kanban) ──
let horecaBoardLoaded = false;
let horecaBoardCounts = {};       // { status: count }
let horecaBoardCards = {};        // { status: [records] }
let horecaBoardPages = {};        // { status: current_page }
let horecaBoardTotalPages = {};   // { status: total_pages }
let horecaBoardAssignedFilter = '';  // current board assigned_to filter

const BOARD_STATUSES = [
    'No Status', 'De-listed', 'Call not answered', 'Call answered',
    'Pre-meeting mail to be sent', 'Pre-meeting mail sent',
    'Meeting aligned', 'Meeting done',
    'Post-meeting mail to be sent', 'Post meeting mail sent',
    'OB Form Opened', 'OB Form Filled'
];

const BOARD_STATUS_COLORS = {
    'No Status': '#9ca3af',
    'De-listed': '#991b1b',
    'Call not answered': '#9a3412',
    'Call answered': '#0d9488',
    'Pre-meeting mail to be sent': '#a78bfa',
    'Pre-meeting mail sent': '#8b5cf6',
    'Meeting aligned': '#f59e0b',
    'Meeting done': '#22c55e',
    'Post-meeting mail to be sent': '#c084fc',
    'Post meeting mail sent': '#7c3aed',
    'OB Form Opened': '#3b82f6',
    'OB Form Filled': '#059669',
};

const BOARD_PAGE_SIZE = 50;

async function initHoReCaBoard() {
    // Setup filter listener (only once)
    const boardAssignedSelect = document.getElementById('hboard-filter-assigned');
    if (boardAssignedSelect && !boardAssignedSelect.dataset.init) {
        boardAssignedSelect.dataset.init = '1';
        boardAssignedSelect.addEventListener('change', () => {
            horecaBoardAssignedFilter = boardAssignedSelect.value;
            horecaBoardLoaded = false; // force reload
            horecaBoardCards = {};
            horecaBoardPages = {};
            horecaBoardTotalPages = {};
            initHoReCaBoard();
        });
    }

    if (horecaBoardLoaded) return;
    const container = document.getElementById('horeca-board-container');
    container.innerHTML = '<div class="hcrm-dash-loading">Loading board...</div>';

    try {
        // Step 1: Fetch counts per status (with assigned_to filter if set)
        const summaryParams = horecaBoardAssignedFilter
            ? `?assigned_to=${encodeURIComponent(horecaBoardAssignedFilter)}`
            : '';
        const res = await fetch(`${API_BASE}/horeca/crm/summary${summaryParams}`);
        if (!res.ok) throw new Error('API error');
        const summary = await res.json();
        horecaBoardCounts = summary.statusCounts || {};

        // Populate board assignee filter dropdown from summary assignees
        if (summary.assignees && boardAssignedSelect && boardAssignedSelect.options.length <= 2) {
            summary.assignees.forEach(a => {
                const opt = document.createElement('option');
                opt.value = a;
                opt.textContent = a;
                boardAssignedSelect.appendChild(opt);
            });
        }

        // Render skeleton columns with counts immediately
        horecaBoardLoaded = true;
        renderBoardSkeleton();

        // Step 2: Lazy-load first page of cards for non-empty columns (parallel)
        const toLoad = BOARD_STATUSES.filter(s => (horecaBoardCounts[s] || 0) > 0);
        await Promise.all(toLoad.map(s => boardFetchColumn(s, 1)));
    } catch (e) {
        console.error('Failed to load board:', e);
        container.innerHTML = '<div class="card"><p>Failed to load board data.</p></div>';
    }
}

function renderBoardSkeleton() {
    const container = document.getElementById('horeca-board-container');
    let html = '';
    BOARD_STATUSES.forEach(status => {
        const count = horecaBoardCounts[status] || 0;
        const color = BOARD_STATUS_COLORS[status] || '#9ca3af';
        html += `<div class="horeca-board-column" id="board-col-${statusToId(status)}">
            <div class="horeca-board-col-header">
                <div class="horeca-board-col-dot" style="background:${color}"></div>
                <span class="horeca-board-col-title" title="${escapeHtml(status)}">${escapeHtml(status)}</span>
                <span class="horeca-board-col-count">${count.toLocaleString()}</span>
            </div>
            <div class="horeca-board-col-cards" id="board-cards-${statusToId(status)}">
                ${count > 0 ? '<div class="hcrm-dash-loading" style="font-size:12px;padding:12px">Loading...</div>' : '<div style="padding:12px;font-size:12px;color:#9ca3af;text-align:center">Empty</div>'}
            </div>
        </div>`;
    });
    container.innerHTML = html;
}

function statusToId(status) {
    return status.replace(/[^a-zA-Z0-9]/g, '-').toLowerCase();
}

async function boardFetchColumn(status, page) {
    const params = new URLSearchParams({ page, page_size: BOARD_PAGE_SIZE });
    params.set('status', status);
    if (horecaBoardAssignedFilter) params.set('assigned_to', horecaBoardAssignedFilter);

    try {
        const res = await fetch(`${API_BASE}/horeca/crm?${params}`);
        if (!res.ok) return;
        const data = await res.json();

        if (!horecaBoardCards[status]) horecaBoardCards[status] = [];
        horecaBoardCards[status] = horecaBoardCards[status].concat(data.records || []);
        horecaBoardPages[status] = data.page || page;
        horecaBoardTotalPages[status] = data.total_pages || 1;

        renderBoardColumn(status);
    } catch (e) {
        console.error(`Board: failed to load column "${status}":`, e);
    }
}

function renderBoardColumn(status) {
    const colId = statusToId(status);
    const cardsContainer = document.getElementById(`board-cards-${colId}`);
    if (!cardsContainer) return;

    const records = horecaBoardCards[status] || [];
    const color = BOARD_STATUS_COLORS[status] || '#9ca3af';
    const currentPage = horecaBoardPages[status] || 1;
    const totalPages = horecaBoardTotalPages[status] || 1;

    let html = '';
    records.forEach(r => {
        const typeIcon = (r.types || '').toLowerCase().includes('bar') ? '🍺' :
                         (r.types || '').toLowerCase().includes('cafe') ? '☕' :
                         (r.types || '').toLowerCase().includes('hotel') ? '🏨' : '🍽';
        const typeLabel = r.types ? r.types.split(',')[0].trim() : '';
        const city = r.city || '';
        const assignee = r.assigned_to || '';
        html += `<div class="horeca-board-card" style="border-left-color:${color}" onclick="boardClickCard('${escapeHtml(r.place_id)}','${escapeHtml(status)}')">
            <div class="horeca-board-card-name">${escapeHtml(r.name)}</div>
            <div class="horeca-board-card-meta">
                ${typeLabel ? `<span>${typeIcon} ${escapeHtml(typeLabel)}</span>` : ''}
                ${city ? `<span>· ${escapeHtml(city)}</span>` : ''}
                ${assignee ? `<span>· 👤 ${escapeHtml(assignee)}</span>` : ''}
            </div>
        </div>`;
    });

    if (currentPage < totalPages) {
        const remaining = (horecaBoardCounts[status] || 0) - records.length;
        html += `<div class="horeca-board-show-more" onclick="boardShowMore('${escapeHtml(status)}')">
            Load more (${remaining.toLocaleString()} remaining)
        </div>`;
    }

    cardsContainer.innerHTML = html;
}

function boardShowMore(status) {
    const nextPage = (horecaBoardPages[status] || 1) + 1;
    boardFetchColumn(status, nextPage);
}

function boardClickCard(placeId, status) {
    trackEvent('click', 'horeca', 'Open Record', `${placeId} (${status})`);
    // Switch to CRM sub-tab
    document.querySelectorAll('.horeca-sub-tab').forEach(t => t.classList.remove('active'));
    const crmTab = document.querySelector('.horeca-sub-tab[data-horeca="crm"]');
    if (crmTab) crmTab.classList.add('active');
    document.querySelectorAll('.horeca-content').forEach(c => c.classList.remove('active'));
    document.getElementById('horeca-crm').classList.add('active');

    if (!horecaCrmLoaded) initHoReCaCRM();

    // Set status filter and search for the record
    const statusFilter = document.getElementById('hcrm-filter-status');
    if (statusFilter) {
        statusFilter.value = status;
    }

    // Search by place_id in the CRM — update filter and fetch
    horecaCrmFilters.status = status;
    horecaCrmFilters.search = '';
    horecaCrmPage = 1;

    // Fetch CRM data with status filter, then select the record
    const params = new URLSearchParams({ page: 1, page_size: 50 });
    if (horecaCrmFilters.status) params.set('status', horecaCrmFilters.status);

    fetch(`${API_BASE}/horeca/crm?${params}`)
        .then(res => res.json())
        .then(data => {
            horecaCrmData = data.records || [];
            horecaCrmTotal = data.total || 0;
            horecaCrmTotalPages = data.total_pages || 1;
            renderHorecaCrmList();
            renderHorecaCrmPagination();
            // Try to select the clicked record
            const record = horecaCrmData.find(r => r.place_id === placeId);
            if (record) {
                selectHorecaFromMaster(placeId);
            }
        })
        .catch(err => console.error('Board→CRM navigation error:', err));
}

// ── HoReCa CRM ──
let horecaCrmTotal = 0;
let horecaCrmPage = 1;
let horecaCrmTotalPages = 0;
let currentHoreca = null;
let horecaCrmLoaded = false;
let horecaCrmFilters = { search: '', status: '', type: '', zone: '', city: '', assigned_to: '' };
let hcrmSearchTimeout = null;
let horecaDashboardLoaded = false;

function initHoReCaCRM() {
    // Setup search debounce
    const searchInput = document.getElementById('hcrm-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(hcrmSearchTimeout);
            hcrmSearchTimeout = setTimeout(() => {
                horecaCrmFilters.search = searchInput.value;
                horecaCrmPage = 1;
                fetchHoReCaCRMData();
            }, 300);
        });
    }

    // Setup filter listeners
    ['hcrm-filter-status', 'hcrm-filter-type', 'hcrm-filter-zone', 'hcrm-filter-assigned'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => {
                const keyMap = { 'hcrm-filter-assigned': 'assigned_to' };
                const key = keyMap[id] || id.replace('hcrm-filter-', '');
                horecaCrmFilters[key] = el.value;
                horecaCrmPage = 1;
                fetchHoReCaCRMData();
            });
        }
    });

    horecaCrmLoaded = true;
    fetchHoReCaCRMData();
}

async function fetchHoReCaCRMData() {
    const params = new URLSearchParams({
        page: horecaCrmPage,
        page_size: 50,
    });
    if (horecaCrmFilters.search) params.set('search', horecaCrmFilters.search);
    if (horecaCrmFilters.status) params.set('status', horecaCrmFilters.status);
    if (horecaCrmFilters.type) params.set('type', horecaCrmFilters.type);
    if (horecaCrmFilters.zone) params.set('zone', horecaCrmFilters.zone);
    if (horecaCrmFilters.city) params.set('city', horecaCrmFilters.city);
    if (horecaCrmFilters.assigned_to) params.set('assigned_to', horecaCrmFilters.assigned_to);

    try {
        const res = await fetch(`${API_BASE}/horeca/crm?${params}`);
        if (!res.ok) throw new Error('API error');
        const data = await res.json();

        horecaCrmData = data.records || [];
        horecaCrmTotal = data.total || 0;
        horecaCrmPage = data.page || 1;
        horecaCrmTotalPages = data.total_pages || 0;

        // Populate type/zone filters from full dataset options
        if (data.filter_options) {
            populateHorecaCrmDynamicFilters(data.filter_options);
        }

        renderHorecaCrmList();
        renderHorecaCrmPagination();
        document.getElementById('hcrm-result-count').textContent = `${horecaCrmTotal.toLocaleString()} records`;
    } catch (e) {
        console.error('Failed to fetch HoReCa CRM data:', e);
        document.getElementById('hcrm-list').innerHTML =
            '<div class="hcrm-error">Failed to load data. Try again.</div>';
    }
}

function populateHorecaCrmDynamicFilters(filterOptions) {
    // Populate from backend-provided full dataset options
    const typeSelect = document.getElementById('hcrm-filter-type');
    const zoneSelect = document.getElementById('hcrm-filter-zone');
    const assignedSelect = document.getElementById('hcrm-filter-assigned');

    if (typeSelect && typeSelect.options.length <= 1 && filterOptions.types) {
        filterOptions.types.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t;
            opt.textContent = t;
            typeSelect.appendChild(opt);
        });
    }
    if (zoneSelect && zoneSelect.options.length <= 1 && filterOptions.zones) {
        filterOptions.zones.forEach(z => {
            const opt = document.createElement('option');
            opt.value = z;
            opt.textContent = z;
            zoneSelect.appendChild(opt);
        });
    }
    if (assignedSelect && assignedSelect.options.length <= 2 && filterOptions.assignees) {
        filterOptions.assignees.forEach(a => {
            const opt = document.createElement('option');
            opt.value = a;
            opt.textContent = a;
            assignedSelect.appendChild(opt);
        });
    }
}

const HCRM_STATUS_COLORS = {
    'De-listed': 'hcrm-status-delisted',
    'Call not answered': 'hcrm-status-call-not-answered',
    'Call answered': 'hcrm-status-call-answered',
    'Pre-meeting mail to be sent': 'hcrm-status-pre-mail-pending',
    'Pre-meeting mail sent': 'hcrm-status-pre-mail',
    'Meeting aligned': 'hcrm-status-aligned',
    'Meeting done': 'hcrm-status-done',
    'Post-meeting mail to be sent': 'hcrm-status-post-mail-pending',
    'Post meeting mail sent': 'hcrm-status-post-mail',
    'OB Form Opened': 'hcrm-status-ob-opened',
    'OB Form Filled': 'hcrm-status-ob-filled',
};

function renderHorecaCrmList() {
    const container = document.getElementById('hcrm-list');
    if (!horecaCrmData.length) {
        container.innerHTML = '<div class="hcrm-empty-list">No records found</div>';
        return;
    }

    container.innerHTML = horecaCrmData.map(r => {
        const statusClass = HCRM_STATUS_COLORS[r.outreach_status] || 'hcrm-status-none';
        const statusLabel = r.outreach_status || 'No Status';
        const selected = currentHoreca && currentHoreca.place_id === r.place_id ? 'selected' : '';
        const zonePriority = r.zone_priority ? `#${r.zone_priority}` : '-';
        const entityScore = r.priority_score || '-';
        return `
            <div class="hcrm-card ${selected}" onclick="selectHorecaFromMaster('${escapeHtml(r.place_id)}')">
                <div class="hcrm-card-row1">
                    <span class="hcrm-card-name">${escapeHtml(r.name)}</span>
                    <span class="hcrm-card-status ${statusClass}">${escapeHtml(statusLabel)}</span>
                </div>
                <div class="hcrm-card-row2">
                    <span class="hcrm-card-zone" title="Meso Zone">${escapeHtml(r.zone || '-')}</span>
                    <span class="hcrm-card-score" title="Entity Priority Score">${escapeHtml(String(entityScore))}</span>
                    <span class="hcrm-card-zrank" title="Zone Priority">${escapeHtml(zonePriority)}</span>
                </div>
            </div>
        `;
    }).join('');
}

function toggleHorecaSection(section) {
    const el = document.getElementById(`hcrm-${section}-section`);
    if (el) el.classList.toggle('collapsed');
}

function selectHorecaFromMaster(placeId) {
    const record = horecaCrmData.find(r => r.place_id === placeId);
    if (!record) return;

    currentHoreca = record;

    // On mobile, hide master and show detail
    const master = document.getElementById('horeca-crm-master');
    const detail = document.getElementById('horeca-crm-detail');
    if (window.innerWidth < 1024) {
        master.classList.add('hidden-mobile');
        detail.classList.add('show-mobile');
    }

    // Show detail content
    document.getElementById('hcrm-empty').classList.add('hidden');
    document.getElementById('hcrm-details').classList.remove('hidden');

    // Populate header
    document.getElementById('hcrm-name').textContent = record.name;
    document.getElementById('hcrm-type-badge').textContent = record.type || 'Unknown';
    const statusBadge = document.getElementById('hcrm-status-badge');
    statusBadge.textContent = record.outreach_status || 'No Status';
    statusBadge.className = 'hcrm-status-badge ' + (HCRM_STATUS_COLORS[record.outreach_status] || 'hcrm-status-none');

    // Quick info
    document.getElementById('hcrm-address').textContent = record.address || 'No address';
    document.getElementById('hcrm-phone').textContent = record.phone || 'No phone';
    document.getElementById('hcrm-rating').textContent = record.rating ? `${record.rating} (${record.reviews || 0} reviews)` : 'No rating';

    // Maps link
    const mapsLink = document.getElementById('hcrm-maps-link');
    if (record.lat && record.lng) {
        mapsLink.href = `https://www.google.com/maps?q=${record.lat},${record.lng}`;
        mapsLink.style.display = 'inline-flex';
    } else {
        mapsLink.style.display = 'none';
    }

    // Status update form — pre-fill
    document.getElementById('hcrm-update-status').value = record.outreach_status || '';
    document.getElementById('hcrm-follow-up').value = record.follow_up_date || '';
    // Pre-fill updated_by from currentUser
    const updatedByInput = document.getElementById('hcrm-updated-by');
    if (currentUser && currentUser.name && !updatedByInput.value) {
        updatedByInput.value = currentUser.name;
    }

    // Pre-fill comment author from currentUser
    const commentAuthor = document.getElementById('hcrm-comment-author');
    if (currentUser && currentUser.name && !commentAuthor.value) {
        commentAuthor.value = currentUser.name;
    }
    document.getElementById('hcrm-new-comment').value = '';

    // Assignment
    const assigneeBadge = document.getElementById('hcrm-current-assignee');
    const assignmentHint = document.getElementById('hcrm-assignment-hint');
    const assignSelect = document.getElementById('hcrm-assign-to');
    if (record.assigned_to) {
        assigneeBadge.textContent = record.assigned_to;
        assigneeBadge.className = 'hcrm-assignee-badge assigned';
        assignmentHint.textContent = record.assigned_to;
        assignSelect.value = record.assigned_to;
    } else {
        assigneeBadge.textContent = 'Unassigned';
        assigneeBadge.className = 'hcrm-assignee-badge unassigned';
        assignmentHint.textContent = 'Unassigned';
        assignSelect.value = '';
    }
    renderHorecaAssignmentHistory(record);

    // Meetings
    renderHorecaMeetings(record);

    // Contacts
    document.getElementById('hcrm-owner-name').value = record.owner_name || '';
    document.getElementById('hcrm-owner-number').value = record.owner_number || '';
    document.getElementById('hcrm-spoc-name').value = record.spoc_name || '';
    document.getElementById('hcrm-spoc-number').value = record.spoc_number || '';
    document.getElementById('hcrm-spoc-designation').value = record.spoc_designation || '';
    document.getElementById('hcrm-outreach-email').value = record.outreach_email || '';
    document.getElementById('hcrm-bottles').value = record.bottles_per_week || '';

    // Comments timeline
    renderHorecaNotesTimeline(record.outreach_notes);

    // Update comments hint
    const notesEntries = record.outreach_notes ? record.outreach_notes.split('\n---\n').filter(Boolean) : [];
    document.getElementById('hcrm-comments-hint').textContent = notesEntries.length ? `${notesEntries.length} comment${notesEntries.length > 1 ? 's' : ''}` : 'Add notes and comments';

    // Priority details (meso zone only)
    document.getElementById('hcrm-prop-zone').textContent = record.zone || '-';
    document.getElementById('hcrm-prop-zone-priority').textContent = record.zone_priority ? `#${record.zone_priority}` : '-';
    document.getElementById('hcrm-prop-zone-density').textContent = record.zone_density || '-';
    document.getElementById('hcrm-prop-size').textContent = record.size || '-';
    document.getElementById('hcrm-prop-alcohol').textContent = record.alcohol || '-';
    document.getElementById('hcrm-prop-priority').textContent = record.priority_score || '-';
    document.getElementById('hcrm-prop-city').textContent = record.city || '-';
    document.getElementById('hcrm-prop-quadrant').textContent = record.zone_quadrant || '-';

    // Highlight selected card in list
    renderHorecaCrmList();
}

function renderHorecaMeetings(record) {
    const container = document.getElementById('hcrm-meetings-list');
    const hint = document.getElementById('hcrm-meetings-hint');

    // Find meetings for this HoReCa record from meetingsData
    const horecaKey = `HORECA:${record.place_id}`;
    const meetings = (meetingsData || []).filter(m => m.vpCode === horecaKey);

    let html = '';

    if (meetings.length > 0) {
        // Sort: scheduled first (by date), then completed/cancelled
        meetings.sort((a, b) => {
            if (a.status === 'scheduled' && b.status !== 'scheduled') return -1;
            if (a.status !== 'scheduled' && b.status === 'scheduled') return 1;
            return (b.eventDate || '').localeCompare(a.eventDate || '');
        });

        const scheduled = meetings.filter(m => m.status === 'scheduled');
        hint.textContent = scheduled.length ? `${scheduled.length} meeting(s) scheduled` : 'No upcoming meetings';

        meetings.forEach(m => {
            const dateObj = new Date(m.eventDate + 'T' + (m.eventTime || '10:00'));
            const dateStr = dateObj.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
            const timeStr = dateObj.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
            const statusCls = m.status === 'completed' ? 'completed' : (m.status === 'cancelled' ? 'cancelled' : '');
            const title = m.eventTitle || m.eventType || 'Meeting';

            html += `<div class="hcrm-meeting-card-item ${statusCls}">
                <div class="hcrm-mtg-row1">
                    <span class="hcrm-mtg-title">${escapeHtml(title)}</span>
                    <span class="hcrm-mtg-type-badge">${escapeHtml(m.status || 'scheduled')}</span>
                </div>
                <div class="hcrm-mtg-row2">
                    ${dateStr} at ${timeStr}${m.assignedTo ? ` &middot; ${escapeHtml(m.assignedTo)}` : ''}
                    ${m.notes ? `<br>${escapeHtml(m.notes.substring(0, 80))}` : ''}
                </div>
                ${m.status === 'scheduled' ? `<div class="hcrm-mtg-actions">
                    <button class="btn btn-outline btn-small" onclick="editMeeting('${m.meetingId}')">Edit</button>
                    <button class="btn btn-outline btn-small" onclick="markMeetingComplete('${m.meetingId}')">Complete</button>
                </div>` : ''}
            </div>`;
        });
    } else {
        // Also show follow-up date if no actual meetings
        const followUp = record.follow_up_date;
        if (followUp) {
            const fDate = new Date(followUp);
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const isPast = fDate < today;
            const isToday = fDate.toDateString() === today.toDateString();
            const label = isToday ? 'Today' : (isPast ? 'Overdue' : 'Upcoming');
            const cls = isToday ? 'hcrm-meeting-today' : (isPast ? 'hcrm-meeting-overdue' : 'hcrm-meeting-upcoming');

            html += `<div class="hcrm-meeting-card ${cls}">
                <div class="hcrm-meeting-date">${fDate.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}</div>
                <div class="hcrm-meeting-label">${label} follow-up</div>
            </div>`;
            hint.textContent = `Follow-up: ${fDate.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`;
        } else {
            hint.textContent = 'No meetings scheduled';
            html = '<p class="hint">No meetings scheduled yet</p>';
        }
    }

    container.innerHTML = html;
}

function showHorecaCrmMaster() {
    const master = document.getElementById('horeca-crm-master');
    const detail = document.getElementById('horeca-crm-detail');
    master.classList.remove('hidden-mobile');
    detail.classList.remove('show-mobile');
}

function renderHorecaNotesTimeline(notes) {
    const container = document.getElementById('hcrm-notes-timeline');
    if (!notes) {
        container.innerHTML = '<p class="hint">No comments yet</p>';
        return;
    }

    const entries = notes.split('\n---\n').filter(Boolean);
    container.innerHTML = entries.map((entry, i) => {
        // Parse [timestamp|author] content
        const match = entry.match(/^\[([^\]]+)\]\s*(.*)/s);
        if (match) {
            return `<div class="hcrm-note-entry${i === 0 ? ' latest' : ''}">
                <div class="hcrm-note-meta">${escapeHtml(match[1])}</div>
                <div class="hcrm-note-text">${escapeHtml(match[2])}</div>
            </div>`;
        }
        return `<div class="hcrm-note-entry"><div class="hcrm-note-text">${escapeHtml(entry)}</div></div>`;
    }).join('');
}

async function postHorecaComment() {
    const note = document.getElementById('hcrm-new-comment').value.trim();
    const author = document.getElementById('hcrm-comment-author').value.trim() || 'Team';
    if (!note || !currentHoreca) return;

    const body = {
        place_id: currentHoreca.place_id,
        note: note,
        updated_by: author,
    };

    try {
        const res = await fetch(`${API_BASE}/horeca/crm/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Failed to post comment');

        showToast('Comment posted');
        document.getElementById('hcrm-new-comment').value = '';

        // Refresh data and re-select
        await fetchHoReCaCRMData();
        const updated = horecaCrmData.find(r => r.place_id === currentHoreca.place_id);
        if (updated) selectHorecaFromMaster(updated.place_id);
    } catch (e) {
        showToast('Failed to post comment: ' + e.message);
    }
}

async function submitHorecaStatusUpdate() {
    if (!currentHoreca) return;

    const status = document.getElementById('hcrm-update-status').value;
    const followUp = document.getElementById('hcrm-follow-up').value;
    const updatedBy = document.getElementById('hcrm-updated-by').value.trim() || 'Team';

    if (!status) {
        showToast('Select a status');
        return;
    }

    const body = {
        place_id: currentHoreca.place_id,
        updated_by: updatedBy,
    };
    if (status) body.outreach_status = status;
    if (followUp) body.follow_up_date = followUp;

    try {
        const res = await fetch(`${API_BASE}/horeca/crm/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Update failed');

        showToast('Status updated');

        // Auto-create meeting for "Meeting aligned" or when follow-up date is set
        const shouldCreateMeeting = status === 'Meeting aligned' || followUp;
        if (shouldCreateMeeting) {
            await autoCreateHorecaMeeting(currentHoreca, status, followUp, updatedBy);
        }

        // Refresh data
        await fetchHoReCaCRMData();
        // Refresh meetings so the new meeting shows up
        if (shouldCreateMeeting) {
            meetingsData = await fetch(`${API_BASE}/meetings/all`).then(r => r.ok ? r.json() : []).catch(() => []);
            needsSchedulingCache = null;
        }

        // Re-select the same record
        const updated = horecaCrmData.find(r => r.place_id === currentHoreca.place_id);
        if (updated) selectHorecaFromMaster(updated.place_id);
    } catch (e) {
        showToast('Failed to update: ' + e.message);
    }
}

/**
 * Auto-create a meeting when HoReCa status changes to "Meeting aligned" or follow-up date is set.
 * Assigned to: HoReCa's assigned_to → fallback to the person updating.
 * Skips if a scheduled meeting already exists for the same HoReCa on the same date.
 */
async function autoCreateHorecaMeeting(horeca, status, followUpDate, updatedBy) {
    const placeId = horeca.place_id;
    const horecaKey = `HORECA:${placeId}`;

    // Determine meeting date: use follow-up date, or tomorrow if none
    let meetingDate = followUpDate;
    if (!meetingDate) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        meetingDate = tomorrow.toISOString().split('T')[0];
    }

    // Check if a scheduled meeting already exists for this HoReCa on this date
    const existingMeeting = (meetingsData || []).find(m =>
        m.vpCode === horecaKey && m.status === 'scheduled' && m.eventDate === meetingDate
    );
    if (existingMeeting) return; // Don't duplicate

    // Assigned to: HoReCa's assigned person → fallback to person updating
    const assignedTo = horeca.assigned_to || updatedBy;

    // Meeting title based on trigger
    const eventTitle = status === 'Meeting aligned' ? 'First Meeting' : 'Follow-up';

    const meetingData = {
        vp_code: horecaKey,
        vp_name: horeca.name || 'HoReCa',
        block: 'HoReCa',
        event_type: 'calendar_event',
        event_date: meetingDate,
        event_time: '10:00',
        duration_minutes: 60,
        assigned_to: assignedTo,
        notes: `Auto-created from CRM status: ${status}`,
        event_title: eventTitle,
        horeca_place_id: placeId,
        horeca_name: horeca.name || '',
    };

    try {
        const res = await fetch(`${API_BASE}/meetings/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(meetingData),
        });
        if (res.ok) {
            showToast(`Meeting "${eventTitle}" created for ${assignedTo} on ${meetingDate}`);
        }
    } catch (e) {
        console.error('Auto-create meeting failed:', e);
    }
}

// Assignment: team member list with localStorage persistence for custom names
const DEFAULT_TEAM_MEMBERS = ['Ayaan', 'Nupur', 'Aruna', 'Varsha', 'Chaithanya', 'Animesh', 'Vishwash'];

function getTeamMembers() {
    const custom = JSON.parse(localStorage.getItem('horecaCustomTeamMembers') || '[]');
    return [...DEFAULT_TEAM_MEMBERS, ...custom.filter(n => !DEFAULT_TEAM_MEMBERS.includes(n))];
}

function addTeamMember(name) {
    const custom = JSON.parse(localStorage.getItem('horecaCustomTeamMembers') || '[]');
    if (!custom.includes(name) && !DEFAULT_TEAM_MEMBERS.includes(name)) {
        custom.push(name);
        localStorage.setItem('horecaCustomTeamMembers', JSON.stringify(custom));
    }
    populateTeamDatalist();
}

function populateTeamDatalist() {
    const datalist = document.getElementById('hcrm-team-list');
    if (!datalist) return;
    datalist.innerHTML = getTeamMembers().map(n => `<option value="${n}">`).join('');
}

document.addEventListener('DOMContentLoaded', () => {
    populateTeamDatalist();
});

async function assignHoreca() {
    if (!currentHoreca) return;

    let assignee = document.getElementById('hcrm-assign-to').value.trim();
    if (!assignee) {
        showToast('Enter a team member name');
        return;
    }
    // Add new name to list if not already known
    addTeamMember(assignee);

    const author = document.getElementById('hcrm-updated-by').value.trim() || 'Team';
    const body = {
        place_id: currentHoreca.place_id,
        assigned_to: assignee,
        updated_by: author,
    };

    try {
        const res = await fetch(`${API_BASE}/horeca/crm/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Assignment failed');

        showToast(`Assigned to ${assignee}`);
        await fetchHoReCaCRMData();
        const updated = horecaCrmData.find(r => r.place_id === currentHoreca.place_id);
        if (updated) selectHorecaFromMaster(updated.place_id);
    } catch (e) {
        showToast('Failed to assign: ' + e.message);
    }
}

function renderHorecaAssignmentHistory(record) {
    const container = document.getElementById('hcrm-assignment-history');
    const historyStr = record.assignment_history || '';

    if (!historyStr.trim()) {
        container.innerHTML = '<p class="hint">No assignment history</p>';
        return;
    }

    const entries = historyStr.split('\n---\n').filter(Boolean);
    let html = '';
    for (const entry of entries) {
        // Format: [YYYY-MM-DD HH:MM|author] → assignee
        const match = entry.match(/^\[(.+?)\|(.+?)\]\s*→\s*(.+)$/);
        if (match) {
            const [, timestamp, author, assignee] = match;
            html += `<div class="hcrm-assign-entry">
                <strong>${escapeHtml(assignee)}</strong>
                <div class="hcrm-assign-meta">by ${escapeHtml(author)} on ${escapeHtml(timestamp)}</div>
            </div>`;
        } else {
            html += `<div class="hcrm-assign-entry">${escapeHtml(entry)}</div>`;
        }
    }
    container.innerHTML = html;
}

async function saveHorecaContacts() {
    if (!currentHoreca) return;

    const updatedBy = document.getElementById('hcrm-updated-by').value.trim() || 'Team';

    const body = {
        place_id: currentHoreca.place_id,
        owner_name: document.getElementById('hcrm-owner-name').value.trim(),
        owner_number: document.getElementById('hcrm-owner-number').value.trim(),
        spoc_name: document.getElementById('hcrm-spoc-name').value.trim(),
        spoc_number: document.getElementById('hcrm-spoc-number').value.trim(),
        spoc_designation: document.getElementById('hcrm-spoc-designation').value.trim(),
        outreach_email: document.getElementById('hcrm-outreach-email').value.trim(),
        bottles_per_week: document.getElementById('hcrm-bottles').value.trim(),
        updated_by: updatedBy,
    };

    try {
        const res = await fetch(`${API_BASE}/horeca/crm/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Save failed');

        showToast('Contacts saved');
        await fetchHoReCaCRMData();
        const updated = horecaCrmData.find(r => r.place_id === currentHoreca.place_id);
        if (updated) selectHorecaFromMaster(updated.place_id);
    } catch (e) {
        showToast('Failed to save: ' + e.message);
    }
}

function renderHorecaCrmPagination() {
    const container = document.getElementById('hcrm-pagination');
    if (horecaCrmTotalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '<div class="hcrm-pag-controls">';
    html += `<button class="btn btn-outline btn-small" ${horecaCrmPage <= 1 ? 'disabled' : ''} onclick="horecaCrmGoPage(${horecaCrmPage - 1})">Prev</button>`;
    html += `<span class="hcrm-pag-info">Page ${horecaCrmPage} of ${horecaCrmTotalPages}</span>`;
    html += `<button class="btn btn-outline btn-small" ${horecaCrmPage >= horecaCrmTotalPages ? 'disabled' : ''} onclick="horecaCrmGoPage(${horecaCrmPage + 1})">Next</button>`;
    html += '</div>';

    container.innerHTML = html;
}

function horecaCrmGoPage(page) {
    if (page < 1 || page > horecaCrmTotalPages) return;
    horecaCrmPage = page;
    fetchHoReCaCRMData();
}

// ── Add New HoReCa Lead ──

function openAddHorecaLeadModal() {
    const modal = document.getElementById('horeca-add-lead-modal');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    // Reset all form fields
    ['add-lead-name', 'add-lead-city', 'add-lead-address', 'add-lead-pincode',
     'add-lead-rating', 'add-lead-lat', 'add-lead-lng', 'add-lead-owner-name',
     'add-lead-owner-phone', 'add-lead-spoc-name', 'add-lead-spoc-phone',
     'add-lead-spoc-designation', 'add-lead-email', 'add-lead-bottles', 'add-lead-note'
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    document.getElementById('add-lead-type').value = '';
    document.getElementById('add-lead-assign').value = '';
    document.getElementById('add-lead-status').value = 'De-listed';
    document.getElementById('add-lead-serves-beer').checked = false;
    document.getElementById('add-lead-serves-wine').checked = false;

    // Show basic section, collapse others
    document.getElementById('add-lead-basic').classList.remove('collapsed');
    ['contacts', 'business', 'assignment', 'notes'].forEach(s => {
        document.getElementById('add-lead-' + s).classList.add('collapsed');
    });
}

function closeAddHorecaLeadModal() {
    document.getElementById('horeca-add-lead-modal').classList.add('hidden');
    document.body.style.overflow = '';
}

function toggleAddLeadSection(section) {
    const el = document.getElementById('add-lead-' + section);
    if (el) el.classList.toggle('collapsed');
}

async function submitNewHorecaLead() {
    const name = document.getElementById('add-lead-name').value.trim();
    if (!name) {
        showToast('Name is required', 'error');
        return;
    }

    const body = {
        name: name,
        type: document.getElementById('add-lead-type').value,
        address: document.getElementById('add-lead-address').value.trim(),
        city: document.getElementById('add-lead-city').value.trim(),
        pincode: document.getElementById('add-lead-pincode').value.trim(),
        rating: document.getElementById('add-lead-rating').value.trim(),
        lat: document.getElementById('add-lead-lat').value.trim(),
        lng: document.getElementById('add-lead-lng').value.trim(),
        owner_name: document.getElementById('add-lead-owner-name').value.trim(),
        owner_phone: document.getElementById('add-lead-owner-phone').value.trim(),
        spoc_name: document.getElementById('add-lead-spoc-name').value.trim(),
        spoc_phone: document.getElementById('add-lead-spoc-phone').value.trim(),
        spoc_designation: document.getElementById('add-lead-spoc-designation').value.trim(),
        email: document.getElementById('add-lead-email').value.trim(),
        serves_beer: document.getElementById('add-lead-serves-beer').checked,
        serves_wine: document.getElementById('add-lead-serves-wine').checked,
        bottles_per_week: document.getElementById('add-lead-bottles').value.trim(),
        status: document.getElementById('add-lead-status').value,
        assigned_to: document.getElementById('add-lead-assign').value,
        note: document.getElementById('add-lead-note').value.trim(),
    };

    showLoading(true);
    try {
        const res = await fetch(`${API_BASE}/horeca/crm/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to add lead');
        }

        showToast('Lead added successfully');
        closeAddHorecaLeadModal();
        await fetchHoReCaCRMData();
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    } finally {
        showLoading(false);
    }
}

window.openAddHorecaLeadModal = openAddHorecaLeadModal;
window.closeAddHorecaLeadModal = closeAddHorecaLeadModal;
window.toggleAddLeadSection = toggleAddLeadSection;
window.submitNewHorecaLead = submitNewHorecaLead;

// ── HoReCa Meeting Scheduling ──

function openHorecaMeetingModal() {
    if (!currentHoreca) {
        showToast('Select a HoReCa record first', 'error');
        return;
    }

    currentMeetingId = null;

    // Set HoReCa context
    document.getElementById('meeting-context').value = 'horeca';
    document.getElementById('meeting-horeca-place-id').value = currentHoreca.place_id;
    document.getElementById('meeting-modal-title').textContent = 'Schedule HoReCa Meeting';

    // Show HoReCa name, hide VP dropdown
    document.getElementById('meeting-vp-group').classList.add('hidden');
    document.getElementById('meeting-horeca-group').classList.remove('hidden');
    document.getElementById('meeting-horeca-name').value = currentHoreca.name || '';

    // HoReCa-specific meeting titles
    const titleSelect = document.getElementById('meeting-title');
    titleSelect.innerHTML = `
        <option value="First Meeting">First Meeting</option>
        <option value="Follow-up">Follow-up</option>
        <option value="Onboarding Discussion">Onboarding Discussion</option>
        <option value="Site Visit">Site Visit</option>
        <option value="custom">Custom...</option>
    `;
    document.getElementById('meeting-title-custom').classList.add('hidden');
    document.getElementById('meeting-title-custom').value = '';

    // Set defaults
    document.getElementById('meeting-event-type').value = 'calendar_event';
    document.getElementById('meeting-date').value = '';
    document.getElementById('meeting-time').value = '10:00';
    document.getElementById('meeting-duration').value = '60';
    document.getElementById('meeting-assigned').value = currentHoreca.assigned_to || '';
    document.getElementById('meeting-notes-input').value = '';

    const notifyCheckbox = document.getElementById('meeting-send-notifications');
    if (notifyCheckbox) notifyCheckbox.checked = false;

    // Show duration group
    const durGroup = document.getElementById('meeting-duration-group');
    if (durGroup) durGroup.style.display = '';
    const notifyGroup = document.getElementById('meeting-notify-group');
    if (notifyGroup) notifyGroup.style.display = '';

    document.getElementById('meeting-modal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

window.openHorecaMeetingModal = openHorecaMeetingModal;

// ── HoReCa Dashboard ──

async function initHoReCaDashboard() {
    const container = document.getElementById('hcrm-dashboard-content');
    container.innerHTML = '<div class="hcrm-dash-loading">Loading dashboard...</div>';

    try {
        const res = await fetch(`${API_BASE}/horeca/crm/summary`);
        if (!res.ok) throw new Error('API error');
        const data = await res.json();

        renderHorecaDashboard(data);
        horecaDashboardLoaded = true;
    } catch (e) {
        container.innerHTML = '<div class="card"><p>Failed to load dashboard</p></div>';
    }
}

function renderHorecaDashboard(data) {
    const container = document.getElementById('hcrm-dashboard-content');
    const statuses = [
        'No Status', 'De-listed', 'Call not answered',
        'Pre-meeting mail to be sent', 'Pre-meeting mail sent',
        'Meeting aligned', 'Meeting done',
        'Post-meeting mail to be sent', 'Post meeting mail sent',
        'OB Form Opened', 'OB Form Filled'
    ];
    const statusColors = {
        'No Status': '#9ca3af',
        'De-listed': '#991b1b',
        'Call not answered': '#9a3412',
        'Pre-meeting mail to be sent': '#a78bfa',
        'Pre-meeting mail sent': '#8b5cf6',
        'Meeting aligned': '#f59e0b',
        'Meeting done': '#22c55e',
        'Post-meeting mail to be sent': '#c084fc',
        'Post meeting mail sent': '#7c3aed',
        'OB Form Opened': '#3b82f6',
        'OB Form Filled': '#059669',
    };

    // Funnel
    let funnelHtml = '<div class="card"><h2>Outreach Funnel</h2><div class="hcrm-funnel">';
    statuses.forEach(s => {
        const count = (data.statusCounts || {})[s] || 0;
        const color = statusColors[s] || '#9ca3af';
        funnelHtml += `
            <div class="hcrm-funnel-card" style="border-left: 4px solid ${color}">
                <div class="hcrm-funnel-count">${count.toLocaleString()}</div>
                <div class="hcrm-funnel-label">${s}</div>
            </div>
        `;
    });
    funnelHtml += '</div></div>';

    // Status × Type table
    let typeTableHtml = '<div class="card"><h2>Status by Type</h2><div class="hcrm-table-scroll"><table class="hcrm-table"><thead><tr><th>Type</th>';
    statuses.forEach(s => { typeTableHtml += `<th>${s}</th>`; });
    typeTableHtml += '</tr></thead><tbody>';
    const byType = data.byType || {};
    Object.keys(byType).sort().forEach(type => {
        typeTableHtml += `<tr><td>${escapeHtml(type)}</td>`;
        statuses.forEach(s => {
            typeTableHtml += `<td class="num">${byType[type][s] || 0}</td>`;
        });
        typeTableHtml += '</tr>';
    });
    typeTableHtml += '</tbody></table></div></div>';

    // Status × Zone table (top 20)
    let zoneTableHtml = '<div class="card"><h2>Status by Zone (Top 20)</h2><div class="hcrm-table-scroll"><table class="hcrm-table"><thead><tr><th>Zone</th>';
    statuses.forEach(s => { zoneTableHtml += `<th>${s}</th>`; });
    zoneTableHtml += '<th>Total</th></tr></thead><tbody>';
    const byZone = data.byZone || {};
    Object.keys(byZone).forEach(zone => {
        const total = Object.values(byZone[zone]).reduce((a, b) => a + b, 0);
        zoneTableHtml += `<tr><td>${escapeHtml(zone)}</td>`;
        statuses.forEach(s => {
            zoneTableHtml += `<td class="num">${byZone[zone][s] || 0}</td>`;
        });
        zoneTableHtml += `<td class="num"><strong>${total}</strong></td></tr>`;
    });
    zoneTableHtml += '</tbody></table></div></div>';

    // Recent activity
    let recentHtml = '<div class="card"><h2>Recent Activity</h2>';
    if (data.recentUpdates && data.recentUpdates.length) {
        recentHtml += '<div class="hcrm-recent-list">';
        data.recentUpdates.forEach(r => {
            const statusClass = HCRM_STATUS_COLORS[r.status] || 'hcrm-status-none';
            recentHtml += `
                <div class="hcrm-recent-item">
                    <div class="hcrm-recent-name">${escapeHtml(r.name)}</div>
                    <span class="hcrm-card-status ${statusClass}">${escapeHtml(r.status)}</span>
                    <div class="hcrm-recent-meta">${escapeHtml(r.updated_by || '')} &middot; ${escapeHtml(r.updated)}</div>
                </div>
            `;
        });
        recentHtml += '</div>';
    } else {
        recentHtml += '<p class="hint">No recent activity</p>';
    }
    recentHtml += '</div>';

    container.innerHTML = funnelHtml + typeTableHtml + zoneTableHtml + recentHtml;
}


// ==================== Learning Tab ====================

const TRAINING_MODULES = [
    { id: 0, title: 'Basic Training', subtitle: 'DRS Foundations', chapters: 6, time: '~20 min', status: 'available' },
    { id: 1, title: 'Consumer', subtitle: 'The Consumer Journey', chapters: 4, time: '~15 min', status: 'available' },
    { id: 2, title: 'Collection Eco System', subtitle: 'How Collection Works', chapters: 7, time: '~30 min', status: 'available' },
    { id: 3, title: 'Collection Devices', subtitle: 'Hardware & Tools', chapters: 5, time: '~25 min', status: 'available' },
    { id: 4, title: 'Handlers', subtitle: 'Field Operations', chapters: 0, time: 'TBD', status: 'coming-soon' },
    { id: 5, title: 'Reverse Logistics', subtitle: 'Material Flow', chapters: 0, time: 'TBD', status: 'coming-soon' },
    { id: 6, title: 'CPC', subtitle: 'Central Processing', chapters: 0, time: 'TBD', status: 'coming-soon' },
];

function getTrainingStorageKey() {
    // Per-user localStorage key to prevent cross-user data contamination
    const email = (currentUser && currentUser.email) ? currentUser.email : 'anonymous';
    return `goa_drs_training_${email}`;
}

function getTrainingState() {
    try {
        const key = getTrainingStorageKey();
        const state = JSON.parse(localStorage.getItem(key));
        return state || {};
    } catch (e) {
        return {};
    }
}

async function hydrateTrainingFromServer() {
    try {
        const resp = await fetch(`${API_BASE}/training/progress`, { credentials: 'include' });
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.found && data.progress_json && data.progress_json !== '{}') {
            const key = getTrainingStorageKey();
            const serverState = JSON.parse(data.progress_json);
            const localState = getTrainingState();
            const localXP = localState.trainee ? (localState.trainee.totalXP || 0) : 0;
            const serverXP = serverState.trainee ? (serverState.trainee.totalXP || 0) : 0;
            if (serverXP > localXP) {
                localStorage.setItem(key, data.progress_json);
            }
        }
    } catch (e) { /* silent — localStorage still works */ }
}

async function initLearningTab() {
    await hydrateTrainingFromServer();
    const rawState = getTrainingState();
    const modules = rawState.modules || {};
    const trainee = rawState.trainee || {};
    const grid = document.getElementById('learning-grid');
    if (!grid) return;

    // Use trainee totals (calculated by gamification engine)
    const totalXP = trainee.totalXP || 0;
    const totalStars = trainee.totalStars || 0;
    let modulesCompleted = 0;

    TRAINING_MODULES.forEach(mod => {
        const modState = modules[mod.id];
        if (modState && modState.status === 'completed') modulesCompleted++;
    });

    // Update header stats
    const xpEl = document.getElementById('learning-total-xp');
    const doneEl = document.getElementById('learning-modules-done');
    const starsEl = document.getElementById('learning-total-stars');
    if (xpEl) xpEl.textContent = totalXP;
    if (doneEl) doneEl.textContent = `${modulesCompleted}/7`;
    if (starsEl) starsEl.textContent = totalStars;

    // Render module cards
    let html = '';
    TRAINING_MODULES.forEach(mod => {
        const modState = modules[mod.id] || {};
        const isCompleted = modState.status === 'completed';
        const isComingSoon = mod.status === 'coming-soon';

        // Calculate progress from chapters
        const chapters = modState.chapters || {};
        const completedChapters = Object.values(chapters).filter(c => c.completed).length;
        const progress = mod.chapters > 0 ? Math.round((completedChapters / mod.chapters) * 100) : 0;
        const hasStarted = completedChapters > 0 || isCompleted;

        // Module XP and stars from chapter data
        const modXP = Object.values(chapters).reduce((sum, ch) => sum + (ch.xp || 0), 0);
        const modStars = Object.values(chapters).reduce((sum, ch) => sum + (ch.stars || 0), 0);

        // Sequential locking: module N requires module N-1 completed
        const isLocked = !isComingSoon && mod.id > 0 &&
            (!modules[mod.id - 1] || modules[mod.id - 1].status !== 'completed');

        let statusClass = '';
        let actionHtml = '';

        if (isComingSoon) {
            statusClass = 'coming-soon';
            actionHtml = '<span class="module-action locked">Coming Soon</span>';
        } else if (isLocked) {
            statusClass = 'locked';
            actionHtml = `<span class="module-action locked">Complete Module ${mod.id - 1} first</span>`;
        } else if (isCompleted) {
            statusClass = 'completed';
            actionHtml = '<span class="module-action done">Completed</span>';
        } else if (hasStarted) {
            actionHtml = '<span class="module-action continue">Continue</span>';
        } else {
            actionHtml = '<span class="module-action start">Start</span>';
        }

        const clickable = !isComingSoon && !isLocked;
        const progressBarHtml = clickable ? `
            <div class="module-progress-bar">
                <div class="module-progress-fill" style="width: ${isCompleted ? 100 : progress}%"></div>
            </div>
        ` : '';

        html += `
            <div class="module-card ${statusClass}" ${clickable ? `onclick="openTrainingModule(${mod.id})"` : ''}>
                <div class="module-badge">${mod.id}</div>
                <div class="module-card-body">
                    <div class="module-card-title">${escapeHtml(mod.title)}</div>
                    <div class="module-card-subtitle">${escapeHtml(mod.subtitle)}</div>
                    <div class="module-card-meta">
                        <span>${mod.chapters > 0 ? mod.chapters + ' chapters' : '--'}</span>
                        <span>${mod.time}</span>
                        ${modXP ? `<span>${modXP} XP</span>` : ''}
                        ${modStars ? `<span>${modStars} ★</span>` : ''}
                    </div>
                    ${progressBarHtml}
                    ${actionHtml}
                </div>
            </div>
        `;
    });

    grid.innerHTML = html;

    // Sync progress to backend and load leaderboard
    syncTrainingProgress(rawState);
    loadLeaderboard();
}

function openTrainingModule(moduleId) {
    window.open(`/static/training/module-${moduleId}/index.html?storageKey=${encodeURIComponent(getTrainingStorageKey())}`, '_blank');
}

// ==================== Training Progress Sync & Leaderboard ====================

let lastSyncTime = 0;

function syncTrainingProgress(rawState) {
    // Debounce: skip if last sync < 30s ago
    const now = Date.now();
    if (now - lastSyncTime < 30000) return;
    lastSyncTime = now;

    const modules = rawState.modules || {};
    const trainee = rawState.trainee || {};

    // Count completed modules and chapters
    let modulesCompleted = 0;
    let chaptersCompleted = 0;
    let currentModule = 0;
    for (const [modId, mod] of Object.entries(modules)) {
        if (mod.status === 'completed') modulesCompleted++;
        const chCount = Object.values(mod.chapters || {}).filter(c => c.completed).length;
        chaptersCompleted += chCount;
        if (chCount > 0) currentModule = Math.max(currentModule, parseInt(modId));
    }

    const payload = {
        total_xp: trainee.totalXP || 0,
        total_stars: trainee.totalStars || 0,
        modules_completed: modulesCompleted,
        chapters_completed: chaptersCompleted,
        total_time_seconds: trainee.totalTimeSeconds || 0,
        current_module: currentModule,
        progress_json: JSON.stringify(rawState)
    };

    // Fire-and-forget
    fetch(`${API_BASE}/training/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload)
    }).catch(() => {}); // Silently ignore errors
}

async function loadLeaderboard() {
    const container = document.getElementById('leaderboard-container');
    if (!container) return;

    try {
        const resp = await fetch(`${API_BASE}/training/leaderboard`, { credentials: 'include' });
        if (!resp.ok) { container.innerHTML = '<p class="text-muted">Leaderboard unavailable</p>'; return; }
        const data = await resp.json();

        if (!data.leaderboard || data.leaderboard.length === 0) {
            container.innerHTML = '<p class="text-muted">No trainees yet. Complete a chapter to appear!</p>';
            return;
        }

        const userEmail = currentUser ? currentUser.email : '';
        const medals = ['🥇', '🥈', '🥉'];

        let html = '<div class="leaderboard-list">';
        data.leaderboard.forEach(entry => {
            const isMe = entry.email === userEmail;
            const rankDisplay = entry.rank <= 3 ? medals[entry.rank - 1] : `#${entry.rank}`;
            html += `
                <div class="leaderboard-row ${isMe ? 'leaderboard-me' : ''} ${entry.rank <= 3 ? 'leaderboard-top' : ''}">
                    <span class="leaderboard-rank">${rankDisplay}</span>
                    <span class="leaderboard-name">${escapeHtml(entry.name)}</span>
                    <span class="leaderboard-stats">
                        <span class="leaderboard-xp">${entry.xp} XP</span>
                        <span class="leaderboard-stars">${entry.stars} ★</span>
                        <span class="leaderboard-modules">${entry.modules}/${TRAINING_MODULES.length} modules</span>
                    </span>
                </div>
            `;
        });
        html += '</div>';

        html += `<p class="leaderboard-footer">${data.totalTrainees} trainees</p>`;

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p class="text-muted">Leaderboard unavailable</p>';
    }
}

// Make learning functions globally accessible
window.openTrainingModule = openTrainingModule;

// ==================== More Bottom Sheet ====================

function toggleMoreSheet() {
    const overlay = document.getElementById('more-sheet-overlay');
    if (!overlay) return;

    if (overlay.classList.contains('hidden')) {
        // Open: update active states in sheet
        const activeTab = localStorage.getItem('activeTab');
        overlay.querySelectorAll('.more-sheet-item').forEach(item => {
            item.classList.toggle('active', item.dataset.tab === activeTab);
        });
        overlay.classList.remove('hidden');
    } else {
        overlay.classList.add('hidden');
    }
}

function closeMoreSheet(event) {
    // Close when clicking overlay background (not the sheet itself)
    const overlay = document.getElementById('more-sheet-overlay');
    if (overlay && event.target === overlay) {
        overlay.classList.add('hidden');
    }
}

function selectMoreItem(tabId) {
    const overlay = document.getElementById('more-sheet-overlay');
    if (overlay) overlay.classList.add('hidden');
    switchToTab(tabId);
}

// Make more menu functions globally accessible
window.toggleMoreSheet = toggleMoreSheet;
window.closeMoreSheet = closeMoreSheet;
window.selectMoreItem = selectMoreItem;

// ==================== RVM Deployment ====================

let depData = null;
let rvmDeployMapInstance = null;
let depDeadline = '2026-07-15';
let depPlanTotal = 301;
let depFilteredLocs = null;

// ── Activity Log ─────────────────────────────────────────────────────────────

const _ACT_BADGE_CLASS = { login:'b-login', page_view:'b-page', scroll:'b-scroll', click:'b-click' };
const _ACT_BADGE_LABEL = { login:'Login', page_view:'Page View', scroll:'Scroll', click:'Click' };
const _ACT_PAGE_COLORS = {
    vps:'#388bfd', dashboard:'#3fb950', meetings:'#f0883e',
    horeca:'#39c5cf', escalation:'#bc8cff', today:'#7d8590',
    learning:'#e3b341', activity:'#f85149', ct:'#3fb950',
};

async function loadActivityLog() {
    const el = document.getElementById('dash-activity-content');
    if (!el) return;
    el.innerHTML = activityShell();
    document.getElementById('act-feed-tab').addEventListener('click', () => actSwitchTab('feed'));
    document.getElementById('act-profiles-tab').addEventListener('click', () => actSwitchTab('profiles'));

    // Load feed
    try {
        const res = await fetch(`${API_BASE}/analytics/log?limit=300`);
        if (!res.ok) throw new Error('Failed');
        const { events } = await res.json();
        renderActivityFeed(events || []);
    } catch (e) {
        document.getElementById('act-feed-body').innerHTML = `<div style="padding:24px;color:#f85149;font-size:13px">Failed to load activity log: ${e.message}</div>`;
    }

    // Load profiles
    try {
        const res = await fetch(`${API_BASE}/analytics/profiles`);
        if (!res.ok) throw new Error('Failed');
        const { profiles } = await res.json();
        renderActProfiles(profiles || []);
    } catch (e) {
        document.getElementById('act-profiles-body').innerHTML = `<div style="padding:24px;color:#f85149;font-size:13px">Failed to load profiles: ${e.message}</div>`;
    }
}

function actSwitchTab(tab) {
    ['feed','profiles'].forEach(t => {
        document.getElementById(`act-${t}-tab`).classList.toggle('act-tab-active', t === tab);
        const panel = document.getElementById(`act-${t}-panel`);
        if (panel) panel.style.display = t === tab ? '' : 'none';
    });
}

function activityShell() {
    return `<div style="background:#FFFFFF;min-height:600px;border-radius:12px;overflow:hidden;margin:0 0 24px;border:1px solid #E2E8F0;box-shadow:0 1px 4px rgba(0,0,0,.06)">
  <!-- Header -->
  <div style="padding:18px 24px 14px;border-bottom:1px solid #E2E8F0;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;background:#FAFBFC">
    <div style="display:flex;align-items:center;gap:12px">
      <div style="width:36px;height:36px;background:linear-gradient(135deg,#1e6b5c,#2d8a78);border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:16px">📊</div>
      <div>
        <div style="font-size:16px;font-weight:700;color:#111827;letter-spacing:-.02em">User Analytics</div>
        <div style="font-size:11px;color:#6B7280;margin-top:1px">Who's using the dashboard, when, and how</div>
      </div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <div style="display:flex;align-items:center;gap:5px;background:rgba(5,150,105,.08);border:1px solid rgba(5,150,105,.2);border-radius:20px;padding:4px 10px;font-size:11px;font-weight:700;color:#059669;letter-spacing:.04em">
        <div style="width:6px;height:6px;background:#059669;border-radius:50%;animation:actPulse 1.8s ease-in-out infinite"></div>LIVE
      </div>
      <div style="background:#FEF3C7;border:1px solid #FCD34D;border-radius:20px;padding:4px 10px;font-size:11px;color:#92400E;font-weight:600">🔒 Only visible to you</div>
    </div>
  </div>
  <!-- KPIs -->
  <div id="act-kpis" style="padding:16px 24px;border-bottom:1px solid #E2E8F0;display:grid;grid-template-columns:repeat(4,1fr);gap:10px;background:#FAFBFC">
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;padding:14px 16px;box-shadow:0 1px 2px rgba(0,0,0,.04)"><div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;margin-bottom:6px">Total events</div><div style="font-size:28px;font-weight:800;color:#111827;letter-spacing:-.03em;line-height:1" id="act-kpi-total">—</div></div>
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;padding:14px 16px;box-shadow:0 1px 2px rgba(0,0,0,.04)"><div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;margin-bottom:6px">Total logins</div><div style="font-size:28px;font-weight:800;color:#111827;letter-spacing:-.03em;line-height:1" id="act-kpi-logins">—</div></div>
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;padding:14px 16px;box-shadow:0 1px 2px rgba(0,0,0,.04)"><div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;margin-bottom:6px">Active users</div><div style="font-size:28px;font-weight:800;color:#111827;letter-spacing:-.03em;line-height:1" id="act-kpi-users">—</div></div>
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;padding:14px 16px;box-shadow:0 1px 2px rgba(0,0,0,.04)"><div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;margin-bottom:6px">Last activity</div><div style="font-size:13px;font-weight:600;color:#111827;margin-top:5px;line-height:1.3" id="act-kpi-last">—</div></div>
  </div>
  <!-- Tab bar -->
  <div style="display:flex;gap:0;padding:0 24px;border-bottom:1px solid #E2E8F0;background:#FFFFFF">
    <button id="act-feed-tab" class="act-tab-active" style="background:none;border:none;border-bottom:2px solid #1e6b5c;color:#1e6b5c;font-size:13px;font-weight:700;padding:11px 16px 10px;cursor:pointer;font-family:inherit;margin-bottom:-1px;transition:color .15s">Activity Feed</button>
    <button id="act-profiles-tab" style="background:none;border:none;border-bottom:2px solid transparent;color:#6B7280;font-size:13px;font-weight:500;padding:11px 16px 10px;cursor:pointer;font-family:inherit;margin-bottom:-1px;transition:color .15s">User Profiles</button>
  </div>
  <!-- Feed panel -->
  <div id="act-feed-panel" style="background:#FFFFFF">
    <div id="act-feed-filters" style="display:flex;gap:8px;padding:12px 24px;border-bottom:1px solid #F3F4F6;flex-wrap:wrap;align-items:center;background:#FAFBFC">
      <span style="font-size:10px;font-weight:700;color:#9CA3AF;text-transform:uppercase;letter-spacing:.08em">Filter by</span>
      <select id="act-filter-user" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:7px;color:#374151;font-size:12px;font-family:inherit;padding:5px 9px;cursor:pointer;outline:none"><option value="">All users</option></select>
      <select id="act-filter-type" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:7px;color:#374151;font-size:12px;font-family:inherit;padding:5px 9px;cursor:pointer;outline:none">
        <option value="">All actions</option><option value="login">Login</option><option value="page_view">Page View</option><option value="scroll">Scroll</option><option value="click">Click</option>
      </select>
      <select id="act-filter-device" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:7px;color:#374151;font-size:12px;font-family:inherit;padding:5px 9px;cursor:pointer;outline:none">
        <option value="">All devices</option><option value="Mobile">Mobile</option><option value="Desktop">Desktop</option>
      </select>
    </div>
    <div style="overflow-x:auto;padding:0 24px 24px">
      <table style="width:100%;border-collapse:collapse;min-width:820px;margin-top:14px;font-size:12px" id="act-table">
        <thead>
          <tr style="border-bottom:2px solid #F3F4F6">
            ${['Date & Time','User','Action','Details','Device','IP'].map(h => `<th style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9CA3AF;padding:0 10px 12px;text-align:left;white-space:nowrap">${h}</th>`).join('')}
          </tr>
        </thead>
        <tbody id="act-feed-body"><tr><td colspan="6" style="padding:40px;color:#9CA3AF;text-align:center;font-size:13px">Loading...</td></tr></tbody>
      </table>
    </div>
  </div>
  <!-- Profiles panel -->
  <div id="act-profiles-panel" style="display:none;background:#F8FAFC">
    <div style="padding:14px 24px;border-bottom:1px solid #E2E8F0;background:#FFFFFF">
      <div style="font-size:13px;color:#6B7280">Engagement profile per team member · All time</div>
    </div>
    <div id="act-profiles-body" style="padding:18px 24px 24px;display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px">
      <div style="color:#6B7280;font-size:13px;padding:16px">Loading profiles...</div>
    </div>
  </div>
</div>
<style>
  @keyframes actPulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}
  .act-tab-active{color:#1e6b5c!important;border-bottom-color:#1e6b5c!important;font-weight:700!important}
</style>`;
}

function renderActivityFeed(events) {
    // Compute KPIs
    document.getElementById('act-kpi-total').textContent = events.length;
    const logins = events.filter(e => e.Event_Type === 'login').length;
    document.getElementById('act-kpi-logins').textContent = logins;
    const users = new Set(events.map(e => e.User_Email).filter(Boolean));
    document.getElementById('act-kpi-users').textContent = users.size;
    const last = events[0];
    document.getElementById('act-kpi-last').textContent = last ? `${last.User_Name || last.User_Email} · ${(last.Timestamp || '').slice(11, 16)}` : '—';

    // Populate user filter
    const userSel = document.getElementById('act-filter-user');
    [...users].sort().forEach(u => {
        const o = document.createElement('option'); o.value = u; o.textContent = u; userSel.appendChild(o);
    });

    function applyFilters() {
        const fu = userSel.value;
        const ft = document.getElementById('act-filter-type').value;
        const fd = document.getElementById('act-filter-device').value;
        const filtered = events.filter(e =>
            (!fu || e.User_Email === fu) &&
            (!ft || e.Event_Type === ft) &&
            (!fd || e.Device_Type === fd)
        );
        paintFeedRows(filtered);
    }

    ['act-filter-user','act-filter-type','act-filter-device'].forEach(id =>
        document.getElementById(id).addEventListener('change', applyFilters)
    );
    paintFeedRows(events);
}

function paintFeedRows(events) {
    const tbody = document.getElementById('act-feed-body');
    if (!events.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="padding:40px;color:#9CA3AF;text-align:center;font-size:13px">No events match the filters</td></tr>`;
        return;
    }

    const badgeColors = { login:'rgba(5,150,105,.1)', page_view:'rgba(37,99,235,.1)', scroll:'rgba(124,58,237,.1)', click:'rgba(217,119,6,.1)', dwell:'rgba(14,165,233,.1)' };
    const badgeText  = { login:'#059669', page_view:'#2563EB', scroll:'#7C3AED', click:'#D97706', dwell:'#0EA5E9' };
    const badgeLabel = { login:'Login', page_view:'Page View', scroll:'Scroll', click:'Click', dwell:'Time Spent' };

    const initials = name => (name || '??').split(' ').map(w => w[0]).slice(0,2).join('').toUpperCase();
    const avatarColor = email => {
        const colors = ['#1e6b5c','#2563eb','#7c3aed','#d97706','#dc2626','#0891b2','#065f46'];
        let h = 0; for (const c of (email||'')) h = (h*31 + c.charCodeAt(0)) & 0xffff;
        return colors[h % colors.length];
    };

    let lastDate = '';
    const rows = [];
    events.forEach(e => {
        const ts = (e.Timestamp || '');
        const dateStr = ts.slice(0, 10);
        if (dateStr !== lastDate) {
            lastDate = dateStr;
            const d = new Date(dateStr + 'T00:00:00');
            const label = isNaN(d) ? dateStr : d.toLocaleDateString('en-IN', { weekday:'long', day:'numeric', month:'short', year:'numeric' });
            rows.push(`<tr><td colspan="6" style="padding:16px 10px 6px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#9CA3AF;pointer-events:none;border-bottom:1px solid #F9FAFB">— ${label}</td></tr>`);
        }
        const ev = e.Event_Type || '';
        const bg = badgeColors[ev] || 'rgba(156,163,175,.1)';
        const tc = badgeText[ev] || '#6B7280';
        const lbl = badgeLabel[ev] || ev;
        const details = (() => {
            if (ev === 'login') return 'Session started';
            if (ev === 'page_view') return `Opened <span style="color:${_ACT_PAGE_COLORS[e.Page]||'#1e6b5c'};font-weight:600">${e.Page||''}</span>`;
            if (ev === 'scroll') return `Scrolled <b style="color:#7C3AED">${e.Value}%</b> down <span style="color:#6B7280">${e.Page}</span>`;
            if (ev === 'dwell') return `Spent <b style="color:#0EA5E9">${e.Value}s</b> on <span style="color:${_ACT_PAGE_COLORS[e.Page]||'#1e6b5c'};font-weight:600">${e.Page}</span>`;
            if (ev === 'click') return `<b style="color:#111827">${e.Element||''}</b> <span style="color:#6B7280">${e.Page ? 'on ' + e.Page : ''}</span>${e.Value ? ` <span style="color:#9CA3AF">→ ${e.Value}</span>` : ''}`;
            return e.Element || e.Page || '';
        })();
        const device = [e.Device_Type === 'Mobile' ? '📱' : '💻', e.Browser, e.OS].filter(Boolean).join(' · ');
        rows.push(`<tr style="border-bottom:1px solid #F9FAFB;transition:background .1s" onmouseenter="this.style.background='#F8FAFC'" onmouseleave="this.style.background=''">
          <td style="padding:11px 10px;white-space:nowrap">
            <div style="font-family:monospace;font-size:13px;font-weight:600;color:#111827">${ts.slice(11,19)||'—'}</div>
            <div style="font-family:monospace;font-size:11px;color:#9CA3AF;margin-top:2px">${dateStr}</div>
          </td>
          <td style="padding:11px 10px">
            <div style="display:flex;align-items:center;gap:8px;white-space:nowrap">
              <div style="width:32px;height:32px;border-radius:50%;background:${avatarColor(e.User_Email)};display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0">${initials(e.User_Name||e.User_Email)}</div>
              <div><div style="font-size:14px;font-weight:600;color:#111827">${e.User_Name||e.User_Email||'—'}</div><div style="font-size:11px;color:#9CA3AF;font-family:monospace;margin-top:1px">${e.User_Email||''}</div></div>
            </div>
          </td>
          <td style="padding:11px 10px"><span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;background:${bg};color:${tc}"><span style="width:5px;height:5px;border-radius:50%;background:${tc}"></span>${lbl}</span></td>
          <td style="padding:11px 10px;font-size:13px;color:#374151;max-width:260px">${details}</td>
          <td style="padding:11px 10px"><div style="display:inline-flex;align-items:center;gap:4px;background:#F3F4F6;border:1px solid #E5E7EB;border-radius:6px;padding:4px 9px;font-size:12px;color:#6B7280;white-space:nowrap">${device||'—'}</div></td>
          <td style="padding:11px 10px;font-family:monospace;font-size:11px;color:#9CA3AF;white-space:nowrap">${(e.IP_Address||'—').replace(/\d+$/, '×')}</td>
        </tr>`);
    });
    tbody.innerHTML = rows.join('');
}

function renderActProfiles(profiles) {
    const el = document.getElementById('act-profiles-body');
    if (!profiles.length) {
        el.innerHTML = `<div style="color:#6B7280;font-size:13px;padding:24px;text-align:center;grid-column:1/-1">No data yet — events will appear after users log in and interact with the dashboard.</div>`;
        return;
    }

    const avatarBg = email => {
        const colors = ['#1e6b5c','#2563eb','#7c3aed','#d97706','#dc2626','#0891b2','#065f46'];
        let h = 0; for (const c of (email||'')) h = (h*31 + c.charCodeAt(0)) & 0xffff;
        return colors[h % colors.length];
    };
    const initials = name => (name||'??').split(' ').map(w=>w[0]).slice(0,2).join('').toUpperCase();
    const heatColor = (v, max) => {
        if (!v) return '#F3F4F6';
        const t = v / max;
        return t < 0.25 ? '#D1FAE5' : t < 0.5 ? '#6EE7B7' : t < 0.75 ? '#10B981' : '#059669';
    };

    el.innerHTML = profiles.map(u => {
        const maxVisits = Math.max(...(u.pages||[]).map(p => p.visits), 1);
        const maxHour = Math.max(...(u.hours||Array(24).fill(0)), 1);

        const pagesHTML = (u.pages||[]).map(p => {
            const w = Math.round(p.visits / maxVisits * 100);
            const col = _ACT_PAGE_COLORS[p.name] || '#1e6b5c';
            return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:7px">
              <div style="font-size:13px;color:#374151;width:80px;flex-shrink:0;font-weight:500">${p.name}</div>
              <div style="flex:1;height:7px;background:#F3F4F6;border-radius:3px;overflow:hidden"><div style="width:${w}%;height:100%;background:${col};border-radius:3px"></div></div>
              <div style="font-size:12px;color:#6B7280;width:56px;text-align:right;font-family:monospace">${p.visits} views</div>
              <div style="font-size:11px;color:#9CA3AF;width:34px;text-align:right;font-family:monospace">${p.avg_scroll}%</div>
            </div>`;
        }).join('');

        const clicksHTML = (u.top_clicks||[]).map(c =>
            `<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #F3F4F6">
               <span style="font-size:11px;color:#374151;font-weight:500">${c.element}</span>
               <span style="font-size:10px;font-family:monospace;color:#059669;background:#D1FAE5;border-radius:4px;padding:1px 7px;font-weight:700">${c.count}×</span>
             </div>`
        ).join('');

        const hoursHTML = (u.hours||Array(24).fill(0)).map((h,i) =>
            `<div style="height:14px;border-radius:2px;background:${heatColor(h,maxHour)}" title="${i}:00 — ${h} actions"></div>`
        ).join('');

        const lastSeenShort = (u.last_seen||'').slice(0,16).replace('T',' ');
        const mobilePct = u.mobile_pct || 0;

        return `<div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.05)">
          <!-- Card header -->
          <div style="display:flex;align-items:center;gap:12px;padding:16px;cursor:pointer;border-bottom:1px solid #F9FAFB" onclick="const d=this.parentElement.querySelector('.act-card-detail');d.style.display=d.style.display==='none'?'':'none'">
            <div style="width:40px;height:40px;border-radius:50%;background:${avatarBg(u.email)};display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff;flex-shrink:0">${initials(u.name)}</div>
            <div style="flex:1;min-width:0">
              <div style="font-size:15px;font-weight:700;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${u.name}</div>
              <div style="font-size:12px;color:#9CA3AF;font-family:monospace;overflow:hidden;text-overflow:ellipsis;margin-top:2px">${u.email}</div>
            </div>
            <div style="text-align:right;flex-shrink:0">
              <div style="font-size:26px;font-weight:800;color:#1e6b5c;line-height:1">${u.logins}</div>
              <div style="font-size:9px;color:#9CA3AF;margin-top:3px;text-transform:uppercase;letter-spacing:.06em">logins</div>
            </div>
            <div style="font-size:11px;color:#D1D5DB;margin-left:4px">▼</div>
          </div>
          <!-- Quick chips -->
          <div style="display:flex;gap:6px;flex-wrap:wrap;padding:10px 16px;background:#FAFBFC;border-bottom:1px solid #F3F4F6">
            <span style="background:#F3F4F6;border-radius:5px;padding:4px 10px;font-size:12px;color:#6B7280">Last seen <b style="color:#111827">${lastSeenShort||'—'}</b></span>
            <span style="background:#F3F4F6;border-radius:5px;padding:4px 10px;font-size:12px;color:#6B7280">📱 <b style="color:#111827">${mobilePct}%</b> mobile</span>
            ${u.pages&&u.pages[0]?`<span style="background:#F3F4F6;border-radius:5px;padding:4px 10px;font-size:12px;color:#6B7280">Top page: <b style="color:${_ACT_PAGE_COLORS[u.pages[0].name]||'#1e6b5c'}">${u.pages[0].name}</b></span>`:''}
          </div>
          <!-- Expandable detail -->
          <div class="act-card-detail" style="display:none">
            ${pagesHTML ? `<div style="padding:14px 16px;border-bottom:1px solid #F3F4F6">
              <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9CA3AF;margin-bottom:10px">Pages visited · scroll depth</div>
              ${pagesHTML}
            </div>` : ''}
            ${clicksHTML ? `<div style="padding:14px 16px;border-bottom:1px solid #F3F4F6">
              <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9CA3AF;margin-bottom:8px">Top clicked elements</div>
              ${clicksHTML}
            </div>` : ''}
            <div style="padding:14px 16px;border-bottom:1px solid #F3F4F6">
              <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9CA3AF;margin-bottom:8px">Active hours heatmap</div>
              <div style="display:grid;grid-template-columns:repeat(24,1fr);gap:2px">${hoursHTML}</div>
              <div style="display:flex;justify-content:space-between;margin-top:5px">
                ${['12am','6am','12pm','6pm','11pm'].map(l=>`<span style="font-size:9px;color:#9CA3AF;font-family:monospace">${l}</span>`).join('')}
              </div>
            </div>
            <div style="padding:14px 16px">
              <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9CA3AF;margin-bottom:8px">Device split</div>
              <div style="height:8px;background:#F3F4F6;border-radius:4px;overflow:hidden;display:flex">
                <div style="width:${mobilePct}%;background:#7C3AED;height:100%;border-radius:4px 0 0 4px"></div>
                <div style="width:${100-mobilePct}%;background:#10B981;height:100%;border-radius:0 4px 4px 0"></div>
              </div>
              <div style="display:flex;gap:14px;margin-top:7px">
                <span style="font-size:10px;color:#6B7280;display:flex;align-items:center;gap:5px"><span style="width:8px;height:8px;border-radius:50%;background:#7C3AED;display:inline-block"></span>Mobile ${mobilePct}%</span>
                <span style="font-size:10px;color:#6B7280;display:flex;align-items:center;gap:5px"><span style="width:8px;height:8px;border-radius:50%;background:#10B981;display:inline-block"></span>Desktop ${100-mobilePct}%</span>
              </div>
            </div>
          </div>
        </div>`;
    }).join('');
}

// ─────────────────────────────────────────────────────────────────────────────

async function loadRvmDeployment() {
    const loading = document.getElementById('ct-loading');
    const main    = document.getElementById('ct-main');
    const errEl   = document.getElementById('ct-error');
    if (!loading) return;
    if (depData) { renderRvmDeployment(depData); return; }

    loading.style.display = 'block';
    main.style.display    = 'none';
    errEl.style.display   = 'none';

    try {
        const res = await fetch('/api/deployment/summary');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        depData = await res.json();
        loading.style.display = 'none';
        main.style.display    = 'block';
        renderRvmDeployment(depData);
    } catch (e) {
        loading.style.display = 'none';
        errEl.style.display   = 'block';
        errEl.textContent     = `Failed to load RVM Deployment data: ${e.message}`;
    }
}

function depStageColor(stage) {
    if (!stage) return '#888';
    if (stage === 'Completed') return '#085f40';
    if (stage === 'Machine Live Pending') return '#085f40';
    if (stage === 'Machine Installation Pending') return '#6b2fa0';
    if (stage === 'Machine Delivery Pending') return '#2f6fb0';
    if (['Shed Pending','Electrical Pending','Internet Pending','CCTV Pending'].includes(stage)) return '#e08a1e';
    return '#d1453b';
}

function depMarkerColor(stage) {
    if (stage === 'Completed' || stage === 'Machine Live Pending') return '#085f40';
    if (stage === 'Machine Installation Pending') return '#6b2fa0';
    if (stage === 'Machine Delivery Pending') return '#2f6fb0';
    if (['Shed Pending','Electrical Pending','Internet Pending','CCTV Pending'].includes(stage)) return '#e08a1e';
    return '#d1453b';
}

function depComputeSummary(locs) {
    function cv(key, val) { return locs.filter(l => l[key] === val).length; }
    function ps(key) {
        const done = cv(key, 'Done'), pending = cv(key, 'Pending'), not_required = cv(key, 'Not Required');
        return { done, pending, not_required, pct: (done + pending) > 0 ? Math.round(done / (done + pending) * 100) : 0 };
    }
    function cvEntity(key, val) {
        const seen = new Set();
        let c = 0;
        locs.forEach(l => {
            const entity = (l.entityName || l.locationName || '').trim();
            if (seen.has(entity)) return;
            seen.add(entity);
            if (l[key] === val) c++;
        });
        return c;
    }
    // Pull NOC/Agreement from vpData (same source as Dashboard > Progress tab)
    // Combined VP + Municipal total for the denominator
    const useVpData = vpData.length > 0;
    const totalEntities = useVpData ? vpData.length : 205;
    const nocCount = useVpData
        ? vpData.filter(vp => resolveStageNumber(vp) >= 9).length
        : cvEntity('nocReceived', 'Yes');
    const agrCount = useVpData
        ? vpData.filter(vp => resolveStageNumber(vp) >= 11).length
        : cvEntity('agreementSigned', 'Yes');
    return {
        total: locs.length, totalEntities,
        noc: nocCount, agreement: agrCount,
        shed: ps('shedStatus'), electrical: ps('electricalStatus'),
        internet: ps('internetStatus'), cctv: ps('cctvStatus'),
        delivered: cv('rvmDelivery', 'Done'),
        installed: ps('rvmDeployed'),
        live: cv('machineLive', 'Done'),
    };
}

// ── Deadline Card ─────────────────────────────────────────────────────────────

function depGetDeadline() {
    const inp = document.getElementById('dep-deadline-input');
    if (inp && inp.value) depDeadline = inp.value;
    return depDeadline;
}

function depRenderDeadlineCard(s) {
    const el = document.getElementById('dep-deadline-card');
    if (el) el.innerHTML = '';  // Deadline card replaced by Project Metrics
}

function _depRenderDeadlineCard_unused(s) {
    const el = document.getElementById('dep-deadline-card');
    if (!el) return;
    const deadlineStr = depGetDeadline();
    const deadline  = new Date(deadlineStr + 'T00:00:00');
    const today     = new Date(); today.setHours(0,0,0,0);
    const daysLeft  = Math.max(0, Math.ceil((deadline - today) / 86400000));
    const weeksLeft = (daysLeft / 7).toFixed(1);
    const projStart = new Date('2026-01-01T00:00:00');
    const totalSpan = Math.max(1, Math.ceil((deadline - projStart) / 86400000));
    const elapsed   = Math.ceil((today - projStart) / 86400000);
    const timePct   = Math.min(100, Math.max(0, Math.round(elapsed / totalSpan * 100)));
    const T = depPlanTotal, installed = s.installed.done;
    const deployPct = Math.round(installed / T * 100);
    const behind    = timePct > deployPct;
    const urgColor  = daysLeft <= 7 ? '#d1453b' : daysLeft <= 21 ? '#e08a1e' : '#0b6b4f';
    const urgBg     = daysLeft <= 7 ? '#fff5f5' : daysLeft <= 21 ? '#fffbf0' : '#f0faf5';

    el.innerHTML = `<div class="card" style="border-left:5px solid ${urgColor};background:${urgBg};margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:14px">
            <div>
                <div style="font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.05em">Project Deadline</div>
                <div style="font-size:22px;font-weight:700;color:${urgColor};margin-top:2px">${deadline.toLocaleDateString('en-IN',{day:'numeric',month:'long',year:'numeric'})}</div>
            </div>
            <span style="padding:4px 12px;border-radius:20px;font-size:13px;font-weight:700;background:${behind?'#fff0f0':'#e8f7ef'};color:${behind?'#d1453b':'#0b6b4f'}">${behind ? 'Behind Schedule' : 'On Track'}</span>
        </div>
        <div class="dep-dl-stats">
            <div class="dep-dl-stat">
                <div style="font-size:34px;font-weight:800;color:${urgColor};line-height:1">${daysLeft}</div>
                <div style="font-size:12px;color:var(--muted);margin-top:4px">Days Remaining</div>
                <div style="font-size:11px;color:var(--muted)">${weeksLeft} weeks</div>
            </div>
            <div class="dep-dl-stat">
                <div style="font-size:34px;font-weight:800;color:#2f6fb0;line-height:1">${timePct}%</div>
                <div style="font-size:12px;color:var(--muted);margin-top:4px">Time Elapsed</div>
                <div style="font-size:11px;color:var(--muted)">of project timeline</div>
            </div>
            <div class="dep-dl-stat">
                <div style="font-size:34px;font-weight:800;color:#0b6b4f;line-height:1">${deployPct}%</div>
                <div style="font-size:12px;color:var(--muted);margin-top:4px">Deployment Done</div>
                <div style="font-size:11px;color:var(--muted)">${installed} of ${T} installed</div>
            </div>
            <div class="dep-dl-stat">
                <div style="font-size:34px;font-weight:800;color:${behind?'#d1453b':'#0b6b4f'};line-height:1">${Math.abs(timePct - deployPct)}%</div>
                <div style="font-size:12px;color:var(--muted);margin-top:4px">${behind ? 'Behind Schedule' : 'Ahead of Schedule'}</div>
                <div style="font-size:11px;color:var(--muted)">${behind ? `${timePct}% time used, ${deployPct}% installed` : `${deployPct}% installed, ${timePct}% time used`}</div>
            </div>
        </div>
        <div style="margin-top:12px">
            <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:3px">
                <span style="color:var(--muted)">Time progress</span><span style="color:#2f6fb0;font-weight:600">${timePct}%</span>
            </div>
            <div style="height:6px;background:#d8e4ef;border-radius:3px;overflow:hidden;margin-bottom:7px">
                <div style="height:100%;width:${timePct}%;background:#2f6fb0;border-radius:3px"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:3px">
                <span style="color:var(--muted)">Deployment progress</span><span style="color:#0b6b4f;font-weight:600">${deployPct}%</span>
            </div>
            <div style="height:6px;background:#c8e8d8;border-radius:3px;overflow:hidden">
                <div style="height:100%;width:${deployPct}%;background:#0b6b4f;border-radius:3px"></div>
            </div>
        </div>
    </div>`;
}

function depRenderSummary302(s) {
    const el = document.getElementById('dep-summary-302');
    if (!el) return;
    const T = depPlanTotal;
    const items = [
        { label:'Machine Delivered', val: s.delivered,      color:'#13a06f' },
        { label:'Machine Installed', val: s.installed.done, color:'#0b6b4f' },
        { label:'Machine Live',      val: s.live,           color:'#085f40' },
    ];
    el.innerHTML = `<div class="card dep-summary-302-card">
        <div class="dep-302-header">
            <div style="font-size:56px;font-weight:800;color:#0b6b4f;line-height:1">${T}</div>
            <div>
                <div style="font-size:17px;font-weight:700">Total Collection Points</div>
                <div style="font-size:13px;color:var(--muted);margin-top:2px">Target deployment locations across Goa &middot; ${s.total} in tracker</div>
            </div>
        </div>
        <div class="dep-302-grid">
            ${items.map(it => {
                const pct = Math.round(it.val / T * 100);
                return `<div class="dep-302-stat" style="border-top:3px solid ${it.color}">
                    <div style="font-size:26px;font-weight:700;color:${it.color}">${it.val}<span style="font-size:14px;color:var(--muted);font-weight:400"> / ${T}</span></div>
                    <div style="font-size:12px;font-weight:600;margin:4px 0">${it.label}</div>
                    <div style="height:7px;background:#e8ecf0;border-radius:3px;overflow:hidden;margin:6px 0">
                        <div style="height:100%;width:${pct}%;background:${it.color};border-radius:3px"></div>
                    </div>
                    <div style="font-size:11px;color:var(--muted)">${pct}% done &middot; ${T - it.val} remaining</div>
                </div>`;
            }).join('')}
        </div>
    </div>`;
}

// ── Pie Charts (vs 302) ───────────────────────────────────────────────────────

function depPiePath(done, total, color) {
    if (total === 0 || done <= 0) return `<circle cx="60" cy="60" r="48" fill="#e8ecf0"/>`;
    if (done >= total) return `<circle cx="60" cy="60" r="48" fill="${color}"/><circle cx="60" cy="60" r="26" fill="white"/>`;
    const pct = done / total;
    const a0 = -Math.PI / 2, a1 = a0 + pct * 2 * Math.PI;
    const x0 = (60 + 48 * Math.cos(a0)).toFixed(2), y0 = (60 + 48 * Math.sin(a0)).toFixed(2);
    const x1 = (60 + 48 * Math.cos(a1)).toFixed(2), y1 = (60 + 48 * Math.sin(a1)).toFixed(2);
    return `<circle cx="60" cy="60" r="48" fill="#e8ecf0"/>
        <path d="M60,60 L${x0},${y0} A48,48 0 ${pct > 0.5 ? 1 : 0},1 ${x1},${y1} Z" fill="${color}"/>
        <circle cx="60" cy="60" r="26" fill="white"/>`;
}

function depRenderPieCharts(s) {
    const el = document.getElementById('dep-pie-charts');
    if (!el) return;
    const T = depPlanTotal;
    const charts = [
        { title:'Machine Delivery',     done: s.delivered,      color:'#13a06f', doneLabel:'Delivered',  pendLabel:'Not Delivered' },
        { title:'Machine Installation', done: s.installed.done, color:'#0b6b4f', doneLabel:'Installed',  pendLabel:'Not Installed' },
        { title:'Machine Live',         done: s.live,           color:'#085f40', doneLabel:'Live',       pendLabel:'Not Live' },
    ];
    el.innerHTML = charts.map(ch => {
        const pend = T - ch.done, pct = Math.round(ch.done / T * 100);
        return `<div class="card dep-pie-card">
            <h3 class="dep-pie-title">${ch.title}</h3>
            <div class="dep-pie-body">
                <svg width="120" height="120" viewBox="0 0 120 120">
                    ${depPiePath(ch.done, T, ch.color)}
                    <text x="60" y="56" text-anchor="middle" font-size="17" font-weight="700" fill="${ch.color}">${pct}%</text>
                    <text x="60" y="72" text-anchor="middle" font-size="10" fill="#888">${ch.done}/${T}</text>
                </svg>
                <div class="dep-pie-legend">
                    <div class="dep-pie-leg-row"><span class="dep-pie-dot" style="background:${ch.color}"></span><span>${ch.doneLabel}: <b>${ch.done}</b></span></div>
                    <div class="dep-pie-leg-row"><span class="dep-pie-dot" style="background:#e8ecf0;border:1px solid #c8d0d8"></span><span>${ch.pendLabel}: <b>${pend}</b></span></div>
                    <div style="font-size:11px;color:var(--muted);margin-top:6px">vs ${T} total CPs</div>
                </div>
            </div>
        </div>`;
    }).join('');
}

function depRenderKPIs(s) {
    const T = depPlanTotal;
    document.getElementById('dep-kpis').innerHTML = [
        { label:'Total Locations',    value: s.total,             cls:'dep-k-total', sub:'deployment sites' },
        { label:'NOC Received',       value: s.noc,               cls:'dep-k-noc',   sub:`of ${s.totalEntities} VP + Municipal · ${s.totalEntities - s.noc} pending` },
        { label:'Agreements Signed',  value: s.agreement,         cls:'dep-k-agr',   sub:`of ${s.totalEntities} VP + Municipal · ${s.totalEntities - s.agreement} pending` },
        { label:'Shed Completed',     value: s.shed.done,         cls:'dep-k-shed',  sub:`of ${s.shed.done + s.shed.pending} required · ${s.shed.not_required} N/A` },
        { label:'Electrical Done',    value: s.electrical.done,   cls:'dep-k-elec',  sub:`${s.electrical.not_required} N/A · ${s.electrical.pending} pending` },
        { label:'Internet Done',      value: s.internet.done,     cls:'dep-k-inet',  sub:`${s.internet.not_required} N/A · ${s.internet.pending} pending` },
        { label:'CCTV Done',          value: s.cctv.done,         cls:'dep-k-cctv',  sub:`${s.cctv.not_required} N/A · ${s.cctv.pending} pending` },
        { label:'Machines Delivered', value: s.delivered,         cls:'dep-k-del',   sub:`${Math.round(s.delivered/T*100)}% of ${T}` },
        { label:'Machines Installed', value: s.installed.done,    cls:'dep-k-inst',  sub:`${Math.round(s.installed.done/T*100)}% installed` },
        { label:'Machines Live',      value: s.live,              cls:'dep-k-live',  sub:`${Math.round(s.live/T*100)}% of ${T}` },
    ].map(k => `<div class="dep-kpi ${k.cls}">
        <div class="dep-kv">${k.value}</div>
        <div class="dep-kl">${k.label}</div>
        <div class="dep-kn">${k.sub}</div>
    </div>`).join('');
}

function depRenderFunnel(s) {
    const T = depPlanTotal;
    const funnelStages = [
        { label: 'NOC Received',     val: s.noc,                                          color: '#2f6fb0', denom: s.totalEntities },
        { label: 'Agreement Signed', val: s.agreement,                                    color: '#4a7ec0', denom: s.totalEntities },
        { label: 'Shed Ready',       val: s.shed.done,                                    color: '#8b6914', denom: T },
        { label: `Electrical Ready (${s.electrical.not_required} N/A)`, val: s.electrical.done + s.electrical.not_required, color: '#c27a10', denom: T },
        { label: `Internet Ready (${s.internet.not_required} N/A)`,     val: s.internet.done + s.internet.not_required,    color: '#9b7b2e', denom: T },
        { label: `CCTV Done (${s.cctv.not_required} N/A)`,              val: s.cctv.done + s.cctv.not_required,            color: '#6b4e9e', denom: T },
        { label: 'Machine Delivered', val: s.delivered,                                   color: '#13a06f', denom: T },
        { label: 'Machine Installed', val: s.installed.done,                              color: '#0b6b4f', denom: T },
        { label: 'Machine Live',      val: s.live,                                        color: '#085f40', denom: T },
    ];
    document.getElementById('dep-funnel').innerHTML = funnelStages.map((st, i) => {
        const denom = st.denom || T;
        const p     = Math.round(st.val / denom * 100);
        const prev  = i === 0 ? denom : funnelStages[i-1].val;
        const drop  = Math.max(0, prev - st.val);
        return `<div class="dep-funnel-stage">
            <div class="dep-funnel-labels">
                <span class="dep-fn">${st.label}</span>
                <span class="dep-fc">${st.val}<span style="color:var(--muted);font-weight:400"> &middot; ${p}% of ${denom}</span></span>
            </div>
            <div class="dep-funnel-bar">
                <div class="dep-funnel-fill" style="width:${Math.max(p,2)}%;background:${st.color}">${st.val}</div>
            </div>
            ${drop > 0 ? `<div class="dep-funnel-drop">▼ ${drop} gap</div>` : ''}
        </div>`;
    }).join('');
}

function depRenderDonuts(s) {
    const progItems = [
        { label:'Shed',              stats: s.shed,       color:'#8b6914' },
        { label:'Electrical',        stats: s.electrical, color:'#c27a10' },
        { label:'Internet',          stats: s.internet,   color:'#2f6fb0' },
        { label:'CCTV',              stats: s.cctv,       color:'#6b2fa0' },
        { label:'Machine Installed', stats: s.installed,  color:'#0b6b4f' },
    ];
    document.getElementById('dep-progress-row').innerHTML = progItems.map(item => {
        const st = item.stats;
        const r = 40, circ = 2 * Math.PI * r;
        const dash = (st.pct / 100) * circ;
        const gap  = circ - dash;
        return `<div class="card dep-prog-card">
            <div class="dep-prog-label">${item.label}</div>
            <div class="dep-prog-donut-wrap">
                <svg viewBox="0 0 100 100" class="dep-donut-svg">
                    <circle cx="50" cy="50" r="${r}" fill="none" stroke="#e8ecf0" stroke-width="12"/>
                    <circle cx="50" cy="50" r="${r}" fill="none" stroke="${item.color}" stroke-width="12"
                        stroke-dasharray="${dash.toFixed(1)} ${gap.toFixed(1)}"
                        stroke-linecap="round" transform="rotate(-90 50 50)"/>
                    <text x="50" y="55" text-anchor="middle" font-size="20" font-weight="700" fill="${item.color}">${st.pct}%</text>
                </svg>
            </div>
            <div class="dep-prog-stats">
                <span class="dep-ps dep-ps-done">${st.done} Done</span>
                <span class="dep-ps dep-ps-pend">${st.pending} Pending</span>
                <span class="dep-ps dep-ps-na">${st.not_required} N/A</span>
            </div>
        </div>`;
    }).join('');
}

function depRenderForecast(s, locs) {
    const el = document.getElementById('dep-forecast');
    if (!el) return;

    const T = depPlanTotal, installed = s.installed.done, remaining = T - installed;
    const deadlineStr = depGetDeadline();
    const deadline    = new Date(deadlineStr + 'T00:00:00');
    const today       = new Date(); today.setHours(0,0,0,0);
    const daysLeft    = Math.max(1, Math.ceil((deadline - today) / 86400000));

    // Actual velocity
    const withDates = locs.filter(l => l.rvmDeployed === 'Done' && l.installDate && l.installDate.length >= 10);
    let dailyRate = 0;
    if (withDates.length >= 2) {
        const dates = withDates.map(l => new Date(l.installDate.substring(0,10)+'T00:00:00')).sort((a,b)=>a-b);
        const span  = Math.max(1, Math.ceil((dates[dates.length-1] - dates[0]) / 86400000) + 1);
        dailyRate   = Math.round(withDates.length / span * 10) / 10;
    }
    const weeklyRate = Math.round(dailyRate * 7 * 10) / 10;
    const reqDaily   = daysLeft > 0 ? Math.ceil(remaining / daysLeft) : remaining;
    const reqWeekly  = reqDaily * 7;
    const reqAggr    = Math.ceil(reqDaily * 1.2);

    function estDate(rate) {
        if (!rate || rate <= 0) return '—';
        return new Date(today.getTime() + Math.ceil(remaining / rate) * 86400000)
            .toLocaleDateString('en-IN', {day:'numeric', month:'short', year:'numeric'});
    }

    const byDate = {};
    locs.filter(l => l.rvmDeployed === 'Done' && l.installDate && typeof l.installDate === 'string' && l.installDate.length >= 10).forEach(l => {
        const d = l.installDate.substring(0,10); byDate[d] = (byDate[d] || 0) + 1;
    });
    const dateEntries = Object.entries(byDate).sort(([a],[b]) => a.localeCompare(b));
    const maxDateVal  = Math.max(...dateEntries.map(e=>e[1]), 1);
    const byWeek = {};
    locs.filter(l => l.rvmDeployed === 'Done' && l.installDate && typeof l.installDate === 'string' && l.installDate.length >= 10).forEach(l => {
        try {
            const d = new Date(l.installDate.substring(0,10)+'T00:00:00');
            if (isNaN(d.getTime())) return;
            const mon = new Date(d); mon.setDate(d.getDate() - ((d.getDay()+6)%7));
            const wk = mon.toISOString().substring(0,10);
            byWeek[wk] = (byWeek[wk] || 0) + 1;
        } catch(e) {}
    });
    const weekEntries = Object.entries(byWeek).sort(([a],[b]) => a.localeCompare(b));

    el.innerHTML = `<div class="dep-forecast-grid">

        <div class="card">
            <h3 style="font-size:15px;margin-bottom:14px">Deployment Velocity</h3>
            <div class="dep-fc-row"><span>Installed</span><b>${installed} / ${T}</b></div>
            <div class="dep-fc-row"><span>Remaining</span><b style="color:#e08a1e">${remaining}</b></div>
            <div class="dep-fc-row"><span>Days to Deadline</span><b style="color:#d1453b">${daysLeft}</b></div>
            <div class="dep-fc-row"><span>Current Daily Rate</span><b style="color:#2f6fb0">${dailyRate > 0 ? dailyRate + '/day' : 'No data yet'}</b></div>
            <div class="dep-fc-row"><span>Current Weekly Rate</span><b style="color:#2f6fb0">${weeklyRate > 0 ? weeklyRate + '/week' : 'No data yet'}</b></div>
            <div class="dep-fc-row dep-fc-sep"><span>Required Daily</span><b style="color:#d1453b">${reqDaily}/day</b></div>
            <div class="dep-fc-row"><span>Required Weekly</span><b style="color:#d1453b">${reqWeekly}/week</b></div>
            <div class="dep-fc-row dep-fc-sep"><span>Est. Completion (current)</span><b style="color:#0b6b4f">${estDate(dailyRate)}</b></div>
        </div>

        <div class="card">
            <h3 style="font-size:15px;margin-bottom:14px">Target Scenarios</h3>
            <div class="dep-scenario" style="border-color:#e08a1e">
                <div class="dep-sc-head" style="color:#e08a1e">Conservative (Current Pace)</div>
                <div class="dep-sc-body">
                    <div>${dailyRate > 0 ? dailyRate : '?'}/day &middot; ${weeklyRate > 0 ? weeklyRate : '?'}/week</div>
                    <div>Est. completion: <b>${estDate(dailyRate)}</b></div>
                    ${dailyRate > 0 && dailyRate < reqDaily ? '<div style="color:#d1453b;font-size:11px;margin-top:3px">Behind — will likely miss deadline</div>' : ''}
                </div>
            </div>
            <div class="dep-scenario" style="border-color:#0b6b4f">
                <div class="dep-sc-head" style="color:#0b6b4f">On-Track (Target)</div>
                <div class="dep-sc-body">
                    <div>${reqDaily}/day &middot; ${reqWeekly}/week</div>
                    <div>Meets deadline: <b>${deadline.toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'})}</b></div>
                </div>
            </div>
            <div class="dep-scenario" style="border-color:#2f6fb0">
                <div class="dep-sc-head" style="color:#2f6fb0">Aggressive (+20%)</div>
                <div class="dep-sc-body">
                    <div>${reqAggr}/day &middot; ${reqAggr * 7}/week</div>
                    <div>Est. completion: <b>${estDate(reqAggr)}</b></div>
                    <div style="color:#0b6b4f;font-size:11px;margin-top:3px">Builds buffer before deadline</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h3 style="font-size:15px;margin-bottom:14px">Installation History</h3>
            ${dateEntries.length > 0 ? `
            <div style="font-size:12px;font-weight:600;margin-bottom:8px">Daily</div>
            <div class="dep-chart-scroll">
                ${dateEntries.map(([date, count]) => {
                    const bPct = Math.round(count / maxDateVal * 100);
                    const lbl  = new Date(date+'T00:00:00').toLocaleDateString('en-IN',{day:'numeric',month:'short'});
                    return `<div class="dep-chart-col">
                        <div class="dep-chart-bar-wrap">
                            <div class="dep-chart-bar" style="height:${Math.max(bPct,4)}%;background:#0b6b4f"></div>
                        </div>
                        <div class="dep-chart-count">${count}</div>
                        <div class="dep-chart-lbl">${lbl}</div>
                    </div>`;
                }).join('')}
            </div>
            ${weekEntries.length > 0 ? `<div style="font-size:12px;font-weight:600;margin:14px 0 8px">Weekly</div>
            ${weekEntries.map(([wk, cnt]) => {
                const bPct = Math.round(cnt / Math.max(...weekEntries.map(e=>e[1])) * 100);
                return `<div style="margin-bottom:8px">
                    <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:3px">
                        <span>Wk of ${new Date(wk+'T00:00:00').toLocaleDateString('en-IN',{day:'numeric',month:'short'})}</span>
                        <span style="color:#0b6b4f;font-weight:600">${cnt}</span>
                    </div>
                    <div style="height:7px;background:#e8ecf0;border-radius:4px;overflow:hidden">
                        <div style="height:100%;width:${bPct}%;background:#13a06f;border-radius:4px"></div>
                    </div>
                </div>`;
            }).join('')}` : ''}
            ` : `<div style="padding:24px 0;text-align:center;color:var(--muted);font-size:13px">
                <div style="font-size:28px;margin-bottom:8px">📋</div>
                Add a <b>Machine Install Date</b> column (YYYY-MM-DD)<br>to see installation history charts.
            </div>`}
        </div>

    </div>`;
}

// ── Where We're Stuck ────────────────────────────────────────────────────────

function depRenderBlockers(locs) {
    const el = document.getElementById('dep-insights');
    if (!el) return;

    // Blocker counts
    const siteGap      = Math.max(0, depPlanTotal - locs.length);
    const nocPending   = locs.filter(l => l.nocReceived !== 'Yes').length;
    const agrPending   = locs.filter(l => l.nocReceived === 'Yes' && l.agreementSigned !== 'Yes').length;
    const elecPending  = locs.filter(l => l.electricalStatus === 'Pending').length;
    const delivNotInst = locs.filter(l => l.rvmDelivery === 'Done' && l.rvmDeployed !== 'Done').length;

    const blockers = [
        siteGap > 0      && { count: siteGap,      label: 'Sites still needed',       color: '#d1453b', bg: '#fff5f5', detail: `${locs.length} of ${depPlanTotal} locations identified` },
        nocPending > 0   && { count: nocPending,   label: 'NOC not received',          color: '#e08a1e', bg: '#fffbf0', detail: 'Panchayat/municipality sign-off pending' },
        agrPending > 0   && { count: agrPending,   label: 'Agreement pending',         color: '#c27a10', bg: '#fef9f0', detail: `${agrPending} NOC done, agreement not signed yet` },
        elecPending > 0  && { count: elecPending,  label: 'Electrical pending',        color: '#8b6914', bg: '#faf6e8', detail: 'Power connection needed before RVM goes live' },
        delivNotInst > 0 && { count: delivNotInst, label: 'Delivered, not installed',  color: '#0b6b4f', bg: '#f0faf5', detail: 'Machine on-site — commission now' },
    ].filter(Boolean);

    if (blockers.length === 0) { el.innerHTML = ''; return; }

    el.innerHTML = `<div style="margin-bottom:16px">
        <div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">Where We're Stuck</div>
        <div class="dep-blocker-strip">
            ${blockers.map(b => `<div class="dep-blocker-chip" style="border-color:${b.color}40;background:${b.bg}">
                <div style="font-size:26px;font-weight:700;color:${b.color};line-height:1;flex-shrink:0">${b.count}</div>
                <div style="min-width:0">
                    <div style="font-size:13px;font-weight:600;color:${b.color};line-height:1.2">${b.label}</div>
                    <div style="font-size:11px;color:#64748b;line-height:1.3;margin-top:2px">${b.detail}</div>
                </div>
            </div>`).join('')}
        </div>
    </div>`;
}

// ── Project Metrics ───────────────────────────────────────────────────────────

function depRenderProjectMetrics(s, locs) {
    const el = document.getElementById('dep-project-metrics');
    if (!el) return;
    const RVM_TARGET = depPlanTotal;
    const identified  = locs.length;
    const siteGap     = Math.max(0, RVM_TARGET - identified);
    const installed   = s.installed.done;
    const live        = s.live ? s.live.done || s.live : 0;
    const gap         = Math.max(0, RVM_TARGET - installed);

    const deadlineStr = depGetDeadline();
    const deadline    = new Date(deadlineStr + 'T00:00:00');
    const today       = new Date(); today.setHours(0,0,0,0);
    const daysLeft    = Math.max(1, Math.ceil((deadline - today) / 86400000));
    const reqPerDay   = (gap / daysLeft).toFixed(1);

    const projStart = new Date('2026-01-01T00:00:00');
    const totalSpan = Math.max(1, Math.ceil((deadline - projStart) / 86400000));
    const elapsed   = Math.ceil((today - projStart) / 86400000);
    const timePct   = Math.min(100, Math.max(0, Math.round(elapsed / totalSpan * 100)));
    const deployPct = Math.round(installed / RVM_TARGET * 100);
    const behind    = timePct > deployPct;
    const schedGap  = Math.abs(timePct - deployPct);

    const instDates = locs.map(l => l.installDate).filter(d => d && d.length >= 8).sort();
    let actualRate = '—';
    if (instDates.length >= 2) {
        const first = new Date(instDates[0]);
        const last  = new Date(instDates[instDates.length - 1]);
        const span  = Math.max(1, Math.ceil((last - first) / 86400000));
        actualRate  = (installed / span * 7).toFixed(1) + '/wk';
    }

    const metrics = [
        { val: identified,  lbl: 'Locations Identified',  sub: siteGap > 0 ? `${siteGap} more needed for ${RVM_TARGET}` : 'Target reached ✓', color: siteGap > 0 ? '#d1453b' : '#0b6b4f' },
        { val: RVM_TARGET,  lbl: 'RVM Target',            sub: `Go-live ${deadline.toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'})}`,      color: '#1e6b5c' },
        { val: deadline.toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'}),
                            lbl: 'Project Deadline',       sub: 'Go-live target date',                                                                              color: daysLeft < 14 ? '#d1453b' : daysLeft < 30 ? '#e08a1e' : '#0b6b4f' },
        { val: daysLeft,    lbl: 'Days Left',              sub: `until ${deadlineStr}`,                                                                             color: daysLeft < 14 ? '#d1453b' : daysLeft < 30 ? '#e08a1e' : '#0b6b4f' },
        { val: installed,   lbl: 'RVMs Installed',        sub: `${deployPct}% of ${RVM_TARGET} · ${live} live`,                                                     color: '#0b6b4f' },
        { val: gap,         lbl: 'Gap to Target',         sub: 'Machines still to install',                                                                         color: gap > 50 ? '#d1453b' : '#e08a1e' },
        { val: reqPerDay,   lbl: 'Req. Installs / Day',   sub: `Actual: ${actualRate}`,                                                                             color: '#2f6fb0' },
    ];

    el.innerHTML = `<div class="card" style="margin-bottom:16px">
        <div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">Project Metrics</div>
        <div style="display:flex;gap:10px;flex-wrap:nowrap;overflow-x:auto">
            ${metrics.map(m => `<div style="flex:1;min-width:110px;background:${m.color}10;border-top:3px solid ${m.color};border-radius:8px;padding:10px 12px">
                <div style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${m.lbl}</div>
                <div style="font-size:22px;font-weight:700;color:${m.color};line-height:1.1;margin-bottom:3px">${m.val}</div>
                <div style="font-size:10px;color:#94a3b8;line-height:1.3">${m.sub}</div>
            </div>`).join('')}
        </div>
    </div>`;
}

// ── Block-wise Summary ────────────────────────────────────────────────────────

function depRenderBlockSummary(locs) {
    const el = document.getElementById('dep-block-summary');
    if (!el) return;

    const blocks = [...new Set(locs.map(l => l.block).filter(Boolean))].sort();
    if (blocks.length === 0) { el.innerHTML = ''; return; }

    const T = depPlanTotal;
    const totalInstalled = locs.filter(l => l.rvmDeployed === 'Done').length;
    const instPct = Math.round(totalInstalled / T * 100);

    function bv(b, key, val) { return locs.filter(l => l.block === b && l[key] === val).length; }
    function btotal(b) { return locs.filter(l => l.block === b).length; }
    function breq(b, key) { return locs.filter(l => l.block === b && l[key] !== 'Not Required').length; }
    function bEntityTotal(b) {
        const seen = new Set();
        locs.filter(l => l.block === b).forEach(l => seen.add((l.entityName || l.locationName || '').trim()));
        return seen.size;
    }
    function bEntityVal(b, key, val) {
        const seen = new Set();
        let c = 0;
        locs.filter(l => l.block === b).forEach(l => {
            const e = (l.entityName || l.locationName || '').trim();
            if (seen.has(e)) return;
            seen.add(e);
            if (l[key] === val) c++;
        });
        return c;
    }

    const cols = [
        { label:'Shed',      fn: b => `${bv(b,'shedStatus','Done')}/${breq(b,'shedStatus')}` },
        { label:'Electrical',fn: b => `${bv(b,'electricalStatus','Done')}/${breq(b,'electricalStatus')}` },
        { label:'Internet',  fn: b => `${bv(b,'internetStatus','Done')}/${breq(b,'internetStatus')}` },
        { label:'CCTV',      fn: b => `${bv(b,'cctvStatus','Done')}/${breq(b,'cctvStatus')}` },
        { label:'Delivered', fn: b => `${bv(b,'rvmDelivery','Done')}/${btotal(b)}` },
        { label:'Installed', fn: b => `${bv(b,'rvmDeployed','Done')}/${btotal(b)}` },
        { label:'Live',      fn: b => `${bv(b,'machineLive','Done')}/${btotal(b)}` },
    ];

    el.innerHTML = `<div class="card" style="margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
            <h2 style="margin:0">Block-wise Progress</h2>
            <div style="font-size:12px;color:var(--muted)">${blocks.length} blocks · ${locs.length} locations</div>
        </div>
        <div class="ct-table-wrap">
            <table class="ct-table" style="font-size:12px">
                <thead><tr>
                    <th>Block</th>
                    <th>Locations</th>
                    ${cols.map(c => `<th>${c.label}</th>`).join('')}
                </tr></thead>
                <tbody>
                    ${blocks.map(b => {
                        const tot = btotal(b);
                        const inst = bv(b,'rvmDeployed','Done');
                        return `<tr>
                            <td><b>${b}</b></td>
                            <td style="color:var(--muted)">${tot}</td>
                            ${cols.map(c => {
                                const txt = c.fn(b);
                                const [a, d] = txt.split('/').map(Number);
                                const done = d > 0 && a === d;
                                const none = a === 0;
                                return `<td style="color:${done?'#0b6b4f':none?'#94a3b8':'#1a2332'};font-weight:${done?'600':'400'}">${txt}</td>`;
                            }).join('')}
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        </div>
        <div style="margin-top:14px">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px">
                <span style="font-weight:600;color:var(--muted)">Machines Installed</span>
                <span style="font-weight:700;color:#0b6b4f">${totalInstalled} / ${T} &nbsp;(${instPct}%)</span>
            </div>
            <div style="height:10px;background:#e8ecf0;border-radius:5px;overflow:hidden">
                <div style="height:100%;width:${Math.max(instPct,1)}%;background:linear-gradient(90deg,#1e6b5c,#0b6b4f);border-radius:5px;transition:width .4s ease"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:3px">
                <span>0</span><span>${T} target</span>
            </div>
        </div>
    </div>`;
}

// ── Location Table ────────────────────────────────────────────────────────────

function depFlag(val) {
    if (!val || val === '') return '<span class="ct-flag-na">—</span>';
    if (val === 'Yes' || val === 'Done') return '<span class="ct-flag-yes">✓</span>';
    if (val === 'No')           return '<span class="ct-flag-no">✗</span>';
    if (val === 'Pending')      return '<span class="ct-flag-pend">◐</span>';
    if (val === 'Not Required') return '<span class="ct-flag-na">N/A</span>';
    return `<span class="ct-flag-pend">${val}</span>`;
}

function depHighestMilestone(l) {
    if (l.machineLive === 'Done')    return { label: 'Machine Live',      color: '#085f40' };
    if (l.rvmDeployed === 'Done')    return { label: 'Machine Installed', color: '#0b6b4f' };
    if (l.rvmDelivery === 'Done')    return { label: 'Machine Delivered', color: '#2f6fb0' };
    if (l.agreementSigned === 'Yes') return { label: 'Agreement Signed',  color: '#5b8fd4' };
    if (l.nocReceived === 'Yes')     return { label: 'NOC Received',      color: '#4a7ec0' };
    return { label: 'Location Identified', color: '#888' };
}

function depPendingItems(l) {
    const items = [];
    if (l.nocReceived !== 'Yes')          items.push('NOC');
    if (l.agreementSigned !== 'Yes')      items.push('Agreement');
    if (l.shedStatus === 'Pending')       items.push('Shed');
    if (l.electricalStatus === 'Pending') items.push('Electrical');
    if (l.internetStatus === 'Pending')   items.push('Internet');
    if (l.cctvStatus === 'Pending')       items.push('CCTV');
    if (l.rvmDelivery !== 'Done')         items.push('Delivery');
    if (l.rvmDeployed !== 'Done')         items.push('Installation');
    if (l.machineLive !== 'Done')         items.push('Go-Live');
    if (items.length === 0) return '<span style="color:#0b6b4f;font-size:11px">Complete ✓</span>';
    return `<span style="font-size:11px;color:#e08a1e">${items.join(', ')}</span>`;
}

function depRenderLocTable(locs) {
    const count = document.getElementById('dep-loc-count');
    if (count) { count.textContent = `${locs.length} locations`; count.style.display = locs.length ? 'inline-flex' : 'none'; }
    document.getElementById('dep-loc-tbody').innerHTML = locs.length
        ? locs.map((l, i) => {
            const hm = depHighestMilestone(l);
            const installDate = l.installDate && l.installDate.length >= 10
                ? l.installDate.substring(0, 10)
                : '—';
            return `<tr>
                <td style="color:var(--muted)">${i+1}</td>
                <td><b>${l.locationName}</b></td>
                <td style="font-size:12px">${l.block || '—'}</td>
                <td><span class="dep-stage-pill" style="background:${hm.color}18;color:${hm.color};border:1px solid ${hm.color}33">${hm.label}</span></td>
                <td>${depFlag(l.nocReceived)}</td>
                <td>${depFlag(l.agreementSigned)}</td>
                <td>${depFlag(l.shedStatus)}</td>
                <td>${depFlag(l.electricalStatus)}</td>
                <td>${depFlag(l.internetStatus)}</td>
                <td>${depFlag(l.cctvStatus)}</td>
                <td>${depFlag(l.rvmDelivery)}</td>
                <td>${depFlag(l.rvmDeployed)}</td>
                <td style="font-size:11px;color:var(--muted)">${installDate}</td>
                <td>${depFlag(l.machineLive)}</td>
                <td>${depPendingItems(l)}</td>
            </tr>`;
        }).join('')
        : '<tr><td colspan="15" style="text-align:center;padding:20px;color:var(--muted)">No locations match current filters.</td></tr>';
}

function depRenderCPSection(cpData, planTotal) {
    const el = document.getElementById('dep-cp-section');
    if (!el || !cpData || cpData.length === 0) return;
    const byBlock = {};
    cpData.forEach(r => {
        if (!byBlock[r.block]) byBlock[r.block] = { total: 0, count: 0 };
        byBlock[r.block].total += r.planCount;
        byBlock[r.block].count++;
    });
    el.innerHTML = `<div class="card" style="margin-bottom:16px">
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:12px">
            <h2 style="margin:0">CP Plan</h2>
            <span style="font-size:13px;color:var(--muted)">${planTotal} planned across ${cpData.length} panchayats</span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px">
            ${Object.entries(byBlock).map(([block, d]) =>
                `<div style="background:#f7f8fa;border-radius:8px;padding:10px">
                    <div style="font-weight:600;font-size:12px;color:var(--muted);margin-bottom:4px">${block}</div>
                    <div style="font-size:22px;font-weight:700;color:#0b6b4f">${d.total}</div>
                    <div style="font-size:11px;color:var(--muted)">${d.count} panchayats</div>
                </div>`
            ).join('')}
        </div>
    </div>`;
}

// ── Main Render + Filters ─────────────────────────────────────────────────────

function renderRvmDeployment(data) {
    if (data.planTotal) depPlanTotal = data.planTotal;
    const subtitleEl = document.getElementById('dep-header-subtitle');
    if (subtitleEl) subtitleEl.textContent = `${depPlanTotal} Collection Points · Goa DRS 2026`;

    const blockSel = document.getElementById('dep-filter-block');
    const existBlocks = new Set([...blockSel.options].map(o => o.value).filter(Boolean));
    (data.blocks || []).forEach(b => {
        if (!existBlocks.has(b)) {
            const opt = document.createElement('option'); opt.value = b; opt.textContent = b;
            blockSel.appendChild(opt);
        }
    });
    const locSel = document.getElementById('dep-filter-location');
    locSel.innerHTML = '<option value="">All Locations</option>';
    data.locations.forEach(l => {
        const opt = document.createElement('option'); opt.value = l.locationName; opt.textContent = l.locationName;
        locSel.appendChild(opt);
    });

    depFilteredLocs = data.locations;
    const s = depComputeSummary(data.locations);
    [
        () => depRenderDeadlineCard(s),
        () => depRenderCPSection(data.cpData || [], depPlanTotal),
        () => depRenderKPIs(s),
        () => depRenderSummary302(s),
        () => depRenderFunnel(s),
        () => depRenderDonuts(s),
        () => depRenderForecast(s, data.locations),
        () => depRenderBlockers(data.locations),
        () => depRenderProjectMetrics(s, data.locations),
        () => depRenderBlockSummary(data.locations),
    ].forEach(fn => { try { fn(); } catch(e) { console.error('dep render error:', e); } });
    depRenderLocTable(data.locations);

    const vsEl = document.getElementById('dep-funnel-title-vs');
    if (vsEl) vsEl.textContent = `vs ${depPlanTotal} total`;

    ['dep-filter-block','dep-filter-location','dep-filter-delivery',
     'dep-filter-installed','dep-filter-live','dep-stage-filter'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.onchange = depApplyFilters;
    });
    const srch = document.getElementById('dep-loc-search');
    if (srch) srch.oninput = depApplyFilters;
    document.getElementById('dep-filter-reset').onclick = depResetFilters;

    const dlInput = document.getElementById('dep-deadline-input');
    if (dlInput) dlInput.onchange = () => {
        depDeadline = dlInput.value;
        depApplyFilters();
    };

    // Populate and wire table-level filters
    const tblBlock = document.getElementById('dep-tbl-block');
    if (tblBlock) {
        tblBlock.innerHTML = '<option value="">All Blocks</option>';
        (data.blocks || []).forEach(b => {
            const opt = document.createElement('option'); opt.value = b; opt.textContent = b;
            tblBlock.appendChild(opt);
        });
        tblBlock.onchange = depApplyTableFilters;
    }
    document.getElementById('dep-tbl-status')?.addEventListener('change', depApplyTableFilters);
    ['dep-tbl-date-from','dep-tbl-date-to'].forEach(id => {
        document.getElementById(id)?.addEventListener('input', depApplyTableFilters);
    });
}

function depApplyFilters() {
    if (!depData) return;
    const block  = document.getElementById('dep-filter-block').value;
    const search = (document.getElementById('dep-loc-search').value || '').toLowerCase().trim();

    const locSel  = document.getElementById('dep-filter-location');
    const prevLoc = locSel.value;
    locSel.innerHTML = '<option value="">All Locations</option>';
    const srcLocs = block ? depData.locations.filter(l => l.block === block) : depData.locations;
    srcLocs.forEach(l => {
        const opt = document.createElement('option'); opt.value = l.locationName; opt.textContent = l.locationName;
        locSel.appendChild(opt);
    });
    if (prevLoc && srcLocs.some(l => l.locationName === prevLoc)) locSel.value = prevLoc;
    const locName = locSel.value;

    let locs = depData.locations;
    if (block)   locs = locs.filter(l => l.block === block);
    if (locName) locs = locs.filter(l => l.locationName === locName);
    if (search)  locs = locs.filter(l =>
        (l.locationName || '').toLowerCase().includes(search) ||
        (l.block || '').toLowerCase().includes(search)
    );

    depFilteredLocs = locs;
    const s = depComputeSummary(locs);
    [
        () => depRenderDeadlineCard(s),
        () => depRenderSummary302(s),
        () => depRenderKPIs(s),
        () => depRenderFunnel(s),
        () => depRenderDonuts(s),
        () => depRenderForecast(s, locs),
        () => depRenderBlockers(locs),
        () => depRenderProjectMetrics(s, locs),
        () => depRenderBlockSummary(locs),
    ].forEach(fn => { try { fn(); } catch(e) { console.error('dep render error:', e); } });
    depApplyTableFilters();
}

function depParseDate(s) {
    if (!s || typeof s !== 'string' || !s.trim()) return null;
    // ISO YYYY-MM-DD
    let d = new Date(s.substring(0,10) + 'T00:00:00');
    if (!isNaN(d.getTime())) return d;
    // DD/MM/YYYY or D/M/YYYY
    const parts = s.split('/');
    if (parts.length === 3) {
        d = new Date(`${parts[2]}-${parts[1].padStart(2,'0')}-${parts[0].padStart(2,'0')}T00:00:00`);
        if (!isNaN(d.getTime())) return d;
    }
    return null;
}

function depApplyTableFilters() {
    if (!depFilteredLocs) return;
    const block    = (document.getElementById('dep-tbl-block')?.value || '');
    const status   = (document.getElementById('dep-tbl-status')?.value || '');
    const dateFrom = (document.getElementById('dep-tbl-date-from')?.value || '');
    const dateTo   = (document.getElementById('dep-tbl-date-to')?.value || '');
    let locs = depFilteredLocs;
    if (block)  locs = locs.filter(l => l.block === block);
    if (status) locs = locs.filter(l => depHighestMilestone(l).label === status);
    if (dateFrom) {
        const from = new Date(dateFrom + 'T00:00:00');
        locs = locs.filter(l => { const d = depParseDate(l.installDate); return d && d >= from; });
    }
    if (dateTo) {
        const to = new Date(dateTo + 'T00:00:00');
        locs = locs.filter(l => { const d = depParseDate(l.installDate); return d && d <= to; });
    }
    depRenderLocTable(locs);
}

function depResetFilters() {
    ['dep-filter-block','dep-filter-location'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    const srch = document.getElementById('dep-loc-search');
    if (srch) srch.value = '';
    depApplyFilters();
}

// legacy stub kept so any residual references don't crash
function renderCtDashboard(data) {
    const s = data.summary;
    const DEADLINE = new Date('2026-07-15');
    const TODAY    = new Date();

    // Working days left (exclude Sundays)
    let wd = 0, c = new Date(TODAY);
    while (c < DEADLINE) { c.setDate(c.getDate() + 1); if (c.getDay() !== 0) wd++; }
    const calDays = Math.round((DEADLINE - TODAY) / 864e5);

    // KPIs
    const rate = wd > 0 ? ((s.target - s.installed) / wd).toFixed(1) : '—';
    const pct  = s.target > 0 ? Math.round(s.installed / s.target * 100) : 0;
    document.getElementById('ct-kpis').innerHTML = [
        { c:'k-loc',  v: s.identified, k: 'Locations Identified', n: `<span style="color:#d1453b">${s.site_gap} more needed for ${s.target}</span>` },
        { c:'k-goal', v: s.target,     k: 'RVM Target',           n: `<span style="color:#0b6b4f">Go-live 15 Jul 2026</span>` },
        { c:'k-live', v: s.installed,  k: 'RVMs Installed',       n: `${pct}% of ${s.target} · ${s.live} live` },
        { c:'k-gap',  v: s.target - s.installed, k: 'Gap to Target', n: `<span style="color:#d1453b">units still to deploy</span>` },
        { c:'k-days', v: wd,           k: 'Working Days Left',    n: `${calDays} calendar days` },
        { c:'k-rate', v: rate,         k: 'Req. Installs / Day',  n: `<span style="color:#e08a1e">to hit target by deadline</span>` },
    ].map(x => `<div class="ct-kpi ${x.c}"><div class="cv">${x.v}</div><div class="ck">${x.k}</div><div class="cn">${x.n}</div></div>`).join('');

    // Banner
    document.getElementById('ct-banner').innerHTML = `
        <b>Run-rate reality check.</b> To install <b>${s.target - s.installed} more RVMs</b> in <b>${wd} working days</b>, the field needs <b>${rate}/day</b>.
        <div class="ct-banner-row">
            <div><span class="bn">${rate}/day</span>installs required</div>
            <div><span class="bn">${s.noc - s.installed}</span>sites with NOC, not installed</div>
            <div><span class="bn">${s.identified - s.noc}</span>identified without NOC</div>
            <div><span class="bn">${s.site_gap}</span>net-new sites to source</div>
        </div>`;

    // Deadline box
    const dColor = wd <= 10 ? '#d1453b' : wd <= 20 ? '#e08a1e' : '#0b6b4f';
    document.getElementById('ct-deadline').innerHTML = `
        <div class="ct-deadline-days" style="color:${dColor}">${wd}</div>
        <div class="ct-deadline-lbl">working days left</div>
        <div class="ct-deadline-date">Deadline: 15 July 2026</div>`;

    // Simulation widget
    const slider = document.getElementById('ct-sim-slider');
    function updateSim() {
        const rateVal = parseInt(slider.value);
        document.getElementById('ct-sim-val').textContent = `${rateVal}/day`;
        const remaining = s.target - s.installed;
        const daysNeeded = Math.ceil(remaining / rateVal);
        // Add working days
        let proj = new Date(TODAY), cnt = 0;
        while (cnt < daysNeeded) { proj.setDate(proj.getDate() + 1); if (proj.getDay() !== 0) cnt++; }
        const projStr = proj.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
        const diff = Math.round((proj - DEADLINE) / 864e5);
        let cls = 'ct-sim-green', msg = `On track — completes by ${projStr}`;
        if (diff > 7)  { cls = 'ct-sim-red';   msg = `Misses deadline by ${diff} days — completes ${projStr}`; }
        else if (diff > 0) { cls = 'ct-sim-amber'; msg = `Just misses deadline by ${diff} days — completes ${projStr}`; }
        document.getElementById('ct-sim-result').className = `ct-sim-result ${cls}`;
        document.getElementById('ct-sim-result').textContent = msg;
    }
    slider.oninput = updateSim;
    updateSim();

    // Funnel
    const stages = [
        ['NOC Secured',      s.noc,       '#2f6fb0'],
        ['Agreement Signed', s.agreement, '#e08a1e'],
        ['Machine Deployed', s.deployed,  '#13a06f'],
        ['Machine Installed',s.installed, '#0b6b4f'],
        ['Live / Working',   s.live,      '#08573f'],
    ];
    const base = s.identified || 1;
    document.getElementById('ct-funnel').innerHTML = stages.map((st, i) => {
        const p = Math.round(st[1] / base * 100);
        const drop = i === 0 ? (s.identified - st[1]) : (stages[i-1][1] - st[1]);
        return `<div class="ct-funnel-stage">
            <div class="ct-funnel-labels"><span class="fn">${st[0]}</span><span class="fc">${st[1]} · ${p}%</span></div>
            <div class="ct-funnel-bar"><div class="ct-funnel-fill" style="width:${Math.max(p,2)}%;background:${st[2]}">${st[1]}</div></div>
            ${drop > 0 ? `<div class="ct-funnel-drop">▼ ${drop} drop from prev gate</div>` : ''}
        </div>`;
    }).join('');

    // Bottlenecks
    const bn = data.bottlenecks;
    document.getElementById('ct-bottlenecks').innerHTML = [
        ['bn-crit', bn.site_gap,              'Site sourcing gap',          `Only ${s.identified} of ${s.target} locations mapped`],
        ['bn-crit', bn.no_noc,                'NOC not received',           'Govt sign-off pending — gates everything downstream'],
        ['bn-warn', bn.no_agreement,          'Awaiting service agreement', 'NOC done but agreement unsigned'],
        ['bn-warn', bn.shed_pending,          'Shed pending',               'Shed required but not yet installed'],
        ['bn-warn', bn.elec_pending,          'Electricity not ready',      'Plug-point / power supply pending'],
        ['bn-ok',   bn.delivered_not_installed,'Deployed, not installed',   'RVM on-site — needs base-fixing (quick win)'],
        ['bn-ok',   bn.cctv_pending,          'CCTV pending',               'Final step before machine goes live'],
    ].map(([cls, count, title, desc]) => `
        <div class="ct-bn ${cls}">
            <div class="bn-c">${count}</div>
            <div class="bn-t"><div class="bn-h">${title}</div><div class="bn-d">${desc}</div></div>
        </div>`).join('');

    // Block table
    ctRenderBlockTable(data.blocks);

    // Location worklist
    ctRenderLocTable(data.locations);

    // Populate block filter dropdown
    const blockSel = document.getElementById('ct-filter-block');
    const existingBlocks = new Set([...blockSel.options].map(o => o.value).filter(Boolean));
    data.blocks.forEach(b => {
        if (!existingBlocks.has(b.block)) {
            const opt = document.createElement('option');
            opt.value = b.block; opt.textContent = b.block;
            blockSel.appendChild(opt);
        }
    });

    // Wire up filters
    document.getElementById('ct-search').oninput       = ctApplyFilters;
    document.getElementById('ct-filter-block').onchange = ctApplyFilters;
    document.getElementById('ct-filter-stage').onchange = ctApplyFilters;
}

function ctRenderBlockTable(blocks) {
    document.getElementById('ct-block-tbody').innerHTML = blocks.map(b => {
        const t = b.total || 1;
        const bar = [
            `<i style="width:${b.live/t*100}%;background:#08573f"></i>`,
            `<i style="width:${(b.installed-b.live)/t*100}%;background:#0b6b4f"></i>`,
            `<i style="width:${(b.deployed-b.installed)/t*100}%;background:#13a06f"></i>`,
            `<i style="width:${(b.agreement-b.deployed)/t*100}%;background:#e08a1e"></i>`,
            `<i style="width:${(b.noc-b.agreement)/t*100}%;background:#2f6fb0"></i>`,
            `<i style="width:${(b.total-b.noc)/t*100}%;background:#dde3e8"></i>`,
        ].join('');
        const score = Math.round(((b.noc + b.agreement + b.deployed + b.installed*2) / (t * 6)) * 100);
        const active = ctActiveBlock === b.block ? ' ct-row-active' : '';
        return `<tr class="ct-block-row${active}" onclick="ctFilterByBlock('${b.block}')" style="cursor:pointer">
            <td><b>${b.block}</b></td>
            <td style="font-size:11.5px;color:var(--muted)">${b.poc || '—'}</td>
            <td>${b.total}</td>
            <td>${b.noc}</td>
            <td>${b.agreement}</td>
            <td>${b.deployed}</td>
            <td><b>${b.installed}</b></td>
            <td>${b.live}</td>
            <td>${score}%</td>
            <td><div class="ct-mini-prog">${bar}</div></td>
        </tr>`;
    }).join('');
}

function ctFlag(val) {
    if (val === true  || val === 'Yes')     return '<span class="ct-flag-yes">✓</span>';
    if (val === false || val === 'No')      return '<span class="ct-flag-no">✗</span>';
    if (val === 'Pending')                  return '<span class="ct-flag-pend">◐</span>';
    if (!val || val === '' || val === '—')  return '<span class="ct-flag-na">·</span>';
    return `<span class="ct-flag-pend">${val}</span>`;
}

function ctRenderLocTable(locs) {
    const count = document.getElementById('ct-loc-count');
    if (count) { count.textContent = `${locs.length} locations`; count.style.display = locs.length ? 'inline-flex' : 'none'; }
    document.getElementById('ct-loc-tbody').innerHTML = locs.map((d, i) => `
        <tr>
            <td style="color:var(--muted)">${i+1}</td>
            <td><b>${d.name}</b></td>
            <td>${d.block}</td>
            <td style="font-size:11.5px;color:var(--muted)">${d.poc || '—'}</td>
            <td><span class="ct-pill ct-s${d.ctStage}">${d.ctStageName}</span></td>
            <td>${ctFlag(d.noc)}</td>
            <td>${ctFlag(d.agreement)}</td>
            <td style="font-size:11.5px">${d.shedType || ctFlag(null)}</td>
            <td>${ctFlag(d.electricityReady)}</td>
            <td>${ctFlag(d.deployed)}</td>
            <td>${ctFlag(d.installed)}</td>
            <td>${ctFlag(d.cctvInstalled)}</td>
            <td>${ctFlag(d.machineLive)}</td>
            <td style="font-size:11.5px;color:var(--muted);max-width:140px">${d.blocker || '—'}</td>
        </tr>`).join('') || '<tr><td colspan="14" style="text-align:center;padding:20px;color:var(--muted)">No locations match current filters.</td></tr>';
}

function ctApplyFilters() {
    if (!ctData) return;
    const search = (document.getElementById('ct-search').value || '').toLowerCase();
    const block  = document.getElementById('ct-filter-block').value;
    const stage  = document.getElementById('ct-filter-stage').value;
    let locs = ctData.locations;
    if (block)  locs = locs.filter(l => l.block === block);
    if (stage !== '') locs = locs.filter(l => String(l.ctStage) === stage);
    if (search) locs = locs.filter(l =>
        (l.name || '').toLowerCase().includes(search) ||
        (l.block || '').toLowerCase().includes(search) ||
        (l.poc || '').toLowerCase().includes(search)
    );
    ctRenderLocTable(locs);
}

function ctFilterByBlock(block) {
    if (!ctData) return;
    ctActiveBlock = ctActiveBlock === block ? null : block;
    ctRenderBlockTable(ctData.blocks);
    const blockSel = document.getElementById('ct-filter-block');
    blockSel.value = ctActiveBlock || '';
    ctApplyFilters();
    document.getElementById('ct-loc-table').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

window.ctFilterByBlock = ctFilterByBlock;
