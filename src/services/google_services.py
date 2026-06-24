"""
Google Services integration for Sheets, Calendar, and Gmail
Uses refresh token for authentication (no credentials.json needed)
"""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ..config.settings import Settings, DeploymentStage, STAGE_LABELS
from ..models.entities import VillagePanchayat, MeetingUpdate

settings = Settings()


def _safe_int(value, default=0):
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default

# OAuth configuration — from env vars or settings (loaded lazily to allow settings init first)
def _get_client_id():
    return os.getenv('GOOGLE_CLIENT_ID') or settings.google_client_id

def _get_client_secret():
    return os.getenv('GOOGLE_CLIENT_SECRET') or settings.google_client_secret

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/calendar',  # Kept for refresh token compat
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive',
]

# Cache for access token
_access_token_cache = {
    'token': None,
    'expiry': None
}


def get_access_token() -> str:
    """Get access token from refresh token"""
    global _access_token_cache

    # Return cached token if still valid
    if _access_token_cache['token'] and _access_token_cache['expiry']:
        if datetime.now() < _access_token_cache['expiry']:
            return _access_token_cache['token']

    refresh_token = os.getenv('GOOGLE_REFRESH_TOKEN') or settings.google_refresh_token

    if not refresh_token:
        raise ValueError("GOOGLE_REFRESH_TOKEN not configured")

    token_data = urllib.parse.urlencode({
        'client_id': _get_client_id(),
        'client_secret': _get_client_secret(),
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }).encode()

    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=token_data,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            token_json = json.loads(response.read().decode())
            _access_token_cache['token'] = token_json['access_token']
            _access_token_cache['expiry'] = datetime.now() + timedelta(
                seconds=token_json.get('expires_in', 3600) - 300
            )
            return _access_token_cache['token']
    except Exception as e:
        raise RuntimeError(f"Failed to get access token: {e}")


def get_google_credentials():
    """Get Google credentials using refresh token"""
    access_token = get_access_token()
    refresh_token = os.getenv('GOOGLE_REFRESH_TOKEN') or settings.google_refresh_token

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=_get_client_id(),
        client_secret=_get_client_secret(),
        scopes=SCOPES
    )
    return creds


class GoogleSheetsService:
    """Service for syncing data with Google Sheets tracker"""

    # Column mapping for the tracker sheet
    COLUMNS = {
        'A': 'sl_no',
        'B': 'block_name',
        'C': 'village_panchayat_name',
        'D': 'vp_code',
        'E': 'secretary_name',
        'F': 'secretary_phone',
        'G': 'sarpanch_name',
        'H': 'sarpanch_phone',
        'I': 'email_id',
        'J': 'current_stage',
        'K': 'first_meeting_date',
        'L': 'follow_up_date',
        'M': 'follow_up_reason',
        'N': 'panch_meeting_date',
        'O': 'location_address',
        'P': 'location_gps',
        'Q': 'electricity_status',
        'R': 'internet_status',
        'S': 'shed_available',
        'T': 'email_sent_date',
        'U': 'noc_received_date',
        'V': 'noc_file_url',
        'W': 'sa_sent_date',
        'X': 'sa_signed_date',
        'Y': 'sa_file_url',
        'Z': 'device_deployed_date',
        'AA': 'device_installed_date',
        'AB': 'device_serial',
        'AC': 'meeting_notes',
        'AD': 'updated_at',
    }

    def __init__(self):
        """Initialize Google Sheets client"""
        creds = get_google_credentials()
        self.gc = gspread.authorize(creds)
        self.spreadsheet_id = settings.google_sheets_id

    def get_worksheet(self, sheet_name: str = "VP Tracker"):
        """Get or create a worksheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=sheet_name, rows=500, cols=30
                )
                # Set up headers
                headers = list(self.COLUMNS.values())
                worksheet.update('A1', [headers])
            return worksheet
        except Exception as e:
            raise RuntimeError(f"Failed to access Google Sheet: {e}")

    def find_vp_row(self, worksheet, vp_name: str, block_name: str) -> Optional[int]:
        """Find the row number for a village panchayat"""
        try:
            # Get all values in column C (VP names) and B (Block names)
            vp_names = worksheet.col_values(3)  # Column C
            block_names = worksheet.col_values(2)  # Column B

            for idx, (vp, block) in enumerate(zip(vp_names, block_names), start=1):
                if vp.lower() == vp_name.lower() and block.lower() == block_name.lower():
                    return idx
            return None
        except Exception:
            return None

    def vp_to_row(self, vp: VillagePanchayat, sl_no: int) -> List[Any]:
        """Convert VillagePanchayat object to sheet row"""
        from ..config.settings import GOA_BLOCKS

        # Get block name
        block = next((b for b in GOA_BLOCKS if b['id'] == vp.block_id), None)
        block_name = block['name'] if block else ""

        # Format GPS
        gps = ""
        if vp.location_gps_lat and vp.location_gps_lng:
            gps = f"{vp.location_gps_lat}, {vp.location_gps_lng}"

        return [
            sl_no,
            block_name,
            vp.name,
            vp.code or "",
            vp.secretary_name or "",
            vp.secretary_phone or "",
            vp.sarpanch_name or "",
            vp.sarpanch_phone or "",
            vp.email_id or "",
            STAGE_LABELS.get(vp.current_stage, vp.current_stage.value),
            str(vp.first_meeting_date) if vp.first_meeting_date else "",
            str(vp.follow_up_date) if vp.follow_up_date else "",
            vp.follow_up_reason or "",
            str(vp.panch_meeting_date) if vp.panch_meeting_date else "",
            vp.location_address or "",
            gps,
            vp.electricity_status.value,
            vp.internet_status.value,
            "Yes" if vp.shed_available else "No",
            str(vp.email_sent_date) if vp.email_sent_date else "",
            str(vp.noc_received_date) if vp.noc_received_date else "",
            vp.noc_file_url or "",
            str(vp.service_agreement_sent_date) if vp.service_agreement_sent_date else "",
            str(vp.service_agreement_signed_date) if vp.service_agreement_signed_date else "",
            vp.service_agreement_url or "",
            str(vp.device_deployed_date) if vp.device_deployed_date else "",
            str(vp.device_installed_date) if vp.device_installed_date else "",
            vp.device_serial_number or "",
            " | ".join(vp.meeting_notes) if vp.meeting_notes else "",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ]

    def update_vp(self, vp: VillagePanchayat, block_name: str):
        """Update or insert a village panchayat record in the sheet"""
        worksheet = self.get_worksheet()

        # Find existing row
        row_num = self.find_vp_row(worksheet, vp.name, block_name)

        if row_num:
            # Update existing row
            row_data = self.vp_to_row(vp, row_num - 1)  # -1 for header
            worksheet.update(f'A{row_num}', [row_data])
        else:
            # Append new row
            all_values = worksheet.get_all_values()
            next_row = len(all_values) + 1
            sl_no = len(all_values)  # -1 for header, but starting from 1
            row_data = self.vp_to_row(vp, sl_no)
            worksheet.update(f'A{next_row}', [row_data])

    def apply_meeting_update(self, update: MeetingUpdate, block_name: str):
        """Apply a meeting update to the sheet"""
        worksheet = self.get_worksheet()

        if not update.village_panchayat_name:
            raise ValueError("Village Panchayat name is required")

        row_num = self.find_vp_row(worksheet, update.village_panchayat_name, block_name)

        if not row_num:
            raise ValueError(f"VP '{update.village_panchayat_name}' not found in block '{block_name}'")

        # Build updates
        updates = []

        if update.secretary_name:
            updates.append(('E', update.secretary_name))
        if update.secretary_phone:
            updates.append(('F', update.secretary_phone))
        if update.sarpanch_name:
            updates.append(('G', update.sarpanch_name))
        if update.sarpanch_phone:
            updates.append(('H', update.sarpanch_phone))
        if update.email_id:
            updates.append(('I', update.email_id))
        if update.suggested_stage:
            updates.append(('J', STAGE_LABELS.get(update.suggested_stage, update.suggested_stage.value)))
        if update.follow_up_date:
            updates.append(('L', str(update.follow_up_date)))
        if update.follow_up_reason:
            updates.append(('M', update.follow_up_reason))
        if update.location_description:
            updates.append(('O', update.location_description))

        # Always update timestamp
        updates.append(('AD', datetime.now().strftime("%Y-%m-%d %H:%M")))

        # Apply updates
        for col, value in updates:
            worksheet.update(f'{col}{row_num}', [[value]])

        # Append to meeting notes
        current_notes = worksheet.acell(f'AC{row_num}').value or ""
        note_entry = f"[{datetime.now().strftime('%Y-%m-%d')}] {update.raw_input[:200]}"
        new_notes = f"{current_notes} | {note_entry}" if current_notes else note_entry
        worksheet.update(f'AC{row_num}', [[new_notes]])

    def get_summary_by_block(self) -> List[Dict]:
        """Get summary statistics by block"""
        worksheet = self.get_worksheet()
        all_data = worksheet.get_all_records()

        from collections import defaultdict
        block_stats = defaultdict(lambda: {
            'total': 0,
            'stages': defaultdict(int),
        })

        for row in all_data:
            block = row.get('block_name', 'Unknown')
            stage = row.get('current_stage', 'Yet to Meet')

            block_stats[block]['total'] += 1
            block_stats[block]['stages'][stage] += 1

        return dict(block_stats)

    def get_tracker_data(self) -> List[Dict]:
        """Get all VP data from the DRS-Tracker sheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("DRS-Tracker")
            all_data = worksheet.get_all_records()

            vps = []
            for row in all_data:
                if not row.get('Block'):
                    continue

                # Parse RVM locations from JSON string
                rvm_locations = []
                rvm_loc_str = row.get('RVM_Locations', '')
                if rvm_loc_str:
                    try:
                        rvm_locations = json.loads(rvm_loc_str)
                    except:
                        pass

                vps.append({
                    'id': len(vps) + 1,
                    'block': row.get('Block', ''),
                    'vpCode': row.get('VP_Code', ''),
                    'vpName': row.get('VP_Name', ''),
                    'bdoName': row.get('BDO_Name', ''),
                    'bdoPhone': row.get('BDO_Phone', ''),
                    'secretaryName': row.get('Secretary_Name', ''),
                    'secretaryPhone': row.get('Secretary_Phone', ''),
                    'sarpanchName': row.get('Sarpanch_Name', ''),
                    'sarpanchPhone': row.get('Sarpanch_Phone', ''),
                    'email': row.get('VP_Email', ''),
                    'vpContact': row.get('VP_Contact', ''),
                    'website': row.get('Website', ''),
                    'address': row.get('Address', ''),
                    'currentStage': row.get('Current_Stage', 'yet_to_meet'),
                    'stageNumber': _safe_int(row.get('Stage_Number'), 1),
                    'stageDate': row.get('Stage_Date', ''),
                    'meetingNotes': row.get('Meeting_Notes', ''),
                    'followUpDate': row.get('Follow_Up_Date', ''),
                    # Profile fields
                    'contractorName': row.get('Contractor_Name', ''),
                    'contractorPhone': row.get('Contractor_Phone', ''),
                    'plannedRvms': _safe_int(row.get('Planned_RVMs'), 1),
                    'agreedRvms': _safe_int(row.get('Agreed_RVMs'), 0),
                    'rvmLocations': rvm_locations,
                    # Cost & Operations fields
                    'electricityBearer': row.get('Electricity_Cost_Bearer', ''),
                    'internetBearer': row.get('Internet_Cost_Bearer', ''),
                    'handlerHiredBy': row.get('Handler_Hired_By', ''),
                    'spaceType': row.get('Space_Type', ''),
                    # NOC Tracking fields (AN-AP)
                    'nocEmailSentDate': row.get('NOC_Email_Sent_Date', ''),
                    'emailRead': row.get('Email_Read', ''),
                    'signedNocDate': row.get('Signed_NOC_Date', ''),
                    # RVM Deployment sub-stage fields (AQ-AX)
                    'shedType':         row.get('Shed_Type', ''),
                    'shedInstalled':    row.get('Shed_Installed', ''),
                    'electricityReady': row.get('Electricity_Ready', ''),
                    'internetReady':    row.get('Internet_Ready', ''),
                    'cctvInstalled':    row.get('CCTV_Installed', ''),
                    'machineLive':      row.get('Machine_Live', ''),
                    'installDate':      row.get('Install_Date', ''),
                    'deploymentBlocker':row.get('Deployment_Blocker', ''),
                    'lastUpdated': row.get('Last_Updated', ''),
                })
            return vps
        except Exception as e:
            raise RuntimeError(f"Failed to get tracker data: {e}")

    def find_vp_row(self, vp_code: str) -> Optional[int]:
        """Find the row number for a VP by VP code in DRS-Tracker sheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("DRS-Tracker")

            # Get all values in column B (VP_Code)
            vp_codes = worksheet.col_values(2)  # Column B

            for idx, code in enumerate(vp_codes, start=1):
                if code == vp_code:
                    return idx
            return None
        except Exception:
            return None

    def update_vp_row(self, row_num: int, updates: Dict[str, str]):
        """Update specific columns in a VP row"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("DRS-Tracker")

            for col_letter, value in updates.items():
                cell = f"{col_letter}{row_num}"
                worksheet.update(cell, [[value]])
        except Exception as e:
            raise RuntimeError(f"Failed to update row: {e}")

    def get_vp_cell_value(self, row_num: int, col_letter: str) -> str:
        """Get a specific cell value from a VP row"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("DRS-Tracker")
            cell = f"{col_letter}{row_num}"
            return worksheet.acell(cell).value or ""
        except Exception:
            return ""

    # ==================== RVM Deployment Methods ====================

    def get_planned_rvms_total(self) -> int:
        """Sum Planned_RVMs from DRS-Tracker sheet."""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("DRS-Tracker")
            all_data = worksheet.get_all_records()
            total = 0
            for row in all_data:
                if not row.get('Block'):
                    continue
                total += _safe_int(row.get('Planned_RVMs'), 0)
            return total if total > 0 else 301
        except Exception:
            return 301

    def get_deployment_data(self) -> List[Dict]:
        """Fetch all rows from the 'RVM Deployment' sheet tab."""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet("RVM Deployment")
            except Exception:
                return []
            # Use get_all_values() instead of get_all_records() to tolerate
            # duplicate or blank column headers that break get_all_records()
            all_values = worksheet.get_all_values()
            if not all_values:
                return []
            headers = [str(h).strip() for h in all_values[0]]
            records = []
            for row_vals in all_values[1:]:
                row = {}
                for i, header in enumerate(headers):
                    row[header] = row_vals[i].strip() if i < len(row_vals) else ''
                records.append(row)
            locations = []
            for row in records:
                row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                _sn = {'done':'Done','yes':'Yes','no':'No','pending':'Pending',
                       'not required':'Not Required','not req':'Not Required','n/a':'Not Required','na':'Not Required'}
                row = {k: _sn.get(str(v).strip().lower(), str(v).strip()) if isinstance(v, str) else v for k, v in row.items()}
                loc_name = str(row.get('Location Name', '') or row.get('Location_Name', '')).strip()
                if not loc_name:
                    continue
                current_stage = self._compute_deployment_stage(row)
                locations.append({
                    'locationName':    loc_name,
                    'block':           str(row.get('Block', '')).strip(),
                    'entityName':      str(row.get('Entity Name', '') or row.get('Entity_Name', '')).strip(),
                    'entityType':      str(row.get('Entity Type', '') or row.get('Entity_Type', '')).strip(),
                    'difficulty':      str(row.get('Difficulty', '')).strip(),
                    'collectionPoint': str(row.get('Collection Point', '') or row.get('Collection_Point', '')).strip(),
                    'nocReceived':     str(row.get('NOC Received', '') or row.get('NOC_Received', '')).strip(),
                    'agreementSigned': str(row.get('Service Agreement Signed', '') or row.get('Service_Agreement_Signed', '')).strip(),
                    'siteClearanceReq':    str(row.get('Site Clearance Requirement', '')).strip(),
                    'siteClearanceStatus': str(row.get('Site Clearance Status', '')).strip(),
                    'civilWorkReq':    str(row.get('Civil Work Requirement', '')).strip(),
                    'civilWorkStatus': str(row.get('Civil Work Status', '')).strip(),
                    'electricalStatus': str(row.get('Electrical Connection for Installation', '')).strip(),
                    'shedRequired': str(row.get('Shed Required', '')).strip(),
                    'shedType':     str(row.get('Shed Type', '')).strip(),
                    'shedStatus':   str(row.get('Shed Status', '')).strip(),
                    'internetRequired': str(row.get('Internet Required', '')).strip(),
                    'internetStatus':   str(row.get('Internet Status', '')).strip(),
                    'cctvStatus': str(row.get('CCTV Installation Status', '')).strip(),
                    'rvmDelivery': str(row.get('RVM Delivery', '')).strip(),
                    'rvmDeployed': str(row.get('RVM Deployed with Base Fixing', '')).strip(),
                    'finalCheck':  str(row.get('Final Check', '')).strip(),
                    'machineLive': str(row.get('RVM Working Condition Check', '')).strip(),
                    'installDate': str(row.get('Machine Install Date', '')).strip(),
                    'lat': str(row.get('Latitude', '') or row.get('Lat', '')).strip(),
                    'lng': str(row.get('Longitude', '') or row.get('Lng', '')).strip(),
                    'currentStage': current_stage,
                })
            return locations
        except Exception as e:
            raise RuntimeError(f"Failed to fetch RVM Deployment data: {e}")

    def get_cp_tab_data(self) -> list:
        """Fetch CP planning data from the 'CP' sheet tab.
        Expected columns: Block, Panchayat, Plan Count
        Returns empty list if tab does not exist yet.
        """
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet("CP")
            except Exception:
                return []
            records = worksheet.get_all_records()
            result = []
            for row in records:
                row = {k.strip(): (str(v).strip() if isinstance(v, str) else v) for k, v in row.items()}
                panchayat = str(row.get('Panchayat', '') or row.get('panchayat', '')).strip()
                if not panchayat:
                    continue
                try:
                    plan_count = int(row.get('Plan Count', 0) or row.get('Plan_Count', 0) or 0)
                except (ValueError, TypeError):
                    plan_count = 0
                result.append({
                    'block':     str(row.get('Block', '') or row.get('block', '')).strip(),
                    'panchayat': panchayat,
                    'planCount': plan_count,
                })
            return result
        except Exception as e:
            return []

    # ==================== Analytics / Activity Log Methods ====================

    def log_analytics_event(self, event: dict) -> None:
        """Append an analytics event to Analytics-Log sheet. Never raises."""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            try:
                ws = spreadsheet.worksheet("Analytics-Log")
            except Exception:
                ws = spreadsheet.add_worksheet("Analytics-Log", rows=50000, cols=12)
                ws.append_row(['Timestamp', 'User_Email', 'User_Name', 'Event_Type',
                               'Page', 'Element', 'Value', 'Session_ID',
                               'Device_Type', 'Browser', 'OS', 'IP_Address'])
            ws.append_row([
                event.get('timestamp', ''),
                event.get('user_email', ''),
                event.get('user_name', ''),
                event.get('event_type', ''),
                event.get('page', ''),
                event.get('element', ''),
                str(event.get('value', '')),
                event.get('session_id', ''),
                event.get('device_type', ''),
                event.get('browser', ''),
                event.get('os', ''),
                event.get('ip', ''),
            ])
        except Exception:
            pass

    def get_analytics_log(self, limit: int = 300) -> list:
        """Fetch recent analytics events, newest first."""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            ws = spreadsheet.worksheet("Analytics-Log")
            records = ws.get_all_records()
            return list(reversed(records[-limit:])) if records else []
        except Exception:
            return []

    def get_analytics_profiles(self) -> list:
        """Aggregate all analytics events into per-user profiles."""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            ws = spreadsheet.worksheet("Analytics-Log")
            records = ws.get_all_records()
        except Exception:
            return []

        from collections import defaultdict

        users: dict = {}
        for r in records:
            email = (r.get('User_Email') or '').strip()
            if not email:
                continue
            if email not in users:
                users[email] = {
                    'name': '', 'email': email,
                    'logins': 0, 'last_seen': '',
                    'mobile_count': 0, 'total_logins': 0,
                    'pages': defaultdict(lambda: {'visits': 0, 'scroll_total': 0.0, 'scroll_count': 0}),
                    'clicks': defaultdict(int),
                    'hours': [0] * 24,
                }
            u = users[email]
            name = (r.get('User_Name') or '').strip()
            if name:
                u['name'] = name
            ts = (r.get('Timestamp') or '').strip()
            if ts > u['last_seen']:
                u['last_seen'] = ts
            try:
                u['hours'][int(ts[11:13])] += 1
            except Exception:
                pass
            ev = (r.get('Event_Type') or '').strip()
            page = (r.get('Page') or '').strip()
            element = (r.get('Element') or '').strip()
            if ev == 'login':
                u['logins'] += 1
                u['total_logins'] += 1
                if (r.get('Device_Type') or '').strip() == 'Mobile':
                    u['mobile_count'] += 1
            elif ev == 'page_view' and page:
                u['pages'][page]['visits'] += 1
            elif ev == 'scroll' and page:
                try:
                    val = float(r.get('Value') or 0)
                    u['pages'][page]['scroll_total'] += val
                    u['pages'][page]['scroll_count'] += 1
                except Exception:
                    pass
            elif ev == 'click' and element:
                u['clicks'][element] += 1

        result = []
        for email, u in users.items():
            pages_list = []
            for pname, pd in u['pages'].items():
                avg_scroll = round(pd['scroll_total'] / pd['scroll_count']) if pd['scroll_count'] > 0 else 0
                pages_list.append({'name': pname, 'visits': pd['visits'], 'avg_scroll': avg_scroll})
            pages_list.sort(key=lambda x: x['visits'], reverse=True)
            clicks_list = [{'element': el, 'count': cnt} for el, cnt in u['clicks'].items()]
            clicks_list.sort(key=lambda x: x['count'], reverse=True)
            mobile_pct = round(u['mobile_count'] / u['total_logins'] * 100) if u['total_logins'] > 0 else 0
            result.append({
                'name': u['name'] or email.split('@')[0],
                'email': email,
                'logins': u['logins'],
                'last_seen': u['last_seen'],
                'mobile_pct': mobile_pct,
                'pages': pages_list[:6],
                'top_clicks': clicks_list[:5],
                'hours': u['hours'],
            })
        result.sort(key=lambda x: x['logins'], reverse=True)
        return result

    @staticmethod
    def _compute_deployment_stage(row) -> str:
        """Auto-compute current stage as the first incomplete deployment step."""
        def v(key, alt=''):
            return str(row.get(key, '') or (row.get(alt, '') if alt else '')).strip()

        if v('NOC Received', 'NOC_Received') != 'Yes':
            return 'NOC Pending'
        if v('Service Agreement Signed', 'Service_Agreement_Signed') != 'Yes':
            return 'Agreement Pending'
        shed = v('Shed Status', 'Shed_Status')
        if shed and shed not in ('Done', 'Not Required'):
            return 'Shed Pending'
        elec = v('Electrical Connection for Installation')
        if elec and elec not in ('Done', 'Not Required'):
            return 'Electrical Pending'
        inet = v('Internet Status', 'Internet_Status')
        if inet and inet not in ('Done', 'Not Required'):
            return 'Internet Pending'
        cctv = v('CCTV Installation Status')
        if cctv and cctv not in ('Done', 'Not Required'):
            return 'CCTV Pending'
        if v('RVM Delivery') != 'Done':
            return 'Machine Delivery Pending'
        if v('RVM Deployed with Base Fixing') != 'Done':
            return 'Machine Installation Pending'
        if v('RVM Working Condition Check') != 'Done':
            return 'Machine Live Pending'
        return 'Completed'

    # ==================== BDO Tracker Methods ====================

    def get_bdo_tracker_data(self) -> List[Dict]:
        """Get all BDO data from the BDO-Tracker sheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("BDO-Tracker")
            records = worksheet.get_all_records()

            return [{
                'block': row.get('Block', ''),
                'bdoName': row.get('BDO_Name', ''),
                'bdoPhone': row.get('BDO_Phone', ''),
                'currentStage': row.get('Current_Stage', 'yet_to_meet'),
            } for row in records]
        except gspread.WorksheetNotFound:
            return []
        except Exception as e:
            raise RuntimeError(f"Failed to get BDO tracker data: {e}")

    def update_bdo_stage(self, block: str, stage: str) -> bool:
        """Update BDO stage for a block"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("BDO-Tracker")

            # Find the block in column A
            cell = worksheet.find(block, in_column=1)
            if cell:
                worksheet.update(f'D{cell.row}', [[stage]])  # Update column D (Current_Stage)
                return True
            return False
        except Exception as e:
            raise RuntimeError(f"Failed to update BDO stage: {e}")

    def init_bdo_tracker(self) -> Dict:
        """Initialize BDO-Tracker sheet from DRS-Tracker data"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)

            # Get unique blocks from DRS-Tracker
            drs_sheet = spreadsheet.worksheet("DRS-Tracker")
            all_data = drs_sheet.get_all_records()

            blocks = {}
            for row in all_data:
                block = row.get('Block', '')
                if block and block not in blocks:
                    blocks[block] = {
                        'bdo_name': row.get('BDO_Name', ''),
                        'bdo_phone': row.get('BDO_Phone', ''),
                    }

            # Create or get BDO-Tracker sheet
            try:
                bdo_sheet = spreadsheet.worksheet("BDO-Tracker")
            except gspread.WorksheetNotFound:
                bdo_sheet = spreadsheet.add_worksheet(title="BDO-Tracker", rows=20, cols=5)

            # Write headers and data
            headers = [['Block', 'BDO_Name', 'BDO_Phone', 'Current_Stage']]
            rows = [[block, info['bdo_name'], info['bdo_phone'], 'yet_to_meet']
                    for block, info in sorted(blocks.items())]

            bdo_sheet.clear()
            bdo_sheet.update('A1', headers + rows)

            return {'success': True, 'blocks_created': len(blocks)}
        except Exception as e:
            raise RuntimeError(f"Failed to initialize BDO tracker: {e}")

    # ==================== Meeting Assignments Methods ====================

    def get_meeting_assignments_data(self) -> List[Dict]:
        """Get all meeting assignments from the Meeting-Assignments sheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("Meeting-Assignments")
            records = worksheet.get_all_records()

            return [{
                'meetingId': row.get('Meeting_ID', ''),
                'vpCode': row.get('VP_Code', ''),
                'vpName': row.get('VP_Name', ''),
                'block': row.get('Block', ''),
                'eventType': row.get('Event_Type', ''),  # calendar_event, task_reminder, milestone
                'eventDate': row.get('Event_Date', ''),
                'eventTime': row.get('Event_Time', ''),
                'assignedTo': row.get('Assigned_To', ''),
                'calendarEventId': row.get('Calendar_Event_ID', ''),
                'status': row.get('Status', 'scheduled'),  # scheduled, completed, cancelled
                'notes': row.get('Notes', ''),
                'createdAt': row.get('Created_At', ''),
                'eventTitle': row.get('Event_Title', ''),  # First Meeting, Panch Meeting, Follow-up, etc.
            } for row in records]
        except gspread.WorksheetNotFound:
            return []
        except Exception as e:
            raise RuntimeError(f"Failed to get meeting assignments: {e}")

    def create_meeting_assignment(self, meeting_data: Dict) -> Dict:
        """Create a new meeting assignment"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)

            # Create or get Meeting-Assignments sheet
            try:
                worksheet = spreadsheet.worksheet("Meeting-Assignments")
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title="Meeting-Assignments", rows=500, cols=15)
                # Write headers (includes Event_Title column)
                headers = [['Meeting_ID', 'VP_Code', 'VP_Name', 'Block', 'Event_Type',
                           'Event_Date', 'Event_Time', 'Assigned_To', 'Calendar_Event_ID',
                           'Status', 'Notes', 'Created_At', 'Event_Title']]
                worksheet.update('A1', headers)

            # Generate meeting ID
            import uuid
            meeting_id = f"MTG-{uuid.uuid4().hex[:8].upper()}"

            # Prepare row data (includes event_title)
            row_data = [
                meeting_id,
                meeting_data.get('vp_code', ''),
                meeting_data.get('vp_name', ''),
                meeting_data.get('block', ''),
                meeting_data.get('event_type', 'calendar_event'),
                meeting_data.get('event_date', ''),
                meeting_data.get('event_time', '10:00'),
                meeting_data.get('assigned_to', ''),
                meeting_data.get('calendar_event_id', ''),
                meeting_data.get('status', 'scheduled'),
                meeting_data.get('notes', ''),
                datetime.now().isoformat(),
                meeting_data.get('event_title', ''),  # New: Event Title
            ]

            # Append row
            worksheet.append_row(row_data, value_input_option='USER_ENTERED')

            return {'success': True, 'meeting_id': meeting_id}
        except Exception as e:
            raise RuntimeError(f"Failed to create meeting assignment: {e}")

    def update_meeting_assignment(self, meeting_id: str, updates: Dict) -> bool:
        """Update an existing meeting assignment"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("Meeting-Assignments")

            # Find the meeting by ID in column A
            cell = worksheet.find(meeting_id, in_column=1)
            if not cell:
                return False

            row_num = cell.row

            # Column mapping for updates
            # A=Meeting_ID, B=VP_Code, C=VP_Name, D=Block, E=Event_Type
            # F=Event_Date, G=Event_Time, H=Assigned_To, I=Calendar_Event_ID
            # J=Status, K=Notes, L=Created_At, M=Event_Title
            col_map = {
                'event_date': 'F',
                'event_time': 'G',
                'assigned_to': 'H',
                'calendar_event_id': 'I',
                'status': 'J',
                'notes': 'K',
                'event_title': 'M',
            }

            # Apply updates
            for field, value in updates.items():
                if field in col_map:
                    worksheet.update(f'{col_map[field]}{row_num}', [[value]])

            return True
        except gspread.WorksheetNotFound:
            return False
        except Exception as e:
            raise RuntimeError(f"Failed to update meeting assignment: {e}")

    def delete_meeting_assignment(self, meeting_id: str) -> bool:
        """Delete a meeting assignment (mark as cancelled)"""
        try:
            return self.update_meeting_assignment(meeting_id, {'status': 'cancelled'})
        except Exception:
            return False

    def init_meeting_assignments(self) -> Dict:
        """Initialize Meeting-Assignments sheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)

            # Create or get Meeting-Assignments sheet
            try:
                worksheet = spreadsheet.worksheet("Meeting-Assignments")
                return {'success': True, 'message': 'Sheet already exists'}
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title="Meeting-Assignments", rows=500, cols=15)
                # Write headers (includes Event_Title column M)
                headers = [['Meeting_ID', 'VP_Code', 'VP_Name', 'Block', 'Event_Type',
                           'Event_Date', 'Event_Time', 'Assigned_To', 'Calendar_Event_ID',
                           'Status', 'Notes', 'Created_At', 'Event_Title']]
                worksheet.update('A1', headers)
                return {'success': True, 'message': 'Sheet created successfully'}
        except Exception as e:
            raise RuntimeError(f"Failed to initialize meeting assignments: {e}")

    def sync_stage_numbers(self) -> Dict:
        """Sync Stage_Number column (O) with Current_Stage column (N) for all VPs.
        Handles enum values, label text, and legacy values."""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("DRS-Tracker")

            # Build comprehensive stage-to-number map
            stage_map = {}
            for i, stage in enumerate(DeploymentStage):
                num = i + 1
                stage_map[stage.value] = num                          # email_sent → 7
                label = STAGE_LABELS.get(stage, '')
                if label:
                    stage_map[label] = num                            # Email Sent → 7
                    stage_map[label.lower()] = num                    # email sent → 7

            # Legacy mappings
            stage_map['meeting_scheduled'] = 2
            stage_map['Meeting Scheduled'] = 2
            stage_map['follow_up_required'] = 3
            stage_map['Follow Up Required'] = 3
            stage_map['punch_meeting_required'] = 4

            # Read all rows (columns N and O: Current_Stage and Stage_Number)
            all_values = worksheet.get_all_values()
            if len(all_values) <= 1:
                return {'success': True, 'message': 'No data rows', 'fixed': 0}

            fixed = 0
            skipped = []
            import time

            for row_idx in range(1, len(all_values)):  # Skip header
                row = all_values[row_idx]
                if len(row) < 15:
                    continue

                current_stage = row[13]  # Column N (0-indexed)
                current_number = row[14]  # Column O (0-indexed)

                if not current_stage:
                    continue

                # Resolve correct number
                correct_number = stage_map.get(current_stage) or stage_map.get(current_stage.lower())
                if not correct_number:
                    skipped.append(f"Row {row_idx + 1}: unrecognized stage '{current_stage}'")
                    continue

                # Check if update needed
                try:
                    existing_num = int(current_number) if current_number else 0
                except (ValueError, TypeError):
                    existing_num = 0

                if existing_num != correct_number:
                    sheet_row = row_idx + 1  # 1-indexed for sheets
                    worksheet.update(f'O{sheet_row}', [[str(correct_number)]])
                    fixed += 1

                    # Rate limit: pause every 10 updates
                    if fixed % 10 == 0:
                        time.sleep(2)

            return {
                'success': True,
                'message': f'Fixed {fixed} stage numbers',
                'fixed': fixed,
                'total_rows': len(all_values) - 1,
                'skipped': skipped[:20]
            }
        except Exception as e:
            raise RuntimeError(f"Failed to sync stage numbers: {e}")

    def add_noc_tracking_headers(self) -> Dict:
        """Add NOC tracking headers (AN, AO, AP) to DRS-Tracker sheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("DRS-Tracker")

            # Expand sheet if needed (AN=40, AO=41, AP=42)
            if worksheet.col_count < 42:
                worksheet.resize(cols=42)

            header_row = worksheet.row_values(1)
            added = []

            # AN = NOC_Email_Sent_Date (column 40)
            if 'NOC_Email_Sent_Date' not in header_row:
                worksheet.update('AN1', [['NOC_Email_Sent_Date']])
                added.append('AN: NOC_Email_Sent_Date')

            # AO = Email_Read (column 41)
            if 'Email_Read' not in header_row:
                worksheet.update('AO1', [['Email_Read']])
                added.append('AO: Email_Read')

            # AP = Signed_NOC_Date (column 42)
            if 'Signed_NOC_Date' not in header_row:
                worksheet.update('AP1', [['Signed_NOC_Date']])
                added.append('AP: Signed_NOC_Date')

            if not added:
                return {'success': True, 'message': 'All NOC tracking headers already exist', 'added': []}

            return {'success': True, 'message': f'Added {len(added)} headers', 'added': added}
        except Exception as e:
            raise RuntimeError(f"Failed to add NOC tracking headers: {e}")

    def add_event_title_header(self) -> Dict:
        """Add Event_Title header to column M of Meeting-Assignments sheet"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("Meeting-Assignments")

            # Check if Event_Title header already exists
            header_row = worksheet.row_values(1)
            if 'Event_Title' in header_row:
                return {'success': True, 'message': 'Event_Title header already exists', 'added': False}

            # Add Event_Title header to column M
            worksheet.update('M1', [['Event_Title']])
            return {'success': True, 'message': 'Event_Title header added to column M', 'added': True}
        except gspread.WorksheetNotFound:
            return {'success': False, 'message': 'Meeting-Assignments sheet not found'}
        except Exception as e:
            raise RuntimeError(f"Failed to add Event_Title header: {e}")

    # ==================== Training Progress ====================

    TRAINING_PROGRESS_HEADERS = [
        'Email', 'Name', 'Total_XP', 'Total_Stars', 'Modules_Completed',
        'Chapters_Completed', 'Total_Time_Seconds', 'Current_Module',
        'Last_Active', 'Progress_JSON', 'Created_At'
    ]

    def init_training_progress(self) -> Dict:
        """Initialize Training-Progress sheet with headers (one-time setup)"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)

            try:
                worksheet = spreadsheet.worksheet("Training-Progress")
                return {'success': True, 'message': 'Training-Progress sheet already exists', 'created': False}
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title="Training-Progress", rows=200, cols=11)

            worksheet.update('A1', [self.TRAINING_PROGRESS_HEADERS])
            return {'success': True, 'message': 'Training-Progress sheet created', 'created': True}
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Training-Progress: {e}")

    def sync_training_progress(self, email: str, name: str, data: Dict) -> Dict:
        """Upsert training progress for a user by email"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)

            try:
                worksheet = spreadsheet.worksheet("Training-Progress")
            except gspread.WorksheetNotFound:
                # Auto-create if not exists
                worksheet = spreadsheet.add_worksheet(title="Training-Progress", rows=200, cols=11)
                worksheet.update('A1', [self.TRAINING_PROGRESS_HEADERS])

            now = datetime.now().isoformat()

            # Find existing row by email (column A)
            cell = worksheet.find(email, in_column=1)
            if cell:
                row_num = cell.row
                # Update columns C through J (skip Email and Name)
                worksheet.update(f'C{row_num}:J{row_num}', [[
                    data.get('total_xp', 0),
                    data.get('total_stars', 0),
                    data.get('modules_completed', 0),
                    data.get('chapters_completed', 0),
                    data.get('total_time_seconds', 0),
                    data.get('current_module', 0),
                    now,
                    data.get('progress_json', '{}'),
                ]])
                # Also update name in case it changed
                worksheet.update(f'B{row_num}', [[name]])
                return {'success': True, 'action': 'updated', 'row': row_num}
            else:
                # New user — append row
                row_data = [
                    email, name,
                    data.get('total_xp', 0),
                    data.get('total_stars', 0),
                    data.get('modules_completed', 0),
                    data.get('chapters_completed', 0),
                    data.get('total_time_seconds', 0),
                    data.get('current_module', 0),
                    now,
                    data.get('progress_json', '{}'),
                    now,  # Created_At
                ]
                worksheet.append_row(row_data, value_input_option='USER_ENTERED')
                return {'success': True, 'action': 'created'}

        except Exception as e:
            raise RuntimeError(f"Failed to sync training progress: {e}")

    def get_training_progress(self, email: str) -> Dict:
        """Get training progress JSON for a user by email"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet("Training-Progress")
            except gspread.WorksheetNotFound:
                return {'found': False, 'progress_json': '{}'}

            cell = worksheet.find(email, in_column=1)
            if cell:
                # Progress_JSON is column J (10th column)
                progress_json = worksheet.cell(cell.row, 10).value
                return {'found': True, 'progress_json': progress_json or '{}'}
            return {'found': False, 'progress_json': '{}'}
        except Exception as e:
            raise RuntimeError(f"Failed to get training progress: {e}")

    def get_training_leaderboard(self) -> Dict:
        """Get training leaderboard with ALL authorized users, sorted by XP descending"""
        try:
            # Get all authorized users
            auth_service = AuthService()
            all_users = auth_service.get_authorized_users()

            # Get training progress data (may be empty)
            progress_by_email = {}
            try:
                spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
                worksheet = spreadsheet.worksheet("Training-Progress")
                records = worksheet.get_all_records()
                for row in records:
                    email = str(row.get('Email', '')).strip().lower()
                    if email:
                        progress_by_email[email] = row
            except gspread.WorksheetNotFound:
                pass  # No progress yet — all users will show 0

            # Merge: all authorized users with their progress (or 0s)
            merged = []
            for user in all_users:
                email = user.get('email', '')
                progress = progress_by_email.get(email, {})
                merged.append({
                    'email': email,
                    'name': user.get('name', '') or progress.get('Name', ''),
                    'xp': int(progress.get('Total_XP', 0) or 0),
                    'stars': int(progress.get('Total_Stars', 0) or 0),
                    'modules': int(progress.get('Modules_Completed', 0) or 0),
                    'chapters': int(progress.get('Chapters_Completed', 0) or 0),
                    'lastActive': progress.get('Last_Active', ''),
                })

            # Sort by XP descending, then by name for ties
            merged.sort(key=lambda r: (-r['xp'], r['name'].lower()))

            # Add ranks
            for i, entry in enumerate(merged):
                entry['rank'] = i + 1

            return {
                'leaderboard': merged,
                'totalTrainees': len(merged),
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get training leaderboard: {e}")

    # ==================== HoReCa CRM Methods ====================

    HORECA_CRM_SHEET_ID = '12YHTCeJxholgigzmGuf2GtTGsTREiS-EZj4Fod8B5x8'
    # After deleting 7 micro zone columns, CRM fields shifted from BI-BT to BB-BM
    HORECA_CRM_COL_MAP = {
        'outreach_status': 'BB', 'owner_name': 'BC', 'owner_number': 'BD',
        'spoc_name': 'BE', 'spoc_number': 'BF', 'spoc_designation': 'BG',
        'outreach_email': 'BH', 'bottles_per_week': 'BI',
        'outreach_notes': 'BJ', 'follow_up_date': 'BK',
        'last_updated': 'BL', 'updated_by': 'BM',
        'assigned_to': 'BN', 'assignment_history': 'BO',
    }
    HORECA_OUTREACH_STATUSES = [
        'De-listed', 'Call not answered', 'Call answered',
        'Pre-meeting mail to be sent', 'Pre-meeting mail sent',
        'Meeting aligned', 'Meeting done',
        'Post-meeting mail to be sent', 'Post meeting mail sent',
        'OB Form Opened', 'OB Form Filled',
    ]

    def _get_horeca_crm_cache(self):
        """Get or initialize the HoReCa CRM cache"""
        global _horeca_crm_cache
        now = datetime.now()
        if (_horeca_crm_cache['data'] is not None
                and _horeca_crm_cache['expiry']
                and now < _horeca_crm_cache['expiry']):
            return _horeca_crm_cache['data'], _horeca_crm_cache['headers']

        # Fetch all data from the enriched sheet
        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        worksheet = spreadsheet.sheet1
        all_values = worksheet.get_all_values()

        if len(all_values) < 2:
            _horeca_crm_cache['data'] = []
            _horeca_crm_cache['headers'] = []
            _horeca_crm_cache['expiry'] = now + timedelta(minutes=2)
            return [], []

        headers = all_values[0]
        rows = all_values[1:]

        _horeca_crm_cache['data'] = rows
        _horeca_crm_cache['headers'] = headers
        _horeca_crm_cache['expiry'] = now + timedelta(minutes=2)
        return rows, headers

    def _horeca_row_to_dict(self, row, headers):
        """Convert a HoReCa row to a frontend-friendly dict"""
        def safe_get(idx):
            return row[idx] if idx < len(row) else ''

        # Build a header-index map for key columns
        h = {}
        for i, hdr in enumerate(headers):
            h[hdr] = i

        # Actual sheet headers (65 cols after micro zone deletion):
        # A=Place ID, B=Name, C=Types, D=Primary Type, E=Street, F=Locality
        # G=City, H=State, I=Pincode, J=Full Address, K=Latitude, L=Longitude
        # M=Google Maps URL, N=Phone, O=International Phone, P=Website
        # Q=Opening Hours, R=Currently Open, S=Price Level, T=Rating
        # U=Total Ratings, V=Serves Beer, W=Serves Wine
        # AI=HoReCa_Type, AJ=Alcohol_Signal, AK=Size_Tier, AL=Contactability
        # AM=Area_Zone, AN=Priority_Score, AO=Priority_Rank
        # AU=h3_res7, AV=Zone_ID, AW=Zone_Name, AX=Zone_HoReCa_Count
        # AY=Zone_Density, AZ=Zone_Quadrant, BA=Zone_Priority_Rank
        # BB-BM: CRM outreach fields
        return {
            'place_id': safe_get(h.get('Place ID', 0)),
            'name': safe_get(h.get('Name', 1)),
            'type': safe_get(h.get('HoReCa_Type', 34)) or safe_get(h.get('Primary Type', 3)),
            'address': safe_get(h.get('Full Address', 9)) or safe_get(h.get('Street', 4)),
            'city': safe_get(h.get('City', 6)),
            'phone': safe_get(h.get('Phone', 13)),
            'rating': safe_get(h.get('Rating', 19)),
            'reviews': safe_get(h.get('Total Ratings', 20)),
            'lat': safe_get(h.get('Latitude', 10)),
            'lng': safe_get(h.get('Longitude', 11)),
            'alcohol': safe_get(h.get('Alcohol_Signal', 35)),
            'size': safe_get(h.get('Size_Tier', 36)),
            'maps_url': safe_get(h.get('Google Maps URL', 12)),
            'priority_score': safe_get(h.get('Priority_Score', 39)),
            'priority_rank': safe_get(h.get('Priority_Rank', 40)),
            # Meso zone fields (5 km²) — indices updated after 7 micro col deletion
            'zone_id': safe_get(h.get('Zone_ID', 47)),
            'zone': safe_get(h.get('Zone_Name', 48)),
            'zone_count': safe_get(h.get('Zone_HoReCa_Count', 49)),
            'zone_density': safe_get(h.get('Zone_Density', 50)),
            'zone_quadrant': safe_get(h.get('Zone_Quadrant', 51)),
            'zone_priority': safe_get(h.get('Zone_Priority_Rank', 52)),
            # CRM fields (columns BB-BM, indices 53-64)
            'outreach_status': safe_get(h.get('Outreach_Status', 53)),
            'owner_name': safe_get(h.get('Owner_Name', 54)),
            'owner_number': safe_get(h.get('Owner_Number', 55)),
            'spoc_name': safe_get(h.get('SPOC_Name', 56)),
            'spoc_number': safe_get(h.get('SPOC_Number', 57)),
            'spoc_designation': safe_get(h.get('SPOC_Designation', 58)),
            'outreach_email': safe_get(h.get('Outreach_Email', 59)),
            'bottles_per_week': safe_get(h.get('Bottles_Per_Week', 60)),
            'outreach_notes': safe_get(h.get('Outreach_Notes', 61)),
            'follow_up_date': safe_get(h.get('Follow_Up_Date', 62)),
            'last_updated': safe_get(h.get('Last_Updated', 63)),
            'updated_by': safe_get(h.get('Updated_By', 64)),
            'assigned_to': safe_get(h.get('Assigned_To', 65)),
            'assignment_history': safe_get(h.get('Assignment_History', 66)),
        }

    def get_horeca_crm_data(self, search='', status='', htype='',
                            zone='', city='', assigned_to='', page=1, page_size=50):
        """Get filtered, paginated HoReCa CRM data"""
        try:
            rows, headers = self._get_horeca_crm_cache()
            if not rows:
                return {'records': [], 'total': 0, 'page': 1, 'total_pages': 0}

            # Build header index for filtering
            h = {}
            for i, hdr in enumerate(headers):
                h[hdr] = i

            # Collect all distinct types and zones from full dataset for filter dropdowns
            type_idx = h.get('HoReCa_Type', 34)
            type_fallback_idx = h.get('Primary Type', 3)
            zone_name_idx = h.get('Zone_Name', 48)

            all_types = set()
            all_zones = set()
            all_assignees = set()
            assigned_to_idx = h.get('Assigned_To', 65)
            for row in rows:
                def _sg(idx):
                    return row[idx] if idx < len(row) else ''
                t = _sg(type_idx) or _sg(type_fallback_idx)
                z = _sg(zone_name_idx)
                a = _sg(assigned_to_idx)
                if t:
                    all_types.add(t)
                if z:
                    all_zones.add(z)
                if a:
                    all_assignees.add(a)

            # Filter in Python
            filtered = []
            name_matches = []  # rows where search matches name
            addr_matches = []  # rows where search matches address only
            search_lower = search.lower() if search else ''

            for row in rows:
                def safe_get(idx):
                    return row[idx] if idx < len(row) else ''

                # Search filter (name first, then address)
                if search_lower:
                    name_val = safe_get(h.get('Name', 1)).lower()
                    addr_val = safe_get(h.get('Full Address', 9)).lower()
                    is_name_match = search_lower in name_val
                    is_addr_match = search_lower in addr_val
                    if not is_name_match and not is_addr_match:
                        continue

                # Status filter
                if status:
                    row_status = safe_get(h.get('Outreach_Status', 53))
                    if status == 'No Status':
                        if row_status:
                            continue
                    elif row_status != status:
                        continue

                # Type filter
                if htype:
                    row_type = safe_get(h.get('HoReCa_Type', 34)) or safe_get(h.get('Primary Type', 3))
                    if row_type != htype:
                        continue

                # Zone filter (meso zone only)
                if zone:
                    row_zone = safe_get(h.get('Zone_Name', 48))
                    if row_zone != zone:
                        continue

                # City filter
                if city:
                    row_city = safe_get(h.get('City', 6))
                    if row_city != city:
                        continue

                # Assigned-to filter (case-insensitive)
                if assigned_to:
                    row_assignee = safe_get(h.get('Assigned_To', 65)).strip()
                    if assigned_to == 'Unassigned':
                        if row_assignee:
                            continue
                    elif row_assignee.lower() != assigned_to.lower():
                        continue

                if search_lower:
                    if is_name_match:
                        name_matches.append(row)
                    else:
                        addr_matches.append(row)
                else:
                    filtered.append(row)

            # When searching, put name matches first, then address-only matches
            if search_lower:
                filtered = name_matches + addr_matches

            total = len(filtered)
            total_pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, total_pages)

            start = (page - 1) * page_size
            end = start + page_size
            page_rows = filtered[start:end]

            records = [self._horeca_row_to_dict(r, headers) for r in page_rows]

            return {
                'records': records,
                'total': total,
                'page': page,
                'total_pages': total_pages,
                'filter_options': {
                    'types': sorted(all_types),
                    'zones': sorted(all_zones),
                    'assignees': sorted(all_assignees),
                },
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get HoReCa CRM data: {e}")

    def find_horeca_row(self, place_id):
        """Find row number for a HoReCa record by place_id"""
        try:
            rows, headers = self._get_horeca_crm_cache()
            h = {}
            for i, hdr in enumerate(headers):
                h[hdr] = i
            pid_idx = h.get('Place ID', 0)

            for idx, row in enumerate(rows):
                if pid_idx < len(row) and row[pid_idx] == place_id:
                    return idx + 2  # +2: row 1 is header, data starts at row 2
            return None
        except Exception:
            return None

    def update_horeca_outreach(self, place_id, updates, author='Team'):
        """Update outreach fields for a HoReCa record"""
        try:
            row_num = self.find_horeca_row(place_id)
            if not row_num:
                raise ValueError(f"HoReCa record not found: {place_id}")

            spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
            worksheet = spreadsheet.sheet1

            # Handle notes: prepend with timestamp
            if 'note' in updates and updates['note']:
                note_text = updates.pop('note')
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                new_entry = f"[{timestamp}|{author}] {note_text}"

                # Get existing notes
                existing = worksheet.acell(f'BJ{row_num}').value or ''
                if existing:
                    combined = f"{new_entry}\n---\n{existing}"
                else:
                    combined = new_entry
                worksheet.update(f'BJ{row_num}', [[combined]])

            # Handle assignment: update assigned_to and append to assignment_history
            if 'assigned_to' in updates and updates['assigned_to']:
                assignee = updates.pop('assigned_to')
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                new_entry = f"[{timestamp}|{author}] → {assignee}"

                # Write current assignee
                worksheet.update(f'BN{row_num}', [[assignee]])

                # Append to assignment history
                existing_history = worksheet.acell(f'BO{row_num}').value or ''
                if existing_history:
                    combined_history = f"{new_entry}\n---\n{existing_history}"
                else:
                    combined_history = new_entry
                worksheet.update(f'BO{row_num}', [[combined_history]])

            # Map field names to column letters and update
            for field, value in updates.items():
                if field in self.HORECA_CRM_COL_MAP and value is not None:
                    col = self.HORECA_CRM_COL_MAP[field]
                    worksheet.update(f'{col}{row_num}', [[str(value)]])

            # Always update Last_Updated and Updated_By
            worksheet.update(f'BL{row_num}', [[datetime.now().isoformat()]])
            worksheet.update(f'BM{row_num}', [[author]])

            # Invalidate cache
            global _horeca_crm_cache
            _horeca_crm_cache['expiry'] = None

            return {'success': True}
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to update HoReCa outreach: {e}")

    def add_horeca_record(self, data: dict) -> dict:
        """Add a new HoReCa record (manual lead) to the CRM sheet"""
        try:
            import time
            spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
            worksheet = spreadsheet.sheet1
            headers = worksheet.row_values(1)

            # Build header-index map
            h = {}
            for i, hdr in enumerate(headers):
                h[hdr] = i

            # Generate a unique Place ID
            place_id = f"MANUAL_{int(time.time())}"

            # Create a row with the same number of columns as headers
            row = [''] * len(headers)

            # Base columns
            if 'Place ID' in h: row[h['Place ID']] = place_id
            if 'Name' in h: row[h['Name']] = data.get('name', '')
            if 'Primary Type' in h: row[h['Primary Type']] = data.get('type', '')
            if 'HoReCa_Type' in h: row[h['HoReCa_Type']] = data.get('type', '')
            if 'Full Address' in h: row[h['Full Address']] = data.get('address', '')
            if 'City' in h: row[h['City']] = data.get('city', '')
            if 'Pincode' in h: row[h['Pincode']] = data.get('pincode', '')
            if 'Rating' in h: row[h['Rating']] = data.get('rating', '')
            if 'Latitude' in h: row[h['Latitude']] = data.get('lat', '')
            if 'Longitude' in h: row[h['Longitude']] = data.get('lng', '')
            if 'Phone' in h: row[h['Phone']] = data.get('owner_phone', '')
            if 'Serves Beer' in h: row[h['Serves Beer']] = 'TRUE' if data.get('serves_beer') else ''
            if 'Serves Wine' in h: row[h['Serves Wine']] = 'TRUE' if data.get('serves_wine') else ''

            # CRM outreach columns
            if 'Outreach_Status' in h: row[h['Outreach_Status']] = data.get('status', 'Call not answered')
            if 'Owner_Name' in h: row[h['Owner_Name']] = data.get('owner_name', '')
            if 'Owner_Number' in h: row[h['Owner_Number']] = data.get('owner_phone', '')
            if 'SPOC_Name' in h: row[h['SPOC_Name']] = data.get('spoc_name', '')
            if 'SPOC_Number' in h: row[h['SPOC_Number']] = data.get('spoc_phone', '')
            if 'SPOC_Designation' in h: row[h['SPOC_Designation']] = data.get('spoc_designation', '')
            if 'Outreach_Email' in h: row[h['Outreach_Email']] = data.get('email', '')
            if 'Bottles_Per_Week' in h: row[h['Bottles_Per_Week']] = data.get('bottles_per_week', '')
            if 'Last_Updated' in h: row[h['Last_Updated']] = datetime.now().isoformat()
            if 'Updated_By' in h: row[h['Updated_By']] = 'Manual Entry'

            # Assignment
            if data.get('assigned_to'):
                if 'Assigned_To' in h: row[h['Assigned_To']] = data['assigned_to']
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                if 'Assignment_History' in h:
                    row[h['Assignment_History']] = f"[{timestamp}|Manual Entry] → {data['assigned_to']}"

            # Initial note
            if data.get('note'):
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                if 'Outreach_Notes' in h:
                    row[h['Outreach_Notes']] = f"[{timestamp}|Manual Entry] {data['note']}"

            # Append the row
            worksheet.append_row(row, value_input_option='USER_ENTERED')

            # Invalidate cache
            global _horeca_crm_cache
            _horeca_crm_cache['expiry'] = None

            return {'success': True, 'place_id': place_id}
        except Exception as e:
            raise RuntimeError(f"Failed to add HoReCa record: {e}")

    def get_horeca_crm_summary(self, assigned_to=''):
        """Get CRM summary stats"""
        try:
            rows, headers = self._get_horeca_crm_cache()
            if not rows:
                return {'total': 0, 'statusCounts': {}, 'byZone': {}, 'byType': {}, 'recentUpdates': [], 'assignees': []}

            h = {}
            for i, hdr in enumerate(headers):
                h[hdr] = i

            status_counts = {}
            by_zone = {}
            by_type = {}
            recent = []
            all_assignees = set()

            for row in rows:
                def safe_get(idx):
                    return row[idx] if idx < len(row) else ''

                row_assignee = safe_get(h.get('Assigned_To', 65))
                if row_assignee:
                    all_assignees.add(row_assignee)

                # Apply assigned_to filter (case-insensitive)
                if assigned_to:
                    if assigned_to == 'Unassigned':
                        if row_assignee:
                            continue
                    elif row_assignee.strip().lower() != assigned_to.lower():
                        continue

                status = safe_get(h.get('Outreach_Status', 60)) or 'No Status'
                zone = safe_get(h.get('Zone_Name', 55)) or safe_get(h.get('Meso_Zone_Name', 55)) or 'Unknown'
                rtype = safe_get(h.get('HoReCa_Type', 34)) or safe_get(h.get('Primary Type', 3)) or 'Unknown'
                last_updated = safe_get(h.get('Last_Updated', 70))

                status_counts[status] = status_counts.get(status, 0) + 1

                if zone not in by_zone:
                    by_zone[zone] = {}
                by_zone[zone][status] = by_zone[zone].get(status, 0) + 1

                if rtype not in by_type:
                    by_type[rtype] = {}
                by_type[rtype][status] = by_type[rtype].get(status, 0) + 1

                if last_updated:
                    recent.append({
                        'name': safe_get(h.get('Name', 1)),
                        'status': status,
                        'updated': last_updated,
                        'updated_by': safe_get(h.get('Updated_By', 71)),
                    })

            # Sort recent by timestamp descending, take top 20
            recent.sort(key=lambda x: x['updated'], reverse=True)
            recent = recent[:20]

            # Sort by_zone by total count descending, take top 20
            zone_sorted = sorted(by_zone.items(), key=lambda x: sum(x[1].values()), reverse=True)[:20]

            return {
                'total': len(rows) if not assigned_to else sum(status_counts.values()),
                'statusCounts': status_counts,
                'byZone': dict(zone_sorted),
                'byType': by_type,
                'recentUpdates': recent,
                'assignees': sorted(all_assignees),
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get HoReCa CRM summary: {e}")

    def add_horeca_crm_headers(self):
        """One-time migration: add outreach column headers to BB1-BM1
        (originally BI-BT, shifted after deleting 7 micro zone columns)"""
        try:
            spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
            worksheet = spreadsheet.sheet1

            # Expand sheet if needed (BM = column 65)
            if worksheet.col_count < 65:
                worksheet.resize(cols=65)

            header_row = worksheet.row_values(1)
            crm_headers = [
                'Outreach_Status', 'Owner_Name', 'Owner_Number',
                'SPOC_Name', 'SPOC_Number', 'SPOC_Designation',
                'Outreach_Email', 'Bottles_Per_Week', 'Outreach_Notes',
                'Follow_Up_Date', 'Last_Updated', 'Updated_By',
            ]

            # Check if already added
            if 'Outreach_Status' in header_row:
                return {'success': True, 'message': 'CRM headers already exist', 'added': False}

            # Write headers BB1:BM1
            worksheet.update('BB1', [crm_headers])

            return {'success': True, 'message': 'CRM headers added (BB-BM)', 'added': True}
        except Exception as e:
            raise RuntimeError(f"Failed to add HoReCa CRM headers: {e}")

    def migrate_horeca_assignment_headers(self):
        """One-time migration: add Assigned_To (BN) and Assignment_History (BO) headers"""
        try:
            spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
            worksheet = spreadsheet.sheet1

            # Expand sheet if needed (BO = column 67)
            if worksheet.col_count < 67:
                worksheet.resize(cols=67)

            header_row = worksheet.row_values(1)
            if 'Assigned_To' in header_row:
                return {'success': True, 'message': 'Assignment headers already exist', 'added': False}

            worksheet.update('BN1', [['Assigned_To', 'Assignment_History']])
            return {'success': True, 'message': 'Assignment headers added (BN-BO)', 'added': True}
        except Exception as e:
            raise RuntimeError(f"Failed to add assignment headers: {e}")


# HoReCa CRM cache (process-level, 2-min TTL)
_horeca_crm_cache = {'data': None, 'headers': None, 'expiry': None}

# Cache for authorized users
_authorized_users_cache = {
    'users': None,
    'expiry': None
}


class AuthService:
    """Service for managing authorized users via Google Sheets"""

    def __init__(self):
        """Initialize Google Sheets client"""
        creds = get_google_credentials()
        self.gc = gspread.authorize(creds)
        self.spreadsheet_id = settings.google_sheets_id

    def get_authorized_users(self) -> List[Dict]:
        """Get list of authorized users from the Authorized-Users sheet.
        Cached for 5 minutes to avoid excessive API calls."""
        global _authorized_users_cache

        if (_authorized_users_cache['users'] is not None
                and _authorized_users_cache['expiry']
                and datetime.now() < _authorized_users_cache['expiry']):
            return _authorized_users_cache['users']

        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("Authorized-Users")
            records = worksheet.get_all_records()

            users = []
            for row in records:
                active = str(row.get('Active', 'TRUE')).upper()
                if active != 'TRUE':
                    continue
                users.append({
                    'email': str(row.get('Email', '')).strip().lower(),
                    'pin': str(row.get('PIN', '')).strip(),
                    'name': str(row.get('Name', '')).strip(),
                    'role': str(row.get('Role', 'field')).strip().lower(),
                })

            _authorized_users_cache['users'] = users
            _authorized_users_cache['expiry'] = datetime.now() + timedelta(minutes=5)
            return users
        except gspread.WorksheetNotFound:
            return []
        except Exception as e:
            raise RuntimeError(f"Failed to get authorized users: {e}")

    def validate_user(self, email: str, pin: str) -> Optional[Dict]:
        """Validate email + PIN against authorized users list"""
        users = self.get_authorized_users()
        email_lower = email.strip().lower()
        pin_stripped = pin.strip()

        for user in users:
            if user['email'] == email_lower and user['pin'] == pin_stripped:
                return {'email': user['email'], 'name': user['name'], 'role': user['role']}
        return None

    def init_authorized_users(self) -> Dict:
        """Initialize the Authorized-Users sheet with headers"""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)

            try:
                worksheet = spreadsheet.worksheet("Authorized-Users")
                return {'success': True, 'message': 'Sheet already exists'}
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title="Authorized-Users", rows=50, cols=5
                )
                headers = [['Email', 'PIN', 'Name', 'Role', 'Active']]
                worksheet.update('A1', headers)
                return {'success': True, 'message': 'Authorized-Users sheet created'}
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Authorized-Users sheet: {e}")


class GmailService:
    """Service for sending emails"""

    def __init__(self):
        """Initialize Gmail client"""
        creds = get_google_credentials()
        self.service = build('gmail', 'v1', credentials=creds)

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: List[str] = None,
        attachments: List[str] = None
    ) -> str:
        """
        Send an email

        Args:
            to: Recipient email
            subject: Email subject
            body: Email body (HTML supported)
            cc: CC recipients
            attachments: List of file paths to attach

        Returns:
            Message ID
        """
        import base64
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email import encoders

        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject

        if cc:
            message['cc'] = ', '.join(cc)

        message.attach(MIMEText(body, 'html'))

        if attachments:
            for file_path in attachments:
                with open(file_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{os.path.basename(file_path)}"'
                    )
                    message.attach(part)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        sent_message = self.service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()

        return sent_message['id']

    def send_confirmation_email(self, vp: VillagePanchayat, block_name: str):
        """Send confirmation email to village panchayat after meeting"""
        if not vp.email_id:
            raise ValueError("Village Panchayat email not available")

        subject = f"Goa DRS - RVM Collection Point Setup at {vp.name}"

        body = f"""
<html>
<body>
<p>Dear Secretary / Sarpanch,</p>

<p>Greetings from Goa Deposit Return Scheme (DRS) Team!</p>

<p>Thank you for meeting with us and your support in identifying a location for the
Reverse Vending Machine (RVM) collection point at <strong>{vp.name}</strong> Village Panchayat.</p>

<p>As discussed, we are pleased to confirm the following:</p>

<ul>
<li><strong>Village Panchayat:</strong> {vp.name}</li>
<li><strong>Block:</strong> {block_name}</li>
<li><strong>Location:</strong> {vp.location_address or 'To be finalized'}</li>
</ul>

<p><strong>Next Steps:</strong></p>
<ol>
<li>Please print the attached No Objection Certificate (NOC) on your official letterhead</li>
<li>Get it signed and stamped by the appropriate authority</li>
<li>Share the signed NOC with us via email or WhatsApp</li>
</ol>

<p>Once we receive the NOC, we will share the Service Agreement for your review and signature.</p>

<p><strong>Infrastructure Requirements:</strong></p>
<ul>
<li>Electricity connection (single phase)</li>
<li>Internet connectivity (WiFi/Ethernet)</li>
<li>Covered shed/shelter</li>
<li>Flat, level surface for machine placement</li>
</ul>

<p>If you have any questions, please feel free to reach out.</p>

<p>Best regards,<br>
Goa DRS Implementation Team</p>
</body>
</html>
"""

        return self.send_email(
            to=vp.email_id,
            subject=subject,
            body=body,
            cc=settings.notification_emails,
        )
