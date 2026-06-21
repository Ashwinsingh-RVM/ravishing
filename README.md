# Goa DRS - Village Panchayat Collection Point Mapping

A comprehensive tracking system for managing the Reverse Vending Machine (RVM) deployment across all Village Panchayats in Goa under the Deposit Return Scheme (DRS).

## Overview

Goa is divided into **12 blocks**, each managed by a Block Divisional Officer (BDO). This system tracks the progress of RVM deployment across all Village Panchayats within these blocks.

## Workflow Stages

| Stage | Description |
|-------|-------------|
| `yet_to_meet` | Village Panchayat not yet contacted |
| `meeting_scheduled` | Meeting scheduled with VP |
| `first_meeting_done` | Initial meeting with Secretary/Sarpanch completed |
| `follow_up_required` | Follow-up action needed |
| `panch_meeting_scheduled` | Ward members (Panch) meeting scheduled |
| `panch_meeting_done` | Panch member meeting completed |
| `location_finalized` | Collection point location confirmed |
| `email_sent` | Confirmation email sent to VP |
| `noc_pending` | Waiting for NOC on letterhead |
| `noc_received` | NOC received from VP |
| `service_agreement_sent` | Service agreement shared |
| `service_agreement_signed` | Service agreement executed |
| `infra_pending` | Waiting for electricity/internet |
| `infra_complete` | Infrastructure ready |
| `device_deployed` | RVM physically placed |
| `device_installed` | RVM operational |

## Data Points Captured

- Block & BDO Information
- Village Panchayat Name & Code
- Secretary Name & Phone
- Sarpanch Name & Phone
- Email ID
- Location Details (GPS, Address)
- Infrastructure Status (Electricity, Internet, Shed)
- Meeting Notes & Follow-up Dates
- Document Status (NOC, Service Agreement)

## Features

- **Multi-language Input**: Voice/text input in Marathi, Hindi, and English
- **Smart Data Extraction**: AI-powered identification of data points from meeting notes
- **Google Sheets Integration**: Real-time sync with tracking spreadsheet
- **Analytics Dashboard**: Comprehensive visibility of deployment progress
- **HoReCa CRM**: Full CRM for Hotels, Restaurants, Cafes & Bars outreach with status tracking (De-listed → Call not answered → Pre-meeting mail sent → Meeting aligned → Meeting done → Post meeting mail sent → OB Form Opened → OB Form Filled), assignment, meetings, comments, and manual lead entry
- **Meeting Manager**: Week scroller with day-grouped view, time blocks (Morning/Afternoon/Evening), "Needs Scheduling" nudges for HoReCa, VP and HoReCa source badges, auto-meeting creation from CRM status changes
- **Role-Based Access Control**: 4 roles (admin, vp, horeca, new_joinee) with tab-level and data-level access control
- **URL-Based Routing**: Clean shareable URLs (`/VPs`, `/Dashboard`, `/HoReCa`, etc.) with browser back/forward support
- **Training Modules**: 4 interactive learning modules with gamification (XP, stars), leaderboard, per-user progress tracking
- **Reverse Logistics**: Standalone fleet planning tool with PTM-calibrated model, sensitivity analysis, and MoM comparison (`/rl`)

## Project Structure

```
Village Panchayat Collection Point Mapping/
├── src/
│   ├── api/                 # API endpoints
│   ├── services/            # Business logic
│   ├── models/              # Data models
│   ├── utils/               # Helper utilities
│   └── config/              # Configuration files
├── data/                    # Static data (blocks, VPs)
├── templates/               # Email & document templates
├── docs/                    # Documentation
└── tests/                   # Test files
```

## Requirements

- Python 3.9+
- Google Cloud credentials (Sheets, Gmail APIs)
- Sarvam AI API key (voice transcription)

## Deployment

- **Live**: https://ravishing-mindfulness-production.up.railway.app
- **GitHub**: https://github.com/ChDo17/goa-drs-tracker-march
- **Platform**: Railway (Nixpacks auto-detected Python)

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure `.env` with API credentials
4. Run: `uvicorn src.api.endpoints:app --reload`

## Documentation

| File | Description |
|------|-------------|
| `CLAUDE.md` | Project context for AI assistants |
| `CODEBASE.md` | Detailed technical documentation (code patterns, API reference) |
| `PROGRESS.md` | Development progress and changelog |
