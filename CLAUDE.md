# Goa DRS — Tracker App (Flask, deployed)

> **You are inside the `goa-drs` monorepo at `app/`.** This is the deployed Flask app served at `ravishing-mindfulness-production.up.railway.app`. Railway's Root Directory is set to `app/`. For the tool-wide module map, sync workflow, and how this folder relates to `horeca-pipeline/`, `training-source/`, and `reverse-logistics/`, see `../CLAUDE.md`.
>
> **Sync inbound from siblings before redeploy:**
> - `../horeca-pipeline/*.json|geojson` → `frontend/data/horeca/`
> - `../training-source/Module X/` → `frontend/training/module-X/`

## Project Context

This project is part of the **Goa Deposit Return Scheme (DRS)** implementation. The goal is to track the deployment of **Reverse Vending Machines (RVMs)** across all 193 Village Panchayats in Goa's 12 blocks.

### Business Flow

1. **Goa is divided into 12 blocks**, each managed by a Block Divisional Officer (BDO)
2. Team meets BDO → explains DRS concept → gets support to approach Village Panchayats
3. Team visits each Village Panchayat under that BDO:
   - Meets Secretary and Sarpanch (if available)
   - Explains DRS benefits to citizens
   - Requests space for RVM with high footfall
   - Requirements: shed, flat surface, electricity, internet
4. After location identification:
   - Send confirmation email with NOC template
   - VP prints NOC on letterhead, signs, stamps, returns
   - Service agreement is shared and signed
   - Infrastructure setup (electricity + internet)
   - Device deployment and installation

---

## 15 Deployment Stages (Milestones)

| # | Stage Value | Label | Pipeline Funnel |
|---|-------------|-------|-----------------|
| 1 | `yet_to_meet` | Yet to Meet | - |
| 2 | `first_meeting_scheduled` | First Meeting Scheduled | **Contacted** |
| 3 | `first_meeting_done` | First Meeting Done | **Meeting Done** |
| 4 | `panch_meeting_scheduled` | Panch Meeting Scheduled | Meeting Done |
| 5 | `panch_meeting_done` | Panch Meeting Done | Meeting Done |
| 6 | `location_finalized` | Location Finalized | **Location OK** |
| 7 | `email_sent` | Email Sent | Location OK |
| 8 | `noc_pending` | NOC Pending | Location OK |
| 9 | `noc_received` | NOC Received | **NOC Received** |
| 10 | `service_agreement_sent` | Service Agreement Sent | NOC Received |
| 11 | `service_agreement_signed` | Service Agreement Signed | **Agreement** |
| 12 | `infra_pending` | Infra Pending | Agreement |
| 13 | `infra_complete` | Infra Complete | Agreement |
| 14 | `device_deployed` | Device Deployed | Agreement |
| 15 | `device_installed` | Device Installed | **Installed** |

**Note**: Follow-ups are tracked separately via the Meetings system, not as a stage. Legacy data with `meeting_scheduled` or `follow_up_required` is migrated to `first_meeting_scheduled` and `first_meeting_done` respectively.

---

## Data Points Captured

### VP Identification
- Block Name
- VP Code
- VP Name
- BDO Name & Phone

### Contact Information
- Secretary Name & Phone
- Sarpanch Name & Phone
- VP Email ID
- Contractor Name & Phone

### RVM Tracking
- **Planned RVMs** (default: 1 per VP)
- **Agreed RVMs** (after negotiation)
- **RVM Locations** (GPS coordinates as JSON array)

### Cost & Operations
- **Electricity Cost Bearer**: VP / Recykal / Shared
- **Internet Cost Bearer**: VP / Recykal / Shared
- **Handler Hired By**: VP / Recykal
- **Space Type**: Free / Rental

### Stage Tracking
- Current Stage
- Stage Number (1-15)
- Stage Date
- Meeting Notes
- Follow-up Date

### Metadata
- Last Updated (timestamp)
- Updated By (user name)

---

## Google Sheet Column Mapping

**Sheet Name**: `DRS-Tracker` (42 columns: A-AP). Verified against live sheet 2026-05-28.

| Column | Field | Column | Field |
|--------|-------|--------|-------|
| A | Block | T | Location_Address |
| B | VP_Code | U | NOC_Status |
| C | VP_Name | V | NOC_URL |
| D | BDO_Name | W | Agreement_Status |
| E | BDO_Phone | X | Agreement_URL |
| F | Secretary_Name | Y | Infra_Electricity |
| G | Secretary_Phone | Z | Infra_Internet |
| H | Sarpanch_Name | AA | Infra_Shed |
| I | Sarpanch_Phone | AB | Device_Serial |
| J | VP_Email | AC | Contractor_Name |
| K | VP_Contact | AD | Contractor_Phone |
| L | Website | AE | Planned_RVMs |
| M | Address | AF | Agreed_RVMs |
| N | Current_Stage | AG | RVM_Locations (JSON) |
| O | Stage_Number | AH | Electricity_Cost_Bearer |
| P | Stage_Date | AI | Internet_Cost_Bearer |
| Q | Meeting_Notes | AJ | Handler_Hired_By |
| R | Follow_Up_Date | AK | Space_Type |
| S | Location_GPS | AL | Last_Updated |
| | | AM | Updated_By |
| | | AN | NOC_Email_Sent_Date |
| | | AO | Email_Read |
| | | AP | Signed_NOC_Date |

**Status columns vs file URL columns**: The sheet has `NOC_Status` (U) / `NOC_URL` (V) and `Agreement_Status` (W) / `Agreement_URL` (X). In practice these columns are **left empty by the team** — document tracking happens via the stage column (N) and `Signed_NOC_Date` (AP) only. As of 2026-05-28, U/V/W/X are 0 filled across all 205 rows. Don't assume a document was uploaded just because a row is at a NOC/agreement stage.

**Sheet Name**: `BDO-Tracker` (4 columns: A-D)

| Column | Field |
|--------|-------|
| A | Block |
| B | BDO_Name |
| C | BDO_Phone |
| D | Current_Stage |

**Sheet Name**: `Meeting-Assignments` (13 columns: A-M)

| Column | Field |
|--------|-------|
| A | Meeting_ID |
| B | VP_Code (or `HORECA:<place_id>` for HoReCa meetings) |
| C | VP_Name |
| D | Block |
| E | Event_Type |
| F | Event_Date |
| G | Event_Time |
| H | Assigned_To |
| I | Calendar_Event_ID |
| J | Status |
| K | Notes |
| L | Created_At |
| M | Event_Title |

---

## Technical Architecture

### Deployment
- **Platform**: Railway (https://railway.com)
- **URL**: https://ravishing-mindfulness-production.up.railway.app
- **Builder**: Nixpacks (auto-detected Python)

#### Railway Deploy Command
```bash
# IMPORTANT: This project has multiple services, so all three flags are required
railway up -p c1db1468-4fed-4efd-af43-8b9876e58012 -e d4e00643-7391-4df3-ba69-b1cbc8e49114 -s 4019e783-9894-4536-8694-1c4f75d7f3fc --detach
```

| Parameter | ID | Description |
|-----------|-----|-------------|
| `-p` (Project) | `c1db1468-4fed-4efd-af43-8b9876e58012` | Railway project ID |
| `-e` (Environment) | `d4e00643-7391-4df3-ba69-b1cbc8e49114` | Production environment |
| `-s` (Service) | `4019e783-9894-4536-8694-1c4f75d7f3fc` | Main web service |

#### Deployment Notes
- Build takes ~2-3 minutes to complete and activate
- Verify deployment: `curl -s "https://ravishing-mindfulness-production.up.railway.app/api/health"`
- Check logs: `railway logs -n 50 -s 4019e783-9894-4536-8694-1c4f75d7f3fc`
- Config stored in: `~/.railway/config.json`

### Backend Stack
- **Framework**: FastAPI
- **Language**: Python 3.11+
- **Authentication**: Google OAuth 2.0 (refresh token)

### Frontend Stack
- **Type**: Single Page Application (SPA)
- **Framework**: Vanilla JavaScript
- **Styling**: Custom CSS (mobile-first)
- **State**: LocalStorage for offline support

### External Services
| Service | Purpose | API Key Env Var |
|---------|---------|-----------------|
| Google Sheets | Data storage & sync | `GOOGLE_REFRESH_TOKEN` |
| Sarvam AI | Voice transcription (Hindi/Marathi/English) | `SARVAM_API_KEY` |

**Note**: Google Calendar integration was removed (2026-03-09). Meetings are now managed entirely via the in-app Meetings tab backed by the Meeting-Assignments Google Sheet.

---

## Project Structure

```
Village Panchayat Collection Point Mapping/
├── src/
│   ├── api/
│   │   └── endpoints.py          # FastAPI REST endpoints
│   ├── services/
│   │   ├── google_services.py    # Google Sheets/Gmail
│   │   ├── sarvam_processor.py   # Sarvam AI voice/text processing
│   │   └── tracker.py            # Main tracker service
│   ├── models/
│   │   └── entities.py           # Pydantic data models
│   ├── config/
│   │   └── settings.py           # Configuration & stages
│   └── main.py                   # Entry point
├── frontend/
│   ├── index.html                # Main SPA page
│   ├── app.js                    # JavaScript application
│   └── styles.css                # CSS styles
├── templates/                    # Email templates
├── requirements.txt              # Python dependencies
├── Procfile                      # Railway process file
├── CLAUDE.md                     # This context document
└── PROGRESS.md                   # Progress tracker
```

---

## API Endpoints

### Core Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve frontend application |
| GET | `/api/health` | Health check |
| GET | `/blocks` | List all 12 blocks |
| GET | `/stages` | List all 15 stages |

### VP Data Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vps/all` | Get all VP data from Google Sheet |
| POST | `/api/update/stage` | Update VP stage with notes |
| POST | `/api/update/profile` | Update VP profile (contacts, RVMs, costs) |

### Voice/Text Processing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/update/text` | Process text meeting notes |
| POST | `/update/voice` | Transcribe audio via Sarvam AI |

### BDO Tracker
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bdo/all` | Get all BDO tracking data (admin, vp) |
| POST | `/api/bdo/update` | Update BDO stage for a block |
| POST | `/api/bdo/init` | Initialize BDO-Tracker sheet (one-time) |

### Meeting Manager
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/meetings/all` | Get all meetings (past and future) |
| POST | `/api/meetings/create` | Create a new meeting/event |
| PUT | `/api/meetings/update` | Update an existing meeting |
| DELETE | `/api/meetings/{id}` | Delete/cancel a meeting |
| POST | `/api/meetings/init` | Initialize Meeting-Assignments sheet (one-time) |

### HoReCa CRM
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/horeca/crm` | Get filtered, paginated CRM data |
| POST | `/api/horeca/crm/update` | Update outreach fields (status, contacts, assignment) |
| POST | `/api/horeca/crm/add` | Add a new HoReCa lead manually |
| GET | `/api/horeca/crm/summary` | Get CRM dashboard summary stats |
| GET | `/api/horeca/crm/statuses` | Get valid outreach status list |
| POST | `/api/horeca/crm/init` | Initialize CRM column headers (one-time) |
| POST | `/api/horeca/crm/migrate-assignment` | Add assignment headers BN-BO (one-time) |

### Training
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/training/sync` | Sync training progress for authenticated user |
| GET | `/api/training/leaderboard` | Get training leaderboard (all users) |
| POST | `/api/training/reset` | Admin-only: reset a user's training progress |
| POST | `/api/training/init` | Initialize Training-Progress sheet (one-time) |

### SPA Routing
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/{path:path}` | SPA catch-all — serves `index.html` for frontend routes |

---

## Frontend Features

### Navigation (v72)
- **Mobile**: Fixed bottom nav bar with 6 SVG icons + labels + badge overlays
- **Desktop (≥1024px)**: Left sidebar (60px collapsed / 180px expanded), hamburger toggle at top
- **Tabs**: VPs | Dashboard | Meetings | Escalation | Today | HoReCa | Learning
- **Badges**: Escalation (red), Meetings (blue), Today (gray) — overlaid on icons
- **Sidebar state**: Persisted in `localStorage('sidebarExpanded')`
- **URL-based routing** (v72): Each tab has a clean URL (`/VPs`, `/Dashboard`, `/Meetings`, `/Escalation`, `/Today`, `/HoReCa`, `/Learning`). Uses `history.pushState`/`popstate`. Browser back/forward works. URLs are shareable and bookmarkable. SPA catch-all route on backend serves `index.html` for all frontend paths.
- **Route mapping**: `ROUTE_TO_TAB` and `TAB_TO_ROUTE` objects in app.js. URL path takes priority over localStorage on page load.

### 1. VPs Tab (Master-Detail Layout)
- Master panel: Searchable VP list with block/stage filters
- Detail panel: VP profile + stage update forms
- **VP Profile Section** (always editable):
  - Contact info (Secretary, Sarpanch, Contractor)
  - Planned/Agreed RVMs with GPS capture
  - Cost & Operations dropdowns
- **Stage Update Section**:
  - Stage dropdown (15 stages)
  - Meeting notes with voice recording
  - Follow-up date picker
  - Auto-creates calendar event

### 2. Dashboard Tab (3 Sub-views)

#### Progress View (Redesigned - #16)
- **Holistic Funnel** (horizontal scrollable):
  - Blocks (12) → Blocks Unlocked → VPs Accessible → Contacted → Meetings Done → Location OK → NOC Received → Agreement → Installed
  - "Blocks Unlocked" = BDO meeting done
  - "VPs Accessible" = VPs in unlocked blocks
- **BDO Progress** (integrated from former BDO tab):
  - Stats: Total, Meetings Done, Comms Sent
  - Compact 3-column grid of 12 block cards
  - Click card → Opens BDO update modal
- **Block-wise VP Progress**:
  - Stage dropdown filter
  - Gamified cards (gray→yellow→blue→green)
  - Progress bars with percentage
  - Achievement badges (💤✨🚀💪🔥🏆)
  - Rank medals for top 3 (🥇🥈🥉)
  - **Clickable** → Opens VP list modal

#### RVM View
- Total Planned vs Agreed RVMs
- Conversion rate percentage
- Block-wise comparison bars

#### Cost View
- Distribution charts for:
  - Electricity bearer
  - Internet bearer
  - Handler hired by
  - Space type
- Summary totals

### 3. Meetings Tab (Redesigned 2026-03-09)
- **Summary Stats**: Upcoming, Scheduled, Completed counts
- **"Needs Scheduling" section**: Shows HoReCa records with "Meeting aligned" status but no scheduled meeting. Each card has a "Schedule" button.
- **Week Scroller**: Horizontal Mon-Sun day pills with week navigation arrows (prev/next week). Day pills show colored dots (blue=VP, orange=HoReCa) when meetings exist that day. Today has a ring highlight, selected day is filled.
- **Day View**: Meetings grouped by time blocks (Morning <12, Afternoon 12-17, Evening 17+)
- **Filters**: Block, Type, Status (below week scroller)
- **Source Badges**: Blue "VP" or orange "HoReCa" badge on each meeting card
- **Meeting Cards**: Show time, source badge, VP/HoReCa name, type badge, block, assigned person
- **Event Types**:
  - **Meeting (with duration)**: Full meeting
  - **Task/Reminder**: Lightweight reminder
  - **Milestone (record only)**: No calendar entry
- **Actions per meeting**: Edit, Mark Complete, Cancel
- **Schedule Follow-up**: Available from VP details at any stage
- **RBAC**: Non-admin users only see meetings assigned to them
- **Google Sheet**: Meeting-Assignments tab with columns:
  - Meeting_ID, VP_Code, VP_Name, Block, Event_Type, Event_Date, Event_Time
  - Assigned_To, Calendar_Event_ID, Status, Notes, Created_At, Event_Title

### 4. Escalation Tab
- VPs stuck beyond working-day thresholds
- Severity groups: red (>3 days), amber (2-3), yellow (1-2)
- Filter by stage and severity
- **Click VP card** → Navigates to VPs tab detail view (mobile + desktop)

### 5. Today Tab
- Activity feed of VPs updated today (since 6 AM)
- Shows stage changes, notes, and timestamps

### 6. Block Modal (on block click)
- Block stats (Total, Done, Progress %)
- Search within block
- VP list sorted by progress
- Color-coded stage indicators
- **Click VP** → Navigate to Update tab

### 6. BDO Tracker (Integrated into Dashboard > Progress)
**Note**: As of #16, BDO is no longer a separate tab. It's integrated into Dashboard > Progress sub-tab.

- **4 BDO Stages**:
  1. Yet to Meet
  2. Meeting Scheduled
  3. Meeting Done
  4. Communication Sent to VPs
- **Click Card** → Opens modal to update BDO stage
- **Google Sheet**: BDO-Tracker tab with 4 columns (Block, BDO_Name, BDO_Phone, Current_Stage)

**Note**: Follow-ups for BDOs are tracked via the Meetings system, not as a stage.

### 7. HoReCa Data Tab (NEW — v59)
HoReCa (Hotels, Restaurants, Cafes, Bars) dataset integrated from the HoReCa Collection pipeline.

- **Data**: 4 static JSON/GeoJSON files in `frontend/data/horeca/` (~9.6 MB total, lazy-loaded)
- **Source**: Exported by `HoReCa Collection/segment.py` (separate project in Goa DRS folder)
- **3 Sub-tabs**: CRM (default), Board (Kanban), Dashboard
  - Map, Explorer, Summary sub-tabs archived (2026-02-24)
  - **Board view**: Kanban-style columns for each outreach status. Loads summary counts first (fast), then lazy-loads 50 cards per column in parallel. Click card → navigates to CRM detail panel. "Load more" pagination per column.
- **Current data**: 13,589 HoReCas, 1,007 micro zones, 243 meso zones, 3,453 alcohol-serving
- **CRM Features** (Google Sheets-backed, sheet `12YHTCeJxholgigzmGuf2GtTGsTREiS-EZj4Fod8B5x8`):
  - Master-detail layout with search, status/type/zone/city filters, pagination
  - **Detail panel sections**: Status Update, Assignment, Meetings, Comments, Contacts, Properties
  - **Assignment**: Searchable input with `<datalist>` — type to filter/search team members. Default list: Ayaan, Nupur, Aruna, Varsha, Chaithanya, Animesh, Vishwash. New names are persisted to localStorage and added to the datalist. Reassignment support, full history in `BO` column. Backend filtering is case-insensitive with whitespace trimming.
  - **CRM columns**: BB-BO (Outreach_Status through Assignment_History)
  - **HoReCa Outreach Statuses**: De-listed, Call not answered, Pre-meeting mail sent, Meeting aligned, Meeting done, Post meeting mail sent, OB Form Opened, OB Form Filled
  - **Add New Lead**: "+ Add Lead" button opens modal with collapsible sections (Basic Info, Contact Details, Business Details, Assignment, Notes). Creates row with `MANUAL_<timestamp>` Place ID.
  - **Meeting Scheduling**: "Schedule Meeting" button in Meetings collapsible section. Opens shared meeting modal in HoReCa mode (HoReCa-specific titles: First Meeting, Follow-up, Onboarding Discussion, Site Visit). Meetings stored in Meeting-Assignments sheet with `HORECA:<place_id>` in VP_Code column. Meeting cards shown in detail panel with edit/complete actions.
  - **Auto-Meeting Creation** (v70): When CRM status changes to "Follow-up" or "Meeting aligned", a meeting is auto-created in Meeting-Assignments sheet. Assigned to the HoReCa's `assigned_to` person (fallback: the updater). Duplicate prevention checks for existing scheduled meeting on same date. Uses `follow_up_date` or defaults to tomorrow.
- **2 Sub-tabs** (v70): CRM (default), Board (Kanban). Dashboard sub-tab moved to main Dashboard tab.

### 8. Dashboard Tab — Sub-tabs (v70)
Dashboard has RBAC-controlled sub-tabs:
- **Progress** — VP deployment funnel + BDO progress + block-wise VP cards (visible to admin, vp)
- **RVM** — Planned vs Agreed RVMs (visible to admin, vp)
- **Cost** — Electricity/Internet/Handler/Space distribution (visible to admin, vp)
- **HoReCa** — HoReCa CRM summary: outreach funnel, type/zone breakdown, recent activity (visible to admin, horeca)
- `applyDashboardRBAC()` hides sub-tabs based on role (horeca role sees only HoReCa sub-tab, vp role sees only VP sub-tabs)

### 9. Training / Learning Tab
- **Per-user localStorage** (v72): Training progress stored under `goa_drs_training_<email>` key to prevent cross-user contamination on shared devices. Training modules accept `?storageKey=` URL param.
- **localStorage key mismatch fix** (v72, Mar 26): Module HTML files (0-3) and `gamification.js` were updated to read `STORAGE_KEY` from the `?storageKey=` URL param (fallback: `goa_drs_training`). Previously they had the old hardcoded key, which broke cross-module progress and prerequisite checks. Known issue: existing users on old key may need to redo modules.
- **Admin reset**: `POST /api/training/reset` (Form: `email=...`) resets a user's training progress to zero in the Training-Progress sheet.
- Training module HTML files are now included in Railway deploy (`.railwayignore` exclusion removed 2026-03-18). Training URLs work in production.
- **Training source files live in a separate project:** `Recykal/Goa DRS/Training/Module X/`. When changes are made there, files must be copied to `frontend/training/module-X/` in this project and redeployed. This two-location workflow is critical and easy to forget.

### 10. Reverse Logistics Module (standalone)
- **Route**: `/rl` — standalone HTML page (`frontend/reverse-logistics.html`)
- **API**: `/api/rl/*` — months, run model, MoM comparison, sensitivity analysis, save/load defaults
- **Auth**: Exempt from auth middleware (standalone tool)
- **Backend**: `src/services/reverse_logistics.py` — PTM-calibrated fleet model
- **Nav**: Added as link in sidebar + More sheet (not a tab — uses `<a href="/rl">`)

### Known Gotchas
- **SPA catch-all intercepts file requests** (fixed 2026-03-16): The `/{path:path}` catch-all used to serve `index.html` for any path including `.json`/`.js` files. This caused `fetch('vp_data.json')` to get HTML back with 200 OK → JSON parse error → silent fallback to empty cache → dashboard zeros. Fix: catch-all now skips paths with file extensions. **DO NOT add `fetch()` calls for local files** — always use `/api/` endpoints.
- **Assigned-to filtering must be case-insensitive** (fixed 2026-03-18): Board/CRM assigned_to filter was exact match — missed records with case/whitespace differences. Always use `.strip().lower()` for comparison.
- **Training module localStorage key mismatch** (fixed 2026-03-26): Training module HTML files had hardcoded `goa_drs_training` storage key while the main app passed per-user `goa_drs_training_<email>` via `?storageKey=`. Fix: all module `index.html` files + `gamification.js` now read the key from URL param. **Remember:** training source is in `Recykal/Goa DRS/Training/` — edit there first, then copy to `frontend/training/` and redeploy.
- **Dashboard funnel is 100% stage-driven** (operational, recurring): Every funnel tile (`NOC Received`, `Agr Sent`, `Agr Signed`, `Installed`, etc.) is computed from `resolveStageNumber(vp) >= N` in `frontend/app.js`, reading only column N (`Current_Stage`). It does **not** look at `NOC_URL`, `Agreement_URL`, `Signed_NOC_Date`, or any document-presence signal. Recurring symptom: team brings back physically signed documents (or completes NOCs on the ground) but does not bump the VP's stage in the app → manual reconciliation diverges from dashboard count. Example: 2026-05-27 "Agr Signed = 40 vs manual reco = 50" — 9 VPs sat at `service_agreement_sent` with paper signatures and 1 (Sanquelim MC, NOR-005) was further back at `noc_received`; nothing was deleted, the stage was simply never advanced. **Audit method** when this happens: pull Drive revisions (`drive/v3/files/{id}/revisions`) → export each as XLSX → diff stage histograms over time. Drive retains ~12 days of revisions for active sheets. For finer-grained "was this cell ever set to X" checks, use the Sheets UI cell history (right-click cell → Show edit history). The Drive Revisions API only gives periodic snapshots; the cell history popup is the source of truth for individual edits.
- **`noc_received` < `service_agreement_sent` < `service_agreement_signed`** (workflow direction): The NOC and the Service Agreement are two separate documents in sequence. VP issues NOC first (stage 9), then Recykal sends SA to VP (stage 10), then VP signs SA and returns it (stage 11). A cell-history entry like `"noc_received" → "service_agreement_sent"` is **forward progression** (9 → 10), not a rollback.

---

### Design System (v70)
- **Fonts**: DM Sans (headings, `letter-spacing: -0.02em`) + Inter (body)
- **Primary color**: `#1e6b5c` (rich teal-green)
- **Shadows**: Layered dual-shadow system
- **Buttons**: Active `scale(0.97)` spring feedback
- **Modals**: `backdrop-filter: blur(8px)`, spring animation
- **Toasts**: Pill-shaped (24px radius)
- **Inputs**: 44px height, 1.5px border, 10px radius
- **All transitions**: `cubic-bezier(0.4, 0, 0.2, 1)`

---

## Role-Based Access Control (RBAC)

Added 2026-03-09. Authentication uses email + PIN → session cookie with `{name, email, role}`.

| Role | Tabs | Meetings Scope | Today Scope |
|------|------|---------------|-------------|
| `admin` | All 8 | All meetings | All activity |
| `vp` | VPs, Dashboard, Meetings, Escalation, Today, Learning | Own meetings only | VP updates + VP meetings |
| `horeca` | HoReCa, Dashboard, Meetings, Today, Learning | Own HoReCa meetings only | HoReCa meetings only |
| `new_joinee` | Learning only | N/A | N/A |

**Backend enforcement**: `require_role(request, allowed_roles)` on data endpoints.
**Frontend enforcement**: `applyRBAC()` hides nav items via `.rbac-hidden` CSS class.

---

## Environment Variables

```env
# Google OAuth (required)
GOOGLE_REFRESH_TOKEN=1//0g...

# Google Sheet
GOOGLE_SHEETS_ID=1gy0xNL7-ayFfVjf3ETvi8qN3bWytNGbRZg68nShnkEo

# Sarvam AI (for voice transcription)
SARVAM_API_KEY=sk_52rcjfng_...

# Notification emails
NOTIFICATION_EMAILS=gdrs_vpcpleads@recykal.com
```

---

## Key References

| Item | Value |
|------|-------|
| **Production URL** | https://ravishing-mindfulness-production.up.railway.app |
| **GitHub** | https://github.com/ChDo17/goa-drs-tracker-march |
| **Project Folder** | `/Users/chaithanyadonda/Documents/Claude Folder/Goa DRS/Village Panchayat Collection Point Mapping` |
| **Google Sheet ID** | `1gy0xNL7-ayFfVjf3ETvi8qN3bWytNGbRZg68nShnkEo` |
| **Tracker Sheet** | `DRS-Tracker` |
| **Railway Project** | `ravishing-mindfulness` |

---

## Requirements Workflow

**CRITICAL**: When a new requirement is mentioned:
1. **DO NOT build immediately**
2. Add to `REQUIREMENTS.md` with I/E scoring
3. Display the requirements table to user
4. Recommend what to build based on I/E
5. **Wait for user alignment before implementing**

### I/E Scoring

| Impact (I) | Score | Criteria |
|------------|-------|----------|
| High | 3 | Blocks work, security risk, 50%+ productivity gain |
| Medium | 2 | Improves workflow, nice-to-have |
| Low | 1 | Cosmetic, informational |

| Effort (E) | Score | Est. Tokens |
|------------|-------|-------------|
| Low | 1 | 5K-15K |
| Medium | 2 | 15K-40K |
| High | 3 | 40K-100K+ |

**Priority** = I/E ratio (higher = build first)

---

## Documentation Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project context and overview (this file) |
| `CODEBASE.md` | **Detailed technical documentation** - code structure, patterns, API reference |
| `PROGRESS.md` | Development progress and changelog |
| `REQUIREMENTS.md` | **Requirements backlog with I/E scoring** |
| `README.md` | Basic project overview |

**Important**: When making significant code changes, update `CODEBASE.md` with the new patterns, endpoints, or structure.

---

## Resume Instructions

After restarting Claude Code, say:

```
Continue with the Goa DRS VP tracker. Read CLAUDE.md and CODEBASE.md in the project folder for context.
```

Working directory: `/Users/chaithanyadonda/Documents/Claude Folder/Goa DRS/Village Panchayat Collection Point Mapping`
