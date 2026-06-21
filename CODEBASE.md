# Codebase Documentation

**Last Updated**: 2026-03-10
**Purpose**: Detailed technical documentation for AI assistants to quickly understand the codebase structure, patterns, and implementation details.

---

## Table of Contents
1. [Project Structure](#project-structure)
2. [Backend Architecture](#backend-architecture)
3. [Frontend Architecture](#frontend-architecture)
4. [Google Sheets Integration](#google-sheets-integration)
5. [API Endpoints Reference](#api-endpoints-reference)
6. [Stage Definitions](#stage-definitions)
7. [Key Patterns & Conventions](#key-patterns--conventions)
8. [Common Operations](#common-operations)

---

## Project Structure

```
Village Panchayat Collection Point Mapping/
├── src/
│   ├── api/
│   │   └── endpoints.py          # FastAPI routes (~1300 lines)
│   ├── services/
│   │   ├── google_services.py    # Google Sheets/Gmail (~1400 lines)
│   │   ├── sarvam_processor.py   # Sarvam AI voice/text processing
│   │   └── tracker.py            # Main tracker service
│   ├── models/
│   │   └── entities.py           # Pydantic data models
│   ├── config/
│   │   └── settings.py           # Configuration & stage enums
│   └── main.py                   # Entry point (unused - endpoints.py is main)
├── frontend/
│   ├── index.html                # Main SPA page (~1420 lines)
│   ├── app.js                    # JavaScript application (~6600 lines)
│   ├── styles.css                # CSS styles (~5880 lines)
│   ├── training/                 # Training modules (4 built, excluded from Railway deploy)
│   │   ├── module-0/index.html   # Basic Training (6 chapters)
│   │   ├── module-1/index.html   # Consumer (4 chapters)
│   │   ├── module-2/index.html   # Collection Ecosystem (7 chapters)
│   │   └── module-3/index.html   # Collection Devices (5 chapters)
│   └── data/
│       └── horeca/               # HoReCa static data (exported by segment.py)
│           ├── horeca_records.json    # 13,589 records (8.6 MB)
│           ├── horeca_hex8.geojson    # 1,007 micro zone polygons (587 KB)
│           ├── horeca_hex7.geojson    # 243 meso zone polygons (115 KB)
│           └── horeca_taluka.geojson  # 12 taluka boundaries (287 KB)
├── templates/                    # Email templates
├── data/                         # Static data files
├── tests/                        # Test files
├── requirements.txt              # Python dependencies
├── Procfile                      # Railway process file
├── railway.json                  # Railway configuration
├── .env                          # Environment variables (not in git)
├── .env.example                  # Environment template
├── CLAUDE.md                     # Project context for AI
├── PROGRESS.md                   # Development progress tracker
├── CODEBASE.md                   # This file - detailed technical docs
├── REQUIREMENTS.md               # Requirements backlog with I/E scoring
└── README.md                     # Basic project overview
```

---

## Backend Architecture

### Framework & Entry Point
- **Framework**: FastAPI
- **Entry**: `src/api/endpoints.py` (app object)
- **Start Command**: `uvicorn src.api.endpoints:app --host 0.0.0.0 --port $PORT`

### Key Files

#### `src/api/endpoints.py`
Main API file containing all routes and request models.

**Request Models (Pydantic)**:
```python
class TextUpdateRequest(BaseModel):
    text: str
    village_panchayat_name: Optional[str] = None
    block_name: Optional[str] = None
    recorded_by: Optional[str] = None

class DirectStageUpdate(BaseModel):
    vp_code: str
    block: str
    new_stage: str
    meeting_notes: Optional[str] = None
    followup_date: Optional[str] = None
    followup_time: Optional[str] = "10:00"  # HH:MM format for calendar event
    updated_by: str
    create_calendar_event: bool = True

class VPProfileUpdate(BaseModel):
    vp_code: str
    block: str
    secretary_name: Optional[str] = ""
    secretary_phone: Optional[str] = ""
    sarpanch_name: Optional[str] = ""
    sarpanch_phone: Optional[str] = ""
    vp_email: Optional[str] = ""
    contractor_name: Optional[str] = ""
    contractor_phone: Optional[str] = ""
    planned_rvms: Optional[int] = 1
    agreed_rvms: Optional[int] = 0
    rvm_locations: Optional[List[RVMLocation]] = []
    electricity_bearer: Optional[str] = ""
    internet_bearer: Optional[str] = ""
    handler_hired_by: Optional[str] = ""
    space_type: Optional[str] = ""
    updated_by: str = "Unknown"

class BDOUpdateRequest(BaseModel):
    block: str
    new_stage: str  # yet_to_meet, follow_up_required, meeting_set_up, meeting_done, communication_sent

class MeetingCreateRequest(BaseModel):
    vp_code: str              # VP code or "HORECA:<place_id>" for HoReCa meetings
    vp_name: str
    block: str                # Block name or "HoReCa"
    event_type: str           # calendar_event, task_reminder, milestone
    event_date: str           # YYYY-MM-DD
    event_time: Optional[str] = "10:00"
    duration_minutes: Optional[int] = 60
    assigned_to: Optional[str] = ""
    notes: Optional[str] = ""
    event_title: Optional[str] = ""
    horeca_place_id: Optional[str] = ""
    horeca_name: Optional[str] = ""

class MeetingUpdateRequest(BaseModel):
    meeting_id: str
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None  # scheduled, completed, cancelled
    notes: Optional[str] = None
```

#### `src/services/google_services.py`
Handles all Google API integrations.

**Classes**:
- `GoogleSheetsService` - Sheets read/write operations
- `GmailService` - Email sending

**Note**: `GoogleCalendarService` was removed (2026-03-09). Calendar scope kept in SCOPES for refresh token compatibility.

**Key Methods in GoogleSheetsService**:
```python
# VP Operations
def get_tracker_data(self) -> List[Dict]       # Read all VP data from DRS-Tracker
def find_vp_row(self, vp_code: str) -> int     # Find row number by VP code
def update_vp_row(self, row_num, updates)      # Update specific columns

# BDO Operations
def get_bdo_tracker_data(self) -> List[Dict]   # Read BDO-Tracker sheet
def update_bdo_stage(self, block, stage)       # Update BDO stage
def init_bdo_tracker(self) -> Dict             # Initialize BDO sheet from DRS data

# Meeting Operations
def get_meeting_assignments_data() -> List[Dict]  # Read Meeting-Assignments sheet
def create_meeting_assignment(data) -> Dict       # Create new meeting record
def update_meeting_assignment(id, updates) -> bool # Update meeting record
def delete_meeting_assignment(id) -> bool          # Cancel meeting (set status)
def init_meeting_assignments() -> Dict             # Initialize Meeting-Assignments sheet

# HoReCa CRM Operations
def get_horeca_crm_data(search, status, htype, zone, city, page, page_size) -> Dict
def find_horeca_row(place_id) -> int               # Find row by place_id
def update_horeca_outreach(place_id, updates, author) -> Dict  # Update CRM fields
def add_horeca_record(data) -> Dict                # Add new manual lead (MANUAL_<ts> place ID)
def get_horeca_crm_summary() -> Dict               # CRM dashboard stats
def add_horeca_crm_headers() -> Dict               # Init CRM columns (BB-BM)
def migrate_horeca_assignment_headers() -> Dict    # Init assignment columns (BN-BO)

# Training Operations
def sync_training_progress(email, name, data) -> Dict   # Upsert progress in Training-Progress sheet
def get_training_leaderboard() -> Dict                   # All users merged with progress, sorted by XP
def init_training_progress() -> Dict                     # Initialize Training-Progress sheet
```

**HoReCa CRM Column Map** (`HORECA_CRM_COL_MAP`):
```python
{
    'outreach_status': 'BB', 'owner_name': 'BC', 'owner_number': 'BD',
    'spoc_name': 'BE', 'spoc_number': 'BF', 'spoc_designation': 'BG',
    'outreach_email': 'BH', 'bottles_per_week': 'BI',
    'outreach_notes': 'BJ', 'follow_up_date': 'BK',
    'last_updated': 'BL', 'updated_by': 'BM',
    'assigned_to': 'BN', 'assignment_history': 'BO',
}
```

**Authentication Flow**:
```python
# Uses refresh token to get access token
GOOGLE_REFRESH_TOKEN -> get_access_token() -> Credentials object -> gspread/googleapiclient
```

#### `src/config/settings.py`
Contains configuration and enums.

**DeploymentStage Enum** (16 stages):
```python
class DeploymentStage(str, Enum):
    YET_TO_MEET = "yet_to_meet"
    MEETING_SCHEDULED = "meeting_scheduled"
    FIRST_MEETING_DONE = "first_meeting_done"
    FOLLOW_UP_REQUIRED = "follow_up_required"
    PANCH_MEETING_SCHEDULED = "panch_meeting_scheduled"
    PANCH_MEETING_DONE = "panch_meeting_done"
    LOCATION_FINALIZED = "location_finalized"
    EMAIL_SENT = "email_sent"
    NOC_PENDING = "noc_pending"
    NOC_RECEIVED = "noc_received"
    SERVICE_AGREEMENT_SENT = "service_agreement_sent"
    SERVICE_AGREEMENT_SIGNED = "service_agreement_signed"
    INFRA_PENDING = "infra_pending"
    INFRA_COMPLETE = "infra_complete"
    DEVICE_DEPLOYED = "device_deployed"
    DEVICE_INSTALLED = "device_installed"
```

---

## Frontend Architecture

### Single Page Application (SPA)
- **No framework** - Vanilla JavaScript
- **State**: Global variables (`vpData`, `currentVP`, `bdoData`, etc.)
- **Rendering**: Template literals + innerHTML
- **URL routing** (v72): `history.pushState`/`popstate` with `ROUTE_TO_TAB`/`TAB_TO_ROUTE` maps. Clean URLs: `/VPs`, `/Dashboard`, `/HoReCa`, etc. Backend catch-all `/{path:path}` serves `index.html`.
- **Design system** (v70): DM Sans + Inter fonts, `#1e6b5c` teal primary, dual-shadow layers, `cubic-bezier(0.4,0,0.2,1)` transitions

### File Structure

#### `frontend/index.html`
HTML structure with 8 navigation tabs (bottom nav mobile, left sidebar desktop), visibility controlled by RBAC:
1. **VPs Tab** (`#vps-tab`) - Master-detail layout: VP list + VP profile/stage forms
2. **ULBs Tab** (`#ulbs-tab`) - ULB-specific view (admin only)
3. **Dashboard Tab** (`#dashboard-tab`) - Progress/RVM/Cost sub-tabs (BDO integrated in Progress)
4. **Meetings Tab** (`#meetings-tab`) - Week scroller + day-grouped view + needs scheduling
5. **Escalation Tab** (`#escalation-tab`) - VPs stuck beyond working-day thresholds
6. **Today Tab** (`#today-tab`) - Today's activity feed (filtered by role)
7. **HoReCa Tab** (`#horeca-tab`) - HoReCa CRM + Board + Dashboard
8. **Learning Tab** (`#learning-tab`) - Training modules (all roles)

**Navigation Pattern** (v56 — bottom nav mobile, left sidebar desktop):
```html
<nav class="nav-bar" id="nav-bar">
    <!-- Desktop: sidebar toggle as first item (hidden on mobile) -->
    <button class="sidebar-toggle" id="sidebar-toggle" onclick="toggleSidebar()">
        <svg>...</svg>
        <span class="toggle-label">Menu</span>
    </button>
    <!-- 5 nav items with SVG icons + labels + badge overlays -->
    <button class="nav-item active" data-tab="vps">
        <span class="nav-icon"><svg>...</svg></span>
        <span class="nav-label">VPs</span>
    </button>
    <button class="nav-item" data-tab="meetings">
        <span class="nav-icon">
            <svg>...</svg>
            <span class="nav-badge" id="badge-meetings"></span>
        </span>
        <span class="nav-label">Meetings</span>
    </button>
    <!-- ... dashboard, escalation, today -->
</nav>

<section id="vps-tab" class="tab-content active">...</section>
<section id="dashboard-tab" class="tab-content">...</section>
<!-- ... meetings-tab, escalation-tab, today-tab -->
```

**Mobile**: Bottom-fixed nav bar with icon + label columns.
**Desktop (≥1024px)**: Left sidebar (60px collapsed, 180px expanded). Toggle shows/hides labels.
Sidebar state persisted in `localStorage('sidebarExpanded')`.

**Modals**:
- `#block-modal` - Block detail modal (VP list within block)
- `#bdo-modal` - BDO stage update modal
- `#meeting-modal` - Schedule/edit meeting modal

#### `frontend/app.js`
JavaScript application logic.

**Global State**:
```javascript
let vpData = [];           // All VP records from API
let currentVP = null;      // Currently selected VP
let bdoData = [];          // All BDO records
let currentBDOBlock = null; // Currently editing BDO block
let meetingsData = [];     // All meeting records from API
let currentMeetingId = null; // Currently editing meeting
let meetingsSelectedDate = null;  // Currently selected date (YYYY-MM-DD)
let meetingsWeekOffset = 0;       // 0 = current week, -1 = last week, +1 = next week
let needsSchedulingCache = null;  // Cache for HoReCa "Meeting aligned" data
let rvmLocations = [];     // GPS coordinates for RVMs
let mediaRecorder = null;  // Voice recording state
// HoReCa tab (lazy-loaded)
let horecaData = null;        // 13,589 records
let horecaGeoHex8 = null;     // 1,007 micro zone GeoJSON
let horecaGeoHex7 = null;     // 243 meso zone GeoJSON
let horecaGeoTaluka = null;   // 12 taluka boundary GeoJSON
let horecaMap = null;          // Leaflet map instance
let horecaPage = 1;            // Explorer pagination
```

**Key Functions**:
```javascript
// Initialization & Routing
init()                    // Main entry point on DOMContentLoaded
setupTabs()               // Nav item switching + URL routing (pushState/popstate) + sidebar restore
getTabFromURL()           // Parse URL path to tab ID (e.g. /VPs → 'vps')
toggleSidebar()           // Toggle sidebar expanded/collapsed (desktop), persists to localStorage
loadVPData()              // Fetch VP data from API
loadBDOData()             // Fetch BDO data from API
loadMeetingsData()        // Fetch meetings from API
updateTabBadges()         // Update badge counts on Escalation/Meetings/Today nav icons

// VP Operations
showVPDetails(vp)         // Display VP info in form
submitUpdate()            // Submit stage update to API
saveVPProfile()           // Save profile changes to API

// Dashboard
loadDashboard()           // Load all dashboard views
loadProgressDashboard()   // Render progress stats (includes BDO)
renderHolisticFunnel()    // Render pipeline funnel
renderBDOInProgress()     // Render BDO section in dashboard
renderBlockProgress()     // Render block-wise VP progress
loadRvmDashboard()        // Render RVM stats
loadCostDashboard()       // Render cost distribution

// Meeting Manager
renderMeetingsTab()       // Render meetings tab (stats + needs scheduling + week scroller + day view)
renderWeekScroller()      // Render Mon-Sun day pills with meeting dots
renderDayMeetings()       // Render meetings for selected day in time blocks
renderNeedsScheduling()   // Show HoReCa records needing scheduling (async)
navigateWeek(direction)   // Navigate to prev/next week
selectDay(dateStr)        // Select a day in the week scroller
openScheduleMeetingModal() // Open schedule meeting modal
submitMeeting()           // Create/update meeting
editMeeting(meetingId)    // Edit existing meeting
markMeetingComplete(id)   // Mark meeting as completed
deleteMeeting(id)         // Cancel meeting
openScheduleFollowup()    // Quick schedule from VP details
applyRBAC()               // Hide nav items based on user role
applyDashboardRBAC()      // Hide dashboard sub-tabs based on role
autoCreateHorecaMeeting() // Auto-create meeting when CRM status → Follow-up/Meeting aligned

// Dashboard
setupDashboardTabs()      // Dashboard sub-tab switching (progress/rvm/cost/horeca)
loadDashHoReCa()          // Lazy-load HoReCa dashboard sub-tab
renderDashHoReCa()        // Render HoReCa funnel + type/zone tables + recent activity

// Training
getTrainingStorageKey()   // Per-user localStorage key: goa_drs_training_<email>
getTrainingState()        // Read training progress from per-user localStorage
openTrainingModule(id)    // Open training module in new tab with storageKey param

// BDO Operations (now in Dashboard)
openBDOModal(block)       // Open BDO edit modal
submitBDOUpdate()         // Submit BDO stage update

// Master-Detail (VPs tab)
selectVPFromMaster(vpCode) // Select VP, show detail, trigger showDetailPanel()
showDetailPanel()          // Add .detail-active for mobile detail view
showMasterPanel()          // Back to master list on mobile
navigateToVP(vpCode, block) // Navigate from escalation/block to VP detail

// Escalation
renderEscalationTab()     // Render escalation tracker with severity groups
toggleEscalationGroup()   // Expand/collapse severity groups

// Today
renderTodayActivity()     // Render today's update feed

// Modals
openBlockModal(blockName) // Open block detail modal
closeBlockModal()         // Close block modal
closeBDOModal()           // Close BDO modal
closeMeetingModal()       // Close meeting modal

// HoReCa Tab
initHoReCaTab()           // Lazy-load data, init all sub-tabs
initHoReCaMap()           // Create Leaflet map with 4 layers
renderHoReCaExplorer()    // Render filtered card grid (50/page)
renderHoReCaSummary()     // Render stat cards + breakdown tables

// Utilities
showToast(message, type)  // Show notification
showLoading(show)         // Show/hide loading spinner
getStageLabel(value)      // Get display label for stage
```

**DOM Element References** (stored in `elements` object):
```javascript
const elements = {
    blockSelect, vpSelect, vpDetails, vpName, currentStage,
    updateForm, newStage, meetingNotes, followupDate, updatedBy,
    submitBtn, searchInput, filterStage, vpList, toast, loading,
    voiceRecordBtn, stopRecordingBtn, recordingStatus, recordingTime,
    secretaryName, secretaryPhone, sarpanchName, sarpanchPhone, vpEmail,
    contractorName, contractorPhone, plannedRvms, agreedRvms,
    electricityBearer, internetBearer, handlerHiredBy, spaceType,
    rvmLocationsSection, rvmLocationsList, captureLocationBtn, saveProfileBtn
};
```

#### `frontend/styles.css`
CSS styles with CSS variables.

**CSS Variables**:
```css
:root {
    --primary: #2563eb;
    --primary-dark: #1d4ed8;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --gray-50 to --gray-900;
    --shadow, --shadow-sm, --shadow-lg;
    --radius: 8px;
    --radius-lg: 12px;
}
```

**Key CSS Classes**:
- `.nav-bar` - Navigation container (bottom bar mobile, left sidebar desktop)
- `.nav-item` - Navigation buttons (replaces former `.tab`)
- `.nav-icon`, `.nav-label`, `.nav-badge` - Icon, label, and badge within nav items
- `.sidebar-toggle`, `.toggle-label` - Sidebar expand/collapse button (desktop only)
- `.tab-content` - Tab content panels (unchanged)
- `.card` - Content cards
- `.btn`, `.btn-primary`, `.btn-secondary` - Buttons
- `.stage-badge` - Stage indicator badges
- `.block-card`, `.bdo-card` - Block/BDO cards
- `.modal-overlay`, `.modal-content` - Modal styles
- `.progress-*`, `.bdo-*` - Dashboard-specific styles
- `.sidebar-expanded` - Applied to `.content` and `.header` when sidebar is expanded (desktop)
- `.master-detail-layout`, `.detail-active` - VP list/detail split view

**Desktop Layout (≥1024px)**:
- Header: `position: fixed; top: 0; left: 60px; height: 64px` (shifts to `left: 180px` when sidebar expanded)
- Sidebar: `position: fixed; top: 0; left: 0; width: 60px` (180px when `.expanded`)
- Content: `margin-left: 60px; margin-top: 64px` (180px when `.sidebar-expanded`)
- Sidebar border only below blue zone via `.nav-bar::after` pseudo-element starting at `top: 64px`

### HoReCa Tab Architecture

**Sub-tabs**: CRM (default), Board (Kanban), Dashboard. Map/Explorer/Summary archived (2026-02-24).

**HoReCa Outreach Statuses** (updated 2026-02-25):
- De-listed, Call not answered, Pre-meeting mail to be sent, Pre-meeting mail sent, Meeting aligned, Meeting done, Post-meeting mail to be sent, Post meeting mail sent, OB Form Opened, OB Form Filled

**CRM Key Functions**:
```javascript
// CRM
fetchHoReCaCRMData()          // Fetch paginated CRM data from API
renderHorecaCrmList()         // Render CRM card list
selectHorecaFromMaster(id)    // Select a HoReCa record, show detail panel
submitHorecaStatusUpdate()    // Update status + follow-up date
assignHoreca()                // Assign to team member
postHorecaComment()           // Post comment/note
saveHorecaContacts()          // Save contact details

// Add New Lead
openAddHorecaLeadModal()      // Open modal, reset form
closeAddHorecaLeadModal()     // Close modal
toggleAddLeadSection(section) // Toggle collapsible section
submitNewHorecaLead()         // POST to /api/horeca/crm/add

// HoReCa Meeting Scheduling
openHorecaMeetingModal()      // Open meeting modal in HoReCa mode
renderHorecaMeetings(record)  // Render meeting cards from meetingsData (filters by HORECA:<place_id>)
// submitMeeting() handles both VP and HoReCa contexts via meeting-context hidden field

// Board (Kanban)
initHoReCaBoard()             // Fetch summary counts, render skeleton, lazy-load columns
renderBoardSkeleton()         // Render column headers with counts (instant)
boardFetchColumn(status, pg)  // Fetch 50 cards for a status column
renderBoardColumn(status)     // Render cards in a column
boardShowMore(status)         // Load next page of cards for a column
boardClickCard(placeId, st)   // Navigate to CRM tab with record selected

// Dashboard
initHoReCaDashboard()         // Fetch CRM summary
renderHorecaDashboard(data)   // Render funnel (6-col grid, 2 rows) + tables
```

**CSS Classes** (all scoped with `.horeca-*` or `.hcrm-*`):
- `.horeca-tabs` / `.horeca-sub-tab` — Sub-tab bar (CRM/Board/Dashboard)
- `.horeca-content` — Sub-tab content panels
- `.horeca-board` / `.horeca-board-column` / `.horeca-board-card` — Kanban board layout
- `.hcrm-status-*` — Status badge colors (delisted, call-not-answered, pre-mail-pending, pre-mail, aligned, done, post-mail-pending, post-mail, ob-opened, ob-filled)
- `.add-lead-section` / `.add-lead-section-title` / `.add-lead-section-content` — Add lead modal collapsible sections
- `.hcrm-meeting-card-item` — HoReCa meeting cards (with .completed, .cancelled variants)
- `.hcrm-mtg-*` — Meeting card sub-elements (row1, title, type-badge, row2, actions)

**Data Files** (in `frontend/data/horeca/`, generated by HoReCa Collection `segment.py`):
| File | Records | Size | Key Fields |
|------|---------|------|------------|
| `horeca_records.json` | 13,589 | 8.6 MB | name, type, city, rat, status, alc, pscore, prank, lat, lng, h8, h7, zname, zrank |
| `horeca_hex8.geojson` | 1,007 | 587 KB | id, name, count, score, rank, city, avg_priority |
| `horeca_hex7.geojson` | 243 | 115 KB | id, name, city, count, micro_count, avg_score |
| `horeca_taluka.geojson` | 12 | 287 KB | Taluka boundary polygons |

**External Dependency**: Leaflet.js (v1.9.4) loaded dynamically from CDN on first map render.

### Cache Busting
Files are versioned: `styles.css?v=68`, `app.js?v=68`
Update version in `index.html` when making frontend changes.

---

## Google Sheets Integration

### Spreadsheet Structure
**Spreadsheet ID**: `1gy0xNL7-ayFfVjf3ETvi8qN3bWytNGbRZg68nShnkEo`

### Sheet: DRS-Tracker (39 columns: A-AM)

| Col | Field | Col | Field | Col | Field |
|-----|-------|-----|-------|-----|-------|
| A | Block | N | Current_Stage | AA | Infra_Status |
| B | VP_Code | O | Stage_Number | AB | Device_Deployed_Date |
| C | VP_Name | P | Stage_Date | AC | Contractor_Name |
| D | BDO_Name | Q | Meeting_Notes | AD | Contractor_Phone |
| E | BDO_Phone | R | Follow_Up_Date | AE | Planned_RVMs |
| F | Secretary_Name | S | Location_GPS | AF | Agreed_RVMs |
| G | Secretary_Phone | T | Email_Sent_Date | AG | RVM_Locations (JSON) |
| H | Sarpanch_Name | U | NOC_Requested_Date | AH | Electricity_Cost_Bearer |
| I | Sarpanch_Phone | V | NOC_Received_Date | AI | Internet_Cost_Bearer |
| J | VP_Email | W | NOC_File_URL | AJ | Handler_Hired_By |
| K | VP_Contact | X | SA_Sent_Date | AK | Space_Type |
| L | Website | Y | SA_Signed_Date | AL | Last_Updated |
| M | Address | Z | SA_File_URL | AM | Updated_By |

### Sheet: BDO-Tracker (4 columns: A-D)

| Col | Field |
|-----|-------|
| A | Block |
| B | BDO_Name |
| C | BDO_Phone |
| D | Current_Stage |

### Sheet: Meeting-Assignments (13 columns: A-M)

| Col | Field | Description |
|-----|-------|-------------|
| A | Meeting_ID | Unique ID (MTG-XXXXXXXX) |
| B | VP_Code | VP code or `HORECA:<place_id>` for HoReCa meetings |
| C | VP_Name | Village Panchayat or HoReCa name |
| D | Block | Block name or "HoReCa" |
| E | Event_Type | `calendar_event`, `task_reminder`, `milestone` |
| F | Event_Date | YYYY-MM-DD format |
| G | Event_Time | HH:MM format |
| H | Assigned_To | Person assigned to meeting |
| I | Calendar_Event_ID | Google Calendar event ID (if created) |
| J | Status | `scheduled`, `completed`, `cancelled` |
| K | Notes | Meeting notes/agenda |
| L | Created_At | Timestamp |
| M | Event_Title | Meeting title (First Meeting, Follow-up, etc.) |

### HoReCa CRM Columns (Sheet ID: `12YHTCeJxholgigzmGuf2GtTGsTREiS-EZj4Fod8B5x8`)

Columns A-BA are enriched data (place info, zones, priorities). CRM outreach fields:

| Col | Field | Col | Field |
|-----|-------|-----|-------|
| BB | Outreach_Status | BH | Outreach_Email |
| BC | Owner_Name | BI | Bottles_Per_Week |
| BD | Owner_Number | BJ | Outreach_Notes |
| BE | SPOC_Name | BK | Follow_Up_Date |
| BF | SPOC_Number | BL | Last_Updated |
| BG | SPOC_Designation | BM | Updated_By |
| BN | Assigned_To | BO | Assignment_History |

**Assignment History Format**: `[YYYY-MM-DD HH:MM|author] → assignee\n---\n[previous entries]`
**Team Members**: Ayaan, Nupur, Aruna, Varsha, Chaithanya, Animesh, Vishwash

### Update Pattern
```python
# Find row by VP code
row_num = sheets_service.find_vp_row(vp_code)

# Build updates dict with column letters
updates = {
    'N': new_stage,           # Current_Stage
    'O': str(stage_number),   # Stage_Number
    'P': date_str,            # Stage_Date
    'AL': timestamp,          # Last_Updated
    'AM': updated_by,         # Updated_By
}

# Apply updates
sheets_service.update_vp_row(row_num, updates)
```

---

## API Endpoints Reference

### Core Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve frontend |
| GET | `/api/health` | Health check |
| GET | `/blocks` | List 12 blocks |
| GET | `/stages` | List 16 stages |

### VP Data Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vps/all` | Get all VP data |
| POST | `/api/update/stage` | Update VP stage |
| POST | `/api/update/profile` | Update VP profile |

### BDO Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bdo/all` | Get all BDO data |
| POST | `/api/bdo/update` | Update BDO stage |
| POST | `/api/bdo/init` | Initialize BDO sheet |

### Voice/Text Processing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/update/text` | Process text notes |
| POST | `/update/voice` | Transcribe audio |

### Meeting Manager
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/meetings/all` | Get all meetings from sheet |
| POST | `/api/meetings/create` | Create new meeting |
| PUT | `/api/meetings/update` | Update existing meeting |
| DELETE | `/api/meetings/{id}` | Cancel meeting |
| POST | `/api/meetings/init` | Initialize Meeting-Assignments sheet |

### HoReCa CRM
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/horeca/crm` | Get filtered, paginated CRM data |
| POST | `/api/horeca/crm/update` | Update outreach fields (status, contacts, assignment) |
| POST | `/api/horeca/crm/add` | Add a new HoReCa lead manually |
| GET | `/api/horeca/crm/summary` | Get CRM dashboard summary stats |
| GET | `/api/horeca/crm/statuses` | Get valid outreach status list |
| POST | `/api/horeca/crm/init` | Initialize CRM column headers (BB-BM) |
| POST | `/api/horeca/crm/migrate-assignment` | Add assignment headers (BN-BO) |

**Meeting Create Request**:
```python
class MeetingCreateRequest(BaseModel):
    vp_code: str              # VP code or "HORECA:<place_id>" for HoReCa meetings
    vp_name: str
    block: str                # Block name or "HoReCa" for HoReCa meetings
    event_type: str           # calendar_event, task_reminder, milestone
    event_date: str           # YYYY-MM-DD
    event_time: Optional[str] = "10:00"
    duration_minutes: Optional[int] = 60
    assigned_to: Optional[str] = ""
    notes: Optional[str] = ""
    create_calendar: Optional[bool] = True
    event_title: Optional[str] = ""           # Custom calendar event title
    horeca_place_id: Optional[str] = ""       # HoReCa place ID (when scheduling for HoReCa)
    horeca_name: Optional[str] = ""           # HoReCa name (when scheduling for HoReCa)
```

---

## Stage Definitions

### VP Stages (16 stages)
| # | Value | Label | Pipeline Step |
|---|-------|-------|---------------|
| 1 | `yet_to_meet` | Yet to Meet | - |
| 2 | `meeting_scheduled` | Meeting Scheduled | Contacted |
| 3 | `first_meeting_done` | First Meeting Done | Meeting Done |
| 4 | `follow_up_required` | Follow-up Required | Meeting Done |
| 5 | `panch_meeting_scheduled` | Panch Meeting Scheduled | Meeting Done |
| 6 | `panch_meeting_done` | Panch Meeting Done | Meeting Done |
| 7 | `location_finalized` | Location Finalized | Location OK |
| 8 | `email_sent` | Email Sent | Location OK |
| 9 | `noc_pending` | NOC Pending | Location OK |
| 10 | `noc_received` | NOC Received | NOC Received |
| 11 | `service_agreement_sent` | Service Agreement Sent | NOC Received |
| 12 | `service_agreement_signed` | Service Agreement Signed | Agreement |
| 13 | `infra_pending` | Infra Pending | Agreement |
| 14 | `infra_complete` | Infra Complete | Agreement |
| 15 | `device_deployed` | Device Deployed | Agreement |
| 16 | `device_installed` | Device Installed | Installed |

### BDO Stages (5 stages)
| # | Value | Label |
|---|-------|-------|
| 1 | `yet_to_meet` | Yet to Meet |
| 2 | `follow_up_required` | Follow-up Required |
| 3 | `meeting_set_up` | Meeting Set Up |
| 4 | `meeting_done` | Meeting Done |
| 5 | `communication_sent` | Communication Sent to VPs |

---

## Key Patterns & Conventions

### Adding a New API Endpoint
1. Define Pydantic request model in `endpoints.py`
2. Create endpoint function with `@app.get/post/delete`
3. Use `GoogleSheetsService()` for sheet operations
4. Return dict or raise `HTTPException`

```python
class NewRequest(BaseModel):
    field1: str
    field2: Optional[int] = None

@app.post("/api/new/endpoint")
async def new_endpoint(request: NewRequest):
    try:
        sheets_service = GoogleSheetsService()
        # ... do work ...
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Adding a New Frontend Tab
1. Add tab button in `index.html`:
   ```html
   <button class="tab" data-tab="newtab">New Tab</button>
   ```
2. Add content section:
   ```html
   <section id="newtab-tab" class="tab-content">...</section>
   ```
3. Add handler in `setupTabs()` in `app.js`:
   ```javascript
   if (tabId === 'newtab') loadNewTab();
   ```
4. Implement load function and rendering

### Adding New Sheet Columns
1. Add column to Google Sheet manually
2. Note the column letter (e.g., 'AN')
3. Update `get_tracker_data()` to parse new field
4. Update `update_vp_row()` calls with new column

### Updating Sheets Data
```python
# Pattern: Find row, build updates dict, apply
row_num = sheets_service.find_vp_row(vp_code)
updates = {
    'COLUMN_LETTER': value,
    'AL': datetime.now().isoformat(),  # Always update timestamp
    'AM': updated_by,                   # Always track who updated
}
sheets_service.update_vp_row(row_num, updates)
```

### Frontend State Updates
```javascript
// After API success, update local state
const idx = vpData.findIndex(vp => vp.vpCode === code);
if (idx >= 0) {
    vpData[idx].fieldName = newValue;
}
// Re-render affected UI
showVPDetails(currentVP);
```

---

## Common Operations

### Deploy to Railway
```bash
cd "/Users/chaithanyadonda/Documents/Claude Folder/Goa DRS/Village Panchayat Collection Point Mapping"
railway link --project ravishing-mindfulness  # If not linked
railway up --service ravishing-mindfulness
```

### Test API Endpoints
```bash
# Health check
curl https://ravishing-mindfulness-production.up.railway.app/api/health

# Get all VPs
curl https://ravishing-mindfulness-production.up.railway.app/api/vps/all

# Get all BDOs
curl https://ravishing-mindfulness-production.up.railway.app/api/bdo/all

# Update BDO stage
curl -X POST https://ravishing-mindfulness-production.up.railway.app/api/bdo/update \
  -H "Content-Type: application/json" \
  -d '{"block": "BARDEZ", "new_stage": "meeting_done"}'

# Get all meetings
curl https://ravishing-mindfulness-production.up.railway.app/api/meetings/all

# Get upcoming calendar events
curl https://ravishing-mindfulness-production.up.railway.app/api/calendar/upcoming

# Create meeting
curl -X POST https://ravishing-mindfulness-production.up.railway.app/api/meetings/create \
  -H "Content-Type: application/json" \
  -d '{"vp_code": "PON-001", "vp_name": "Bandora", "block": "PONDA", "event_type": "calendar_event", "event_date": "2026-02-15", "event_time": "10:00"}'
```

### View Railway Logs
```bash
railway logs --service ravishing-mindfulness
```

### Cache Busting After Frontend Changes
Update version in `index.html`:
```html
<link rel="stylesheet" href="/static/styles.css?v=12">
<script src="/static/app.js?v=12"></script>
```

---

## Environment Variables

```env
GOOGLE_REFRESH_TOKEN=1//0g...        # OAuth refresh token
GOOGLE_SHEETS_ID=1gy0xNL7-...        # Spreadsheet ID
SARVAM_API_KEY=sk_52rcjfng_...       # Sarvam AI key
NOTIFICATION_EMAILS=email@domain.com # Notification recipients
```

---

## 12 Blocks in Goa

| Block | Total VPs |
|-------|-----------|
| Bardez | 33 |
| Bicholim | 18 |
| Cancona | 7 |
| Dharbandora | 5 |
| Mormugao | 10 |
| Pernem | 20 |
| Ponda | 19 |
| Quepem | 11 |
| Salcete | 30 |
| Sanguem | 7 |
| Sattari | 12 |
| Tiswadi | 19 |
| **Total** | **191** |

---

## Changelog

### 2026-03-14 — RBAC Bug Fix: BDO Endpoint Access

- **Bug**: `/api/bdo/all` was `require_role(request, {'admin'})` — `vp` role users got 403, causing Dashboard pipeline to show zeros (bdoData fell back to empty cache)
- **Fix**: Changed to `require_role(request, {'admin', 'vp'})` — matches `/api/vps/all` pattern
- **Affected**: Dashboard > Progress tab — VP Deployment Pipeline funnel (Blocks, Blocks Unlocked, VPs Accessible numbers)

### 2026-03-09 — RBAC + Calendar Removal + Meetings Redesign

#### Google Calendar Removed
- **Deleted** `calendar_service.py`, removed `GoogleCalendarService` class from `google_services.py`
- Removed all `/api/calendar/*` endpoints and `/api/meetings/sync`
- Stripped calendar fields from request models. Meetings are now purely sheet-backed.

#### Role-Based Access Control (RBAC)
- 4 roles: `admin`, `vp`, `horeca`, `new_joinee` with tab-level and data-level access control
- `ROLE_TAB_PERMISSIONS` map + `require_role()` helper in endpoints.py
- Frontend `applyRBAC()` hides nav items via `.rbac-hidden` CSS class
- Auth endpoints return `allowed_tabs` array

#### Meetings Tab Redesign
- **Week scroller**: Horizontal Mon-Sun day pills with colored dots (blue=VP, orange=HoReCa)
- **Day view**: Meetings grouped by Morning/Afternoon/Evening time blocks
- **"Needs Scheduling"**: Shows HoReCa records with "Meeting aligned" but no scheduled meeting
- **Source badges**: Blue "VP" / Orange "HoReCa" on meeting cards
- Replaced old date accordion (`renderMeetingsList`) with `renderWeekScroller()` + `renderDayMeetings()`
- New state: `meetingsSelectedDate`, `meetingsWeekOffset`, `needsSchedulingCache`

#### Deployment Fix
- Added `frontend/training/`, `frontend/data/horeca/` to `.railwayignore` (was 24MB causing CLI upload timeout)
- Cache version: v=68

### 2026-02-24 — HoReCa CRM Overhaul

- **Archived sub-tabs**: Removed Map, Explorer, Summary sub-tabs; only CRM + Dashboard remain
- **Updated status list**: Yet to contact, De-listed, Call not answered, Mail sent, Meeting aligned, Meeting done, OB Form Opened, OB Form Filled (replaced old 6 statuses)
- **Add New Lead**: "+ Add Lead" button, modal with 5 collapsible sections, `POST /api/horeca/crm/add` endpoint, `add_horeca_record()` method (generates `MANUAL_<timestamp>` Place ID)
- **HoReCa Meeting Scheduling**: "Schedule Meeting" button in Meetings section, shared meeting modal adapted with HoReCa context (hidden field, HoReCa-specific titles), `submitMeeting()` handles both VP/HoReCa, meetings stored with `HORECA:<place_id>` in VP_Code column, `renderHorecaMeetings()` shows meeting cards with edit/complete actions
- **MeetingCreateRequest** extended with `horeca_place_id` and `horeca_name` optional fields
- **Files modified**: `google_services.py`, `endpoints.py`, `index.html`, `app.js`, `styles.css`

### 2026-02-24 — HoReCa CRM Assignment Feature

- **New "Assignment" section** in HoReCa CRM detail panel (collapsible, between Status Update and Meetings)
- **Assign/reassign** HoReCa records to team members via dropdown (7 members + "Other..." freeform)
- **Assignment history** tracked with timestamped entries: `[date|author] → assignee`
- **New sheet columns**: `BN: Assigned_To`, `BO: Assignment_History`
- **Backend**: `assigned_to` field in update endpoint, history appended automatically, migration endpoint
- **Files modified**: `google_services.py`, `endpoints.py`, `index.html`, `app.js`, `styles.css`

### 2026-02-12 (v59) — HoReCa Data Tab

#### HoReCa Integration
- **New 6th navigation tab** — "HoReCa" with restaurant SVG icon
- **Map sub-tab**: Leaflet.js (CDN, dynamic load) with 4 toggleable layers:
  - Taluka boundaries, Meso zones (heatmap), Micro zones (choropleth), HoReCa points
  - Frosted glass controls + stats pill
- **Explorer sub-tab**: Card-based browser, 50/page, 6 filters, expand/collapse cards
- **Summary sub-tab**: 5 stat cards + 6 breakdown tables
- **Data**: 4 static JSON/GeoJSON files in `frontend/data/horeca/` (~9.6 MB total)
- **Source**: Data exported by HoReCa Collection `segment.py` pipeline
- **Lines added**: ~730 in app.js, ~400 in styles.css
- **Cache**: v=58 → v=68

### 2026-02-10 (v56) — Navigation Overhaul

#### Bottom Nav + Left Sidebar (#18)
- **Replaced top tab bar** with responsive navigation:
  - **Mobile**: Fixed bottom nav bar with 5 SVG icon buttons + labels + badge overlays
  - **Desktop**: Full-height left sidebar (60px/180px), collapsible via hamburger toggle
- **HTML**: `<nav class="tabs">` → `<nav class="nav-bar">`, `<button class="tab">` → `<button class="nav-item">`
- **CSS**: New `.nav-bar`, `.nav-item`, `.nav-icon`, `.nav-label`, `.nav-badge`, `.sidebar-toggle` styles
  - Desktop header fixed at `left: 60px`, sidebar at `top: 0` (full height)
  - Seamless blue bar: sidebar toggle + header use flat `var(--primary)`, no gradient, no border between them
  - Sidebar border via `::after` pseudo-element only below 64px blue zone
- **JS**: All `.tab` selectors → `.nav-item`, `tab-badge` → `nav-badge`, new `toggleSidebar()` function
- **Bug fix**: `navigateToVP()` now calls `showDetailPanel()` for mobile escalation card clicks
- **5 tabs**: VPs, Dashboard, Meetings, Escalation, Today (with red/blue/gray badge overlays on icons)

### 2026-02-05 (v12)

#### Dashboard Holistic Redesign (#16)
- **Reduced to 4 main tabs**: Update VP | Dashboard | Meetings | VP List
- **BDO integrated into Dashboard > Progress**:
  - Removed standalone BDO Tracker tab
  - BDO section now appears in Progress sub-tab with compact grid
- **Holistic Pipeline Funnel**: New horizontal scrollable funnel showing complete flow:
  - Blocks (12) → Blocks Unlocked → VPs Accessible → Contacted → Meetings Done → Location OK → NOC Received → Agreement → Installed
- **"VPs Accessible" metric**: Shows VPs in blocks where BDO meeting is done
- **Stage filter** added to Block-wise VP Progress

#### Meeting Manager (#17)
- **New Meetings tab** with full meeting management
- **Meeting-Assignments sheet**: New Google Sheet tab for tracking
- **Event Types**:
  - `calendar_event` - Full meeting with duration (creates Google Calendar)
  - `task_reminder` - 1-minute reminder
  - `milestone` - Record only, no calendar entry
- **Features**: Filter by time/block/type, edit, mark complete, cancel
- **Schedule Follow-up button** in VP details (always available)
- Synced 14 existing calendar events to Meeting-Assignments sheet

#### Earlier v7 Changes
- **Conversation History Preservation**: Meeting notes now append with timestamps
  - Pattern: `[2026-02-05 10:30] New note\n---\n[Previous notes]`
- **Unlimited RVM Location Capture**: Removed dependency on agreed RVMs count
- **Calendar Time Selection**: Follow-up reminders support specific times
- Added BDO Tracker feature (5 stages, BDO-Tracker sheet)
- Added collapsible Profile & Status sections

### 2026-02-04
- Gamified dashboard with block progress cards
- RVM and Cost dashboards
- Block modal with VP list
- Sarvam AI voice processing fix
