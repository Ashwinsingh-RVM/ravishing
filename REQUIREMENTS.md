# Requirements Tracker

**Last Updated**: 2026-02-05 (Session 3)

---

## Workflow

**IMPORTANT**: When a new requirement is mentioned:
1. Add it to the backlog with I/E scoring
2. Display the full requirements table
3. Recommend what to build next
4. **Wait for alignment before implementing**

---

## Scoring System

### Impact (I) Score - How valuable is this?

| Score | Level | Criteria |
|-------|-------|----------|
| **3** | High | Blocks daily operations, security risk, or 50%+ productivity gain |
| **2** | Medium | Improves workflow, reduces friction, nice-to-have enhancement |
| **1** | Low | Cosmetic, informational, or rarely used feature |

**How to determine I score:**
- Does it block work? → I=3
- Does it save significant time daily? → I=3
- Is it a security concern? → I=3
- Does it make something easier but not critical? → I=2
- Is it just nice to have or informational? → I=1

### Effort (E) Score - How much work/tokens required?

| Score | Level | Est. Tokens | Time | Scope |
|-------|-------|-------------|------|-------|
| **1** | Low | 5K-15K | <30 min | CSS/HTML only, single file |
| **2** | Medium | 15K-40K | 1-3 hrs | Multiple files, moderate logic |
| **3** | High | 40K-100K+ | 4+ hrs | New services, external APIs, data sourcing |

### Priority Score

**I/E Ratio** = Impact ÷ Effort
- **≥2.0** → Implement immediately (high value, low cost)
- **1.0-1.9** → Evaluate and discuss
- **<1.0** → Defer unless strategically important

---

## Active Backlog (Priority Order)

| Rank | # | Requirement | I | E | Est. Tokens | I/E | Status |
|------|---|-------------|---|---|-------------|-----|--------|
| 1 | **25** | **🐛 BUG: Mobile scroll stuck** - VPs tab not scrolling on mobile | 3 | 1 | ~5K | **3.0** | **NEW - BUG** |
| 2 | **30** | **🐛 BUG: Schedule Meeting broken** - Button on Meetings tab not working | 3 | 1 | ~5K | **3.0** | **NEW - BUG** |
| 3 | **28** | **Evaluate: Schedule Meeting vs Follow-up** - Are both needed? Confusing? | 1.5 | 0.5 | ~3K | **3.0** | **NEW - EVAL** |
| 4 | **26** | **Remove Voice Record Button** - Remove mic button from meeting notes | 1 | 0.5 | ~2K | **2.0** | **NEW** |
| 5 | **27** | **Comments Section Revamp** - Rename, add anytime, timestamps, user attribution (Notion-style) | 3 | 2 | ~20K | **1.5** | **NEW** |
| 6 | 24 | **Today's Activity View** - All updates/contacts made today | 3 | 2 | ~25K | **1.5** | **NEW** |
| 7 | **31** | **Import Legacy Meeting Notes** - Parse old notes, clean junk, show as "Legacy" | 2 | 1.5 | ~15K | **1.33** | **NEW** |
| 8 | **23** | **Evaluate: Meetings Tab UX** - Better UI/UX for readability & understanding | 2 | 1 | **2.0** | **NEW - EVAL** |
| 9 | ~~29~~ | ~~VP Summary Line~~ | 2 | 1.5 | 1.33 | **DEFERRED** |
| 10 | 18 | Desktop-optimized layout when opened on desktop | 2 | 2 | ~25K | **1.0** | ✅ DONE |
| 11 | 8 | Photo capture for RVM locations | 2 | 2 | ~25K | **1.0** | EVALUATE |
| 12 | 7 | Gated access - @recykal.com emails only | 3 | 2.5 | ~30K | **1.2** | DEPRIORITIZED |
| 13 | 10 | Voice input revamp (better UX, feedback) | 2 | 3 | ~50K | **0.67** | DEFER |
| 14 | 11 | Telegram bot for field updates | 2 | 3 | ~60K | **0.67** | DEFER |
| 15 | 9 | VP metadata (population, class, known for) | 1 | 3 | ~70K | **0.33** | DEFER |

**Note**: #7, #13, #14, #15, #16, #17, #18, #19, #21, #22, #32, #33, #34, #35, #36 **COMPLETED**.

---

## Recommendation

### Build Now (I/E ≥ 1.3) ⚡
| # | Requirement | I | E | I/E | Notes |
|---|-------------|---|---|-----|-------|
| 24 | **Today's Activity View** | 3 | 2 | **1.5** | Daily standup visibility, accountability |
| 23 | **Group Meetings by Date** | 2 | 1.5 | **1.33** | Better meeting planning UX |

### Next Up (I/E 1.0-1.3)
| # | Requirement | I | E | I/E | Notes |
|---|-------------|---|---|-----|-------|
| 8 | Photo capture for RVM locations | 2 | 2 | **1.0** | Camera API integration |

### Current Tab Structure (after #18 Master-Detail):
```
VPs | Dashboard | Meetings  (3 tabs - consolidated)
```
- VPs tab has master-detail layout (list + details side-by-side on desktop)
- BDO is integrated into Dashboard > Progress sub-tab

### Proposed Update VP Layout (after #19, #21, #13):
```
┌─────────────────────────────────────────┐
│ [Block ▼] [VP ▼]                        │
├─────────────────────────────────────────┤
│ ▸ Current Status (collapsed by default) │
│   - Stage, Stage Date, Follow-up Date   │
│   - Stage update dropdown               │
├─────────────────────────────────────────┤
│ ▸ Meetings (if any scheduled)           │
│   - Upcoming meetings for this VP       │
│   - Schedule new meeting button         │
├─────────────────────────────────────────┤
│ ▸ Conversation History                  │
│   - Timeline of all past notes          │
│   - Most recent first                   │
├─────────────────────────────────────────┤
│ ▸ VP Profile                            │
│   - Contact info, RVM details, costs    │
└─────────────────────────────────────────┘
```

### What #16 Delivered:
1. ✅ Removed BDO Tracker as main tab → merged into Dashboard > Progress
2. ✅ Dashboard Progress sub-tab now has 3 sections:
   - **Holistic funnel**: Blocks → Blocks Unlocked → VPs Accessible → Contacted → Meetings Done → Location OK → Email Sent → NOC Received → Agreement Sent → Agreement Signed → Installed
   - **BDO Progress**: 12 compact block cards with BDO status (click to update)
   - **Block VP Progress**: Gamified cards with stage dropdown filter
3. ✅ "VPs Accessible" metric shows VPs in blocks where BDO meeting is done

### Deprioritized
| # | Requirement | I/E | Reason |
|---|-------------|-----|--------|
| 7 | Gated Access | 1.2 | User confirmed not a current problem |

### Defer (I/E < 1.0)
- #9, #10, #11 - Lower priority, higher effort

---

## Detailed Analysis

### #25: 🐛 BUG - Mobile Scroll Stuck (NEW - Session 3)
**I=3** (Blocks mobile usage - field team can't use the app!)
**E=1** (~5K tokens: CSS fix for overflow/height issues)

**Problem:**
- VPs tab (master-detail layout) scroll is stuck on mobile
- Users cannot scroll through VP list or VP details

**Likely Cause:**
- `overflow: hidden` on `.master-detail-layout` container
- Fixed height calculation `height: calc(100vh - 120px)` not working on mobile
- Missing `-webkit-overflow-scrolling: touch` for iOS

**Fix approach:**
- Review CSS for `.master-detail-layout`, `.master-panel`, `.detail-panel`
- Ensure proper overflow-y: auto on scrollable containers
- Test on mobile viewport

---

### #26: Remove Voice Record Button (NEW - Session 3)
**I=1** (Cleanup - feature not being used)
**E=0.5** (~2K tokens: Remove HTML element and related JS)

**Scope:**
- Remove the microphone/record button from meeting notes textarea
- Remove associated JS for voice recording (or keep for future use)
- Simple HTML/CSS cleanup

---

### #27: Comments Section Revamp (NEW - Session 3)
**I=3** (Critical for tracking all interactions with VP)
**E=2** (~20K tokens: UI changes, data consolidation, add comment feature)

**Current State:**
- "Conversation History" section shows past meeting notes
- Notes can only be added during Status Update
- No attribution of who added the note

**Requirements:**
1. **Rename** "Conversation History" → "Comments" (or "Activity Log" / "Notes")
2. **Add Comment Anytime** - New input field to add comment without changing status
   - Use case: "Called, they said call back tomorrow" (status still "Yet to Meet")
3. **Consolidate All Notes** - Show notes from:
   - Status Update meeting notes
   - Meeting Schedule notes
   - Direct comments added here
   - Legacy imported notes (#31)
4. **Timestamps** - Human-readable format (e.g., "2 hours ago", "Feb 5, 10:30 AM")
5. **Chronological Order** - Latest on top
6. **User Attribution** - Capture who added the comment
   - Display in Notion-style quote format with avatar/initials

**Proposed UI (Notion-style):**
```
┌─────────────────────────────────────────┐
│ ▼ Comments (4)                          │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ Add a comment...              [Post]│ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 💬 Chaitanya • Today, 2:30 PM       │ │
│ │ ┃ Called secretary, asked to call   │ │
│ │ ┃ back tomorrow after 11 AM.        │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 📅 Rahul • Feb 4, 10:00 AM          │ │
│ │ ┃ First meeting done. They are      │ │
│ │ ┃ interested but need panch approval│ │
│ │ (from Meeting)                       │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 📜 Legacy • Feb 2024                │ │
│ │ ┃ Met with sarpanch, discussed      │ │
│ │ ┃ location options near market.     │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**Comment Types:**
- 💬 Direct comment (added via Comments section)
- 📅 Meeting note (from Status Update or Meeting Schedule)
- 📜 Legacy (imported from old meeting notes)

---

### #31: Import Legacy Meeting Notes (NEW - Session 3)
**I=2** (Preserves historical context from before system existed)
**E=1.5** (~15K tokens: Parse file, clean data, import to sheet)

**Source File:** `/Requirements/Older meeting notes.md`

**Data Structure (observed):**
```
🏛️ Follow-up: [VP Name] VP ([Block])
Follow-up meeting for Goa DRS RVM deployment
Village Panchayat: [VP Name]
Block: [Block]
Contact: - Secretary: [Name] - Phone: [Number]
Notes: [Actual meeting notes]
--- Created by Goa DRS Tracker
```

**Cleanup Required:**
- Remove "🏛️ Follow-up:" prefix
- Remove "Follow-up meeting for Goa DRS RVM deployment" boilerplate
- Remove "Village Panchayat:", "Block:", "Contact:" sections (redundant)
- Remove "--- Created by Goa DRS Tracker" suffix
- Extract only the actual "Notes:" content

**Import Process:**
1. Parse the markdown file
2. Match VP names to existing VPs in sheet (fuzzy match if needed)
3. Clean the notes text
4. Add to VP's meeting notes with timestamp "Legacy (pre-Feb 2025)"
5. Display in Comments section with 📜 Legacy badge

**Example Transformation:**
```
BEFORE:
🏛️ Follow-up: Mayem VP (BICHOLIM)
...
Notes: Met the Sarpanch and the Panch member. Explained them everything.
Sarpanch said he support this and wanted us to come and explain this in the
Panch meeting. --- Created by Goa DRS Tracker

AFTER (in Comments):
📜 Legacy • Pre-Feb 2025
┃ Met the Sarpanch and the Panch member. Explained them everything.
┃ Sarpanch said he support this and wanted us to come and explain
┃ this in the Panch meeting.
```

---

### #28: Evaluate - Schedule Meeting vs Schedule Follow-up (NEW - Session 3)
**I=1.5** (UX clarity - avoid user confusion)
**E=0.5** (~3K tokens: Analysis + recommendation)

**Current State:**
- "Schedule Follow-up" button below VP status badge
- "Schedule Meeting" button in Meetings tab

**Questions to Answer:**
1. Do they do the same thing?
2. Is having both confusing?
3. Should we consolidate or differentiate?

**Recommendation (pending evaluation):**
- If same → Remove one, keep in most logical place
- If different → Clarify labels (e.g., "Quick Reminder" vs "Full Meeting")

---

### #29: VP Summary Line (NEW - Session 3)
**I=2** (Quick context without expanding sections)
**E=1.5** (~12K tokens: Generate summary, display in UI, update cards)

**Requirements:**
1. **Below Status Badge** - 1-2 line summary of current situation
   - e.g., "Called 3 times, waiting for panch meeting date"
   - e.g., "NOC received, pending service agreement"
2. **On List Cards** - Same summary on master list VP cards
   - May need to redesign card height to fit

**Summary Generation:**
- Option A: Manual entry (user types summary)
- Option B: Auto-generated from latest comment + stage
- Option C: AI-generated from all comments (higher effort)

**Recommended:** Option B (auto from latest comment, truncated)

---

### #30: 🐛 BUG - Schedule Meeting Not Working (NEW - Session 3)
**I=3** (Core feature broken)
**E=1** (~5K tokens: Debug and fix)

**Problem:**
- "Schedule Meeting" button on Meetings tab not working
- Need to debug: Is it JS error? API error? Modal not opening?

---

### #24: Today's Activity View (NEW - Session 3)
**I=3** (Critical for daily standups, manager visibility, accountability)
**E=2** (~25K tokens: New view, query filters, aggregation logic)

**What it shows:**
- All VP stage updates made today
- All BDO stage updates made today
- All meetings scheduled/completed today
- All VPs contacted today (meeting notes added)
- Summary metrics: "Today: 5 VPs contacted, 2 BDO meetings, 3 stage updates"

**UX Options:**

**Option A: Dashboard Sub-tab**
```
Dashboard: Progress | RVM | Cost | **Today**
```
- New "Today" sub-tab in Dashboard
- Shows activity feed with timestamps
- Filter by: All / VP Updates / BDO Updates / Meetings

**Option B: Floating Summary Card**
```
┌─────────────────────────────────┐
│ 📅 Today's Activity             │
│ ✅ 5 VPs updated                │
│ 🏛️ 2 BDO meetings               │
│ 📞 3 contacts made              │
│ [View Details →]                │
└─────────────────────────────────┘
```
- Always visible on Dashboard
- Click expands to full activity list

**Option C: Dedicated "Activity" Tab**
- New main tab: VPs | Dashboard | Meetings | **Activity**
- Full activity log with date picker
- Filter by user, block, action type

**Data Source:**
- `Last_Updated` column in DRS-Tracker (for VP updates)
- `Stage_Date` column (for stage changes)
- Meeting-Assignments sheet (for meetings)
- BDO-Tracker `Last_Updated` (need to add column)

---

### #23: Evaluate Meetings Tab UX (UPDATED - Session 3)
**I=2** (Better UX for planning, easier to see daily schedule)
**E=1** (~8K tokens: Research & recommend, no implementation yet)

**Current State:**
- Flat list of meetings sorted by date
- Hard to see "What's happening on Feb 6th?"
- Unclear information hierarchy

**Evaluation Scope:**
1. Review current Meetings tab layout and pain points
2. Research best practices for meeting/calendar UIs
3. Propose 2-3 UX options with pros/cons
4. Consider mobile-first (field team) vs desktop (manager review)
5. Recommend best approach

**Possible Directions to Explore:**

**Option A: Date Accordion**
- Grouped by date, expandable sections
- Today expanded by default

**Option B: Horizontal Date Carousel**
- Swipeable date tabs
- Mobile-friendly

**Option C: Calendar Grid View**
- Mini calendar showing meeting counts
- Click date to see that day's meetings

**Option D: Timeline View**
- Vertical timeline with meetings as nodes
- Visual connection between past and upcoming

**Option E: Kanban-style**
- Columns: Today | This Week | Later
- Drag to reschedule (if feasible)

**Deliverable:** UX recommendation document before implementation.

---

### #29: VP Summary Line (DEFERRED)
**Status:** Deferred per user request (Session 3)
**Original Scope:** 1-2 line summary below status + on list cards
**Reason:** Not priority right now, can revisit later

---

### #15: VPs Unlocked Metric in Pipeline Funnel (NEW)
**I=2** (Shows which VPs are accessible based on BDO meeting status)
**E=1.5** (~12K tokens: Cross-reference BDO data, add to pipeline)
- Logic: BDO stage >= "meeting_done" → Block is unlocked → VPs under that block are "unlocked"
- Add "VPs Unlocked" as a step in pipeline funnel after Total VPs
- Helps field team know which VPs they can start approaching

### #17: Calendar/Meeting Manager (NEW - CRITICAL)
**I=3** (Critical for operations - wrong meetings cause confusion, team coordination needed)
**E=2.5** (~45K tokens: New feature area, multiple components)

**Sub-components:**

| Component | Description | Effort |
|-----------|-------------|--------|
| **A. Edit Calendar Invites** | Fix wrong date/time for VP meetings | ~12K |
| **B. Meeting Manager View** | List all scheduled meetings, filter by date/block | ~15K |
| **C. Assignment/Tagging** | Who is attending which meeting | ~18K |

**Technical Considerations:**
- Google Calendar API supports: create, update, delete, list events
- Google Calendar does NOT support custom tags natively
- **Solution**: Store tags/assignments in our Google Sheet or local state
  - New columns: `Event_ID`, `Assigned_To`, `Meeting_Tags`
  - Or new sheet tab: `Meeting-Assignments`

**Proposed Design:**
```
┌─────────────────────────────────────────────────────────────┐
│ MEETING MANAGER (new tab or section)                        │
├─────────────────────────────────────────────────────────────┤
│ Filter: [This Week ▼] [All Blocks ▼] [My Meetings ▼]       │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📅 Feb 6, 10:00 AM - Bardez VP: Aldona                  │ │
│ │ Assigned: Rahul, Priya  [Edit] [Assign+]                │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📅 Feb 6, 2:00 PM - Bicholim VP: Sanquelim              │ │
│ │ Assigned: -  [Edit] [Assign+] [Tag Me]                  │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Integration with #14 findings:**
- Could be a new main tab: Update VP | Dashboard | **Meetings** | VP List
- Or a new Dashboard sub-tab: Progress | RVM | Cost | **Meetings**

### #16: Dashboard Holistic Redesign (SCOPED by #14)
**I=2.5** (Comprehensive progress view, better decision making)
**E=2** (~30K tokens: Redesign layout, multiple metrics, cross-reference)

**Scope (refined):**
1. Remove BDO Tracker as main tab → integrate into Dashboard > Progress
2. Dashboard keeps 3 sub-tabs: **Progress | RVM | Cost**
3. **Progress sub-tab redesign:**
   - **Section 1: Holistic Funnel** (horizontal flow)
     - Blocks (12) → Blocks Unlocked → VPs Unlocked → Meetings Done → Locations OK → Agreements → Installed
   - **Section 2: BDO Progress** (moved from separate tab)
     - 12 block cards showing BDO status
     - Click to update BDO stage (existing modal)
   - **Section 3: Block-wise VP Progress**
     - Dropdown to filter by stage
     - Block cards showing VP progress
4. Main nav reduces: **Update VP | Dashboard | VP List** (3 tabs)

**Visual hierarchy shows the flow:**
```
BDO Meeting Done → Block Unlocked → VPs can be approached → Pipeline stages
```

**Includes #15** (VPs Unlocked metric) - merged into holistic funnel

### #12: Collapsible Profile & Status Sections - COMPLETED
**I=2** (Reduces visual clutter, easier to focus on current task)
**E=1** (~10K tokens: CSS accordion/toggle, JS click handlers)

### #13: Conversation History Section (EXPANDED)
**I=2** (Context from past meetings helps follow-up)
**E=1.5** (~12K tokens: Parse timestamped notes, display in readable format)
- Notes are stored as: `[timestamp] note\n---\n[older notes]`
- Display as a dedicated "Conversation History" section in Update VP tab
- Timeline/card format showing all past interactions
- Most recent first, scrollable if many entries

### #18: Desktop-Optimized Layout (NEW)
**I=2** (Office review of data benefits from larger screen usage)
**E=2** (~25K tokens: CSS media queries, responsive breakpoints, layout adjustments)
- Currently mobile-first design
- On desktop (>1024px): Two-column layout, sidebar navigation, wider cards
- Better data density for office review sessions
- Maintain consistency with mobile for field team familiarity

### #19: Collapsibles Default Closed (NEW)
**I=1.5** (Reduces visual clutter when VP is selected)
**E=0.5** (~3K tokens: Change default state in JS, minor CSS)
- On Update VP page, all collapsible sections start closed
- User expands what they need
- Less overwhelming initial view
- **Quick win - high I/E ratio**

### #21: Reorder Update VP Tab Layout (NEW)
**I=2** (Better workflow - see current state before editing details)
**E=1** (~8K tokens: HTML reordering, minor JS adjustments)
**New order:**
1. **Current Status** - Stage, stage date, follow-up date (what's happening now)
2. **Meetings** - Scheduled/past meetings for this VP (if any exist)
3. **Conversation History** - All past notes/comments (context)
4. **VP Profile** - Contact info, RVM details, costs (reference data)

**Rationale:** Status first tells you where things stand. Meetings shows upcoming actions. History provides context. Profile is reference info you rarely change.

### #22: Single Calendar Invite per VP/BDO (NEW)
**I=2.5** (Prevents calendar clutter, avoids confusion from multiple invites)
**E=2** (~20K tokens: Track event IDs, check before creating, update existing)
**Logic:**
- Before creating new calendar event, check if VP already has one scheduled
- If existing event found → Update it (date/time) instead of creating new
- Store `calendar_event_id` in Meeting-Assignments sheet (already exists)
- For BDO meetings: Track separately per block
- Option to force new event if needed (e.g., different type of meeting)

### #14: Evaluate Tab View Crowding (NEW)
**I=1.5** (Research task to inform UX decisions)
**E=1** (~5K tokens: Analysis only, no code changes)
- Review current 4 tabs: Update VP, Dashboard, VP List, BDO Tracker
- Assess if information architecture is optimal
- Recommend restructuring if needed

### #7: Gated Access (@recykal.com only) - DEPRIORITIZED
**I=3** (Security risk if unauthorized users can modify data)
**E=2.5** (~30K tokens: OAuth flow, session management, email validation)
**Note**: User confirmed unauthorized access is NOT a current problem

### #8: Photo Capture
**I=2** (Helpful but WhatsApp works as alternative)
**E=2** (~25K tokens: Camera API, image upload, storage setup)

### #9: VP Metadata
**I=1** (Informational only, doesn't affect operations)
**E=3** (~70K tokens: Data sourcing for 191 VPs + implementation)

### #10: Voice Revamp
**I=2** (Current voice works, this is polish)
**E=3** (~50K tokens: Significant frontend rework)

### #11: Telegram Bot
**I=2** (Alternative channel, not essential)
**E=3** (~60K tokens: New service, bot setup, deployment)

---

## Decision Log

| Date | Decision | Requirements |
|------|----------|--------------|
| 2026-02-05 | Implemented high I/E items | #1, #2, #3 |
| 2026-02-05 | Implemented profile UX bundle | #4, #5, #6 |
| 2026-02-05 | Implemented collapsible sections | #12 |
| 2026-02-05 | Completed tab evaluation, merged #15 into #16 | #14, #15 → #16 |
| 2026-02-05 | **Implemented Meeting Manager** | #17 |
| 2026-02-05 | **Implemented Dashboard Holistic Redesign** | #16 (BDO integrated, 4 tabs) |
| 2026-02-05 | **Implemented Update VP UX bundle** | #13, #19, #21, #22 |

---

## Completed (19 items)

| # | Requirement | I | E | I/E | Date |
|---|-------------|---|---|-----|------|
| 36 | Escalation Tab: VPs stuck in stages (First Meeting Done, Panch Meeting Done, Email Sent, NOC Received, Agreement Sent) with 2d/3d/3+d severity, excludes 2nd Saturdays | 3 | 2 | 1.5 | 2026-02-10 |
| 35 | Pipeline 0s bug fix: Data race in initApp — setupTabs ran before loadVPData | 3 | 1 | 3.0 | 2026-02-10 |
| 34 | NOC Tracking Columns: NOC_Email_Sent_Date, Email_Read, Signed_NOC_Date + Days Since computed | 2 | 1 | 2.0 | 2026-02-10 |
| 33 | Deployment Pipeline: Add Email Sent & Agreement Sent steps, equal-width blocks | 2 | 1 | 2.0 | 2026-02-10 |
| 32 | Email + PIN authentication (Authorized-Users sheet, signed cookies, login screen) | 3 | 2 | 1.5 | 2026-02-10 |
| 22 | Single calendar invite per VP/BDO (edit existing) | 2.5 | 2 | 1.25 | 2026-02-05 |
| 21 | Reorder Update VP: Status → Meetings → History → Profile | 2 | 1 | 2.0 | 2026-02-05 |
| 19 | Collapsibles default closed on Update VP | 1.5 | 0.5 | 3.0 | 2026-02-05 |
| 13 | Conversation History section (timeline of past notes) | 2 | 1.5 | 1.33 | 2026-02-05 |
| 16 | Dashboard Holistic Redesign (BDO integrated, VPs Unlocked metric) | 2.5 | 2 | 1.25 | 2026-02-05 |
| 17 | Calendar/Meeting Manager (edit, view, assign, event types) | 3 | 2.5 | 1.2 | 2026-02-05 |
| 14 | Tab view crowding evaluation (research) | 1.5 | 1 | 1.5 | 2026-02-05 |
| 12 | Make Profile & Status sections collapsible | 2 | 1 | 2.0 | 2026-02-05 |
| 1 | Conversation history preservation | 3 | 2 | 1.5 | 2026-02-05 |
| 2 | Unlimited RVM location capture | 3 | 2 | 1.5 | 2026-02-05 |
| 3 | Calendar time selection (1-min reminders) | 2 | 1 | 2.0 | 2026-02-05 |
| 4 | Make Save Profile button prominent | 2 | 1 | 2.0 | 2026-02-05 |
| 5 | Visually distinguish Profile/Status sections | 2 | 1 | 2.0 | 2026-02-05 |
| 6 | Group profile fields into subsections | 2 | 1 | 2.0 | 2026-02-05 |
