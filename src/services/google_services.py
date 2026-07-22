"""
Google Services integration for Sheets, Calendar, and Gmail
Uses refresh token for authentication (no credentials.json needed)
"""
import os
import json
import re
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


def _gs_retry(fn, *args, _attempts=4, _base_delay=2, **kwargs):
    """Call a gspread operation, retrying on transient Google Sheets errors
    (429 rate-limit and 5xx) with exponential backoff. This is what stops a
    momentary per-minute read-cap from surfacing to the browser as a 500 â€”
    it waits and retries instead of crashing the request."""
    import time as _t
    last = None
    for attempt in range(_attempts):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            code = None
            try:
                code = e.response.status_code
            except Exception:
                pass
            if code in (429, 500, 502, 503, 504) and attempt < _attempts - 1:
                last = e
                _t.sleep(_base_delay * (2 ** attempt))  # 2s, 4s, 8s
                continue
            raise
    if last:
        raise last


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

# OAuth configuration â€” from env vars or settings (loaded lazily to allow settings init first)
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
            all_values = _gs_retry(worksheet.get_all_values)
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
        """Sum of the 'Plan' column in the 'Plan RVM' sheet tab.

        Non-numeric cells (e.g. formula errors like #REF!) are treated as 0.
        Falls back to 301 only if the column/tab can't be read.
        """
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet("Plan RVM")
            all_values = _gs_retry(worksheet.get_all_values)
            if not all_values:
                return 301

            def _nk(s):
                return " ".join(str(s).split()).strip().lower()

            headers = [_nk(h) for h in all_values[0]]
            ci = next((i for i, h in enumerate(headers) if h == 'plan'), None)
            if ci is None:
                return 301
            total = 0
            for row in all_values[1:]:
                if ci < len(row):
                    total += _safe_int(row[ci].replace(',', ''), 0)
            return total if total > 0 else 301
        except Exception:
            return 301

    def get_deployment_data(self) -> List[Dict]:
        """Fetch all rows from the 'RVM_Deploy' sheet tab. Headers are on row 2
        (row 1 holds merged section titles), fed via an IMPORTRANGE from a
        separate 'Master Base' spreadsheet spanning columns A:AK â€” any columns
        added later (e.g. Electrical Done, Machine Date) live beyond AK and are
        picked up automatically since we read the whole sheet, not a fixed range.
        """
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet("RVM_Deploy")
            except Exception:
                return []
            # Use get_all_values() instead of get_all_records() to tolerate
            # duplicate or blank column headers that break get_all_records()
            all_values = _gs_retry(worksheet.get_all_values)
            if len(all_values) < 2:
                return []
            headers = [str(h).strip() for h in all_values[1]]
            records = []
            for row_vals in all_values[2:]:
                row = {}
                for i, header in enumerate(headers):
                    row[header] = row_vals[i].strip() if i < len(row_vals) else ''
                records.append(row)
            locations = []
            # Value normalizer (case-insensitive) for common status tokens
            _sn = {'done':'Done','yes':'Yes','no':'No','pending':'Pending',
                   'not required':'Not Required','not req':'Not Required','n/a':'Not Required','na':'Not Required'}
            def _nk(s):
                # normalize a header key: collapse internal whitespace/newlines, lowercase
                return " ".join(str(s).split()).strip().lower()
            for row in records:
                # Build a normalized-key view of the row so header renames, embedded
                # newlines, and case differences in the sheet don't break lookups.
                nrow = {}
                for k, v in row.items():
                    val = v.strip() if isinstance(v, str) else v
                    if isinstance(val, str):
                        val = _sn.get(val.lower(), val)
                    nrow[_nk(k)] = val
                def g(*names):
                    """First non-empty value among the given header aliases (normalized match)."""
                    found = None
                    for n in names:
                        k = _nk(n)
                        if k in nrow:
                            val = str(nrow.get(k) or '').strip()
                            if val:
                                return val
                            if found is None:
                                found = ''
                    return found if found is not None else ''
                loc_name = g('Location Name', 'Location_Name')
                entity_name = g('Entity Name', 'Entity_Name')
                # Keep any row that identifies a place. Some rows have an Entity Name
                # but no Location Name yet â€” those are still real locations and must
                # be counted (Location Identified should match the sheet's row count).
                if not loc_name and not entity_name:
                    continue
                current_stage = self._compute_deployment_stage(row)
                # Shed done = Delivery Status OR Installation Status is Yes (two separate
                # sub-steps in RVM_Deploy; the old tab had one combined status column).
                shed_delivery = g('Delivery Status')
                shed_install = g('Installation Status')
                shed_status = 'Yes' if (shed_delivery == 'Yes' or shed_install == 'Yes') else 'Pending'
                # Final Check uses Ready/Not Ready tokens (not Yes/Done like other columns).
                final_check = g('Final Check')
                machine_live = 'Yes' if final_check in ('Ready', 'Yes', 'Done') else final_check
                locations.append({
                    'locationName':    loc_name,
                    'block':           g('Block'),
                    'entityName':      g('Entity Name', 'Entity_Name'),
                    'entityType':      g('Entity Type', 'Entity_Type'),
                    'difficulty':      g('Difficulty'),
                    'collectionPoint': g('Collection Point', 'Collection_Point'),
                    'nocReceived':     g('NOC Received', 'NOC_Received'),
                    'agreementSigned': g('Service Agreement Signed', 'Service_Agreement_Signed'),
                    'siteClearanceReq':    g('Site Clearance requirement'),
                    'siteClearanceStatus': g('Site Clearance Status'),
                    'civilWorkReq':    g('Civil Work Requirement'),
                    'civilWorkStatus': g('Civil Work Status'),
                    'electricalStatus': g('Electrical Connection for Installation'),
                    'electricalDone':   g('Plug Point Installation Status', 'Electrical Done'),
                    'shedRequired': g('Shed Required'),
                    'shedType':     g('Shed Type'),
                    'shedDeliveryStatus': shed_delivery,
                    'shedInstallStatus':  shed_install,
                    'shedStatus':   shed_status,
                    'internetRequired': g('Internet Required'),
                    'internetStatus':   g('Internet Status'),
                    'cctvStatus': g('CCTV Installation Status'),
                    'rvmDelivery': g('RVM Delivery'),
                    'rvmDeployed': g('RVM Deployed with base fixing', 'RVM Deployed with Base Fixing', 'Machine install', 'RVM install'),
                    'finalCheck':  final_check,
                    'machineLive': machine_live,
                    'rvmWorkingCondition': g('RVM Working Condition Check'),
                    'installDate': g('Machine Date', 'Machine Install Date', 'Deployement Date', 'Deployment Date'),
                    'lat': g('Lat', 'Latitude'),
                    'lng': g('Long', 'Longitude', 'Lng'),
                    'blockPOC': g('Block POC'),
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

    def get_rc_data(self) -> list:
        """Fetch all rows from the 'RC Deployment' sheet tab.
        Returns empty list if tab does not exist yet.
        """
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet("RC Deployment")
            except Exception:
                return []
            all_values = _gs_retry(worksheet.get_all_values)
            if not all_values:
                return []
            headers = [str(h).strip() for h in all_values[0]]
            _sn = {'done':'Done','yes':'Yes','no':'No','pending':'Pending',
                   'not required':'Not Required','not req':'Not Required','n/a':'Not Required','na':'Not Required'}
            locations = []
            for row_vals in all_values[1:]:
                row = {headers[i]: (row_vals[i].strip() if i < len(row_vals) else '') for i in range(len(headers))}
                row = {k: _sn.get(str(v).strip().lower(), str(v).strip()) for k, v in row.items()}
                loc_name = str(row.get('Location Name', '') or row.get('Location_Name', '')).strip()
                if not loc_name:
                    continue
                locations.append({
                    'locationName':    loc_name,
                    'block':           str(row.get('Block', '')).strip(),
                    'entityName':      str(row.get('Entity Name', '') or row.get('Entity_Name', '')).strip(),
                    'rcTarget':        str(row.get('RC Target', '') or row.get('RC_Target', '')).strip(),
                    'nocReceived':     str(row.get('NOC Received', '')).strip(),
                    'agreementSigned': str(row.get('Service Agreement Signed', '')).strip(),
                    'civilWorkStatus': str(row.get('Civil Work Status', '')).strip(),
                    'shedStatus':      str(row.get('Shed Status', '')).strip(),
                    'electricalStatus':str(row.get('Electrical Connection for Installation', '')).strip(),
                    'internetStatus':  str(row.get('Internet Status', '')).strip(),
                    'cctvStatus':      str(row.get('CCTV Installation Status', '')).strip(),
                    'rcDelivery':      str(row.get('RC Delivery', '')).strip(),
                    'rcDeployed':      str(row.get('RC Deployed', '')).strip(),
                    'machineLive':     str(row.get('RC Working Condition', '')).strip(),
                    'installDate':     str(row.get('Machine Install Date', '')).strip(),
                    'lat':             str(row.get('Latitude', '') or row.get('Lat', '')).strip(),
                    'lng':             str(row.get('Longitude', '') or row.get('Lng', '')).strip(),
                })
            return locations
        except Exception as e:
            return []  # Gracefully return empty if sheet does not exist

    def init_rc_tab(self) -> dict:
        """Create the 'RC Deployment' tab in the Google Sheet with standard headers.
        Safe to call multiple times â€” skips if tab already exists.
        """
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            # Check if tab already exists
            try:
                spreadsheet.worksheet("RC Deployment")
                return {"status": "exists", "message": "RC Deployment tab already exists"}
            except Exception:
                pass
            # Create tab
            ws = spreadsheet.add_worksheet(title="RC Deployment", rows=200, cols=25)
            headers = [
                "Location Name", "Block", "Entity Name", "Entity Type",
                "RC Target", "Difficulty",
                "NOC Received", "Service Agreement Signed",
                "Civil Work Requirement", "Civil Work Status",
                "Shed Required", "Shed Type", "Shed Status",
                "Electrical Connection for Installation",
                "Internet Required", "Internet Status",
                "CCTV Installation Status",
                "RC Delivery", "RC Deployed",
                "Machine Install Date", "RC Working Condition",
                "Latitude", "Longitude", "Notes",
            ]
            ws.update('A1', [headers])
            # Add one dummy row so the sheet is not empty
            dummy = [
                "RC Demo Location", "North Goa", "Demo Entity", "Return Center",
                "1", "Low",
                "Yes", "Yes",
                "Yes", "Done",
                "No", "", "Not Required",
                "Done",
                "Yes", "Done",
                "Done",
                "Yes", "Done",
                "2026-07-01", "Done",
                "15.4909", "73.8278", "Dummy row â€” replace with real RC data",
            ]
            ws.update('A2', [dummy])
            return {"status": "created", "message": "RC Deployment tab created with headers and 1 dummy row", "tab": "RC Deployment"}
        except Exception as e:
            raise RuntimeError(f"Failed to init RC Deployment tab: {e}")

    # ==================== Plan vs Actual (PvA) Methods ====================

    def _get_or_create_pva_ws(self):
        """Return the RVM-PvA worksheet (18 cols Aâ€“R), creating it with headers if needed."""
        spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
        try:
            return spreadsheet.worksheet("RVM-PvA")
        except Exception:
            ws = spreadsheet.add_worksheet(title="RVM-PvA", rows=500, cols=18)
            ws.append_row([
                "Date", "Week",
                "Civil_Plan", "Civil_Actual",
                "Shed_Plan", "Shed_Actual",
                "Elec_Plan", "Elec_Actual",
                "Install_Plan", "Install_Actual",
                "Internet_Plan", "Internet_Actual",
                "CCTV_Plan", "CCTV_Actual",
                "Live_Plan", "Live_Actual",
                "Root_Cause_Type", "Remarks",
            ])
            return ws

    def get_pva_plans(self) -> list:
        """Read all plan+actual entries from the RVM-PvA tab (18-column schema)."""
        try:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            try:
                ws = spreadsheet.worksheet("RVM-PvA")
            except Exception:
                return []
            rows = ws.get_all_records()
            plans = []
            for r in rows:
                if not str(r.get("Date", "")).strip():
                    continue
                plans.append({
                    "date":             str(r.get("Date", "")).strip(),
                    "week":             _safe_int(r.get("Week", 0), 0),
                    "civil_plan":       _safe_int(r.get("Civil_Plan", 0), 0),
                    "civil_actual":     _safe_int(r.get("Civil_Actual", 0), 0),
                    "shed_plan":        _safe_int(r.get("Shed_Plan", 0), 0),
                    "shed_actual":      _safe_int(r.get("Shed_Actual", 0), 0),
                    "elec_plan":        _safe_int(r.get("Elec_Plan", 0), 0),
                    "elec_actual":      _safe_int(r.get("Elec_Actual", 0), 0),
                    "install_plan":     _safe_int(r.get("Install_Plan") or r.get("Machine Install Plan") or r.get("Machine_Install_Plan") or r.get("RVM_Deploy_Plan") or 0, 0),
                    "install_actual":   _safe_int(r.get("Install_Actual") or r.get("Machine Install Actual") or r.get("Machine_Install_Actual") or r.get("RVM_Deploy_Actual") or 0, 0),
                    "internet_plan":    _safe_int(r.get("Internet_Plan", 0), 0),
                    "internet_actual":  _safe_int(r.get("Internet_Actual", 0), 0),
                    "cctv_plan":        _safe_int(r.get("CCTV_Plan", 0), 0),
                    "cctv_actual":      _safe_int(r.get("CCTV_Actual", 0), 0),
                    "live_plan":        _safe_int(r.get("Live_Plan", 0), 0),
                    "live_actual":      _safe_int(r.get("Live_Actual", 0), 0),
                    "root_cause_type":  str(r.get("Root_Cause_Type", "") or "").strip(),
                    "notes":            str(r.get("Remarks", "") or "").strip(),
                })
            return sorted(plans, key=lambda x: x["date"])
        except Exception as e:
            logger.error(f"get_pva_plans error: {e}")
            return []

    def save_pva_plan(self, entry: dict) -> bool:
        """Append or overwrite a daily plan+actual entry in the RVM-PvA tab."""
        try:
            ws = self._get_or_create_pva_ws()
            all_vals = ws.get_all_values()
            target_date = str(entry.get("date", "")).strip()
            row_idx = None
            if len(all_vals) > 1:
                for i, row in enumerate(all_vals[1:], start=2):
                    if row and str(row[0]).strip() == target_date:
                        row_idx = i
                        break
            new_row = [
                target_date,
                str(entry.get("week", "")),
                str(entry.get("civil_plan", 0)),
                str(entry.get("civil_actual", 0)),
                str(entry.get("shed_plan", 0)),
                str(entry.get("shed_actual", 0)),
                str(entry.get("elec_plan", 0)),
                str(entry.get("elec_actual", 0)),
                str(entry.get("install_plan", 0)),
                str(entry.get("install_actual", 0)),
                str(entry.get("internet_plan", 0)),
                str(entry.get("internet_actual", 0)),
                str(entry.get("cctv_plan", 0)),
                str(entry.get("cctv_actual", 0)),
                str(entry.get("live_plan", 0)),
                str(entry.get("live_actual", 0)),
                str(entry.get("root_cause_type", "")),
                str(entry.get("notes", "")),
            ]
            if row_idx:
                ws.update(f"A{row_idx}:R{row_idx}", [new_row])
            else:
                ws.append_row(new_row)
            return True
        except Exception as e:
            logger.error(f"save_pva_plan error: {e}")
            return False

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

        # Cells can come back as int/float instead of str — Google Sheets
        # auto-detects numeric-looking values (e.g. an HTTP status code or a
        # scroll percentage) regardless of what type was originally written.
        # Coerce every field through str() before .strip() so a numeric cell
        # never raises AttributeError.
        def _s(v):
            return str(v).strip() if v is not None else ''

        users: dict = {}
        for r in records:
            email = _s(r.get('User_Email'))
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
            name = _s(r.get('User_Name'))
            if name:
                u['name'] = name
            ts = _s(r.get('Timestamp'))
            if ts > u['last_seen']:
                u['last_seen'] = ts
            try:
                u['hours'][int(ts[11:13])] += 1
            except Exception:
                pass
            ev = _s(r.get('Event_Type'))
            page = _s(r.get('Page'))
            element = _s(r.get('Element'))
            if ev == 'login':
                u['logins'] += 1
                u['total_logins'] += 1
                if _s(r.get('Device_Type')) == 'Mobile':
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
        """Auto-compute current stage as the first incomplete deployment step.

        Matches sheet headers via a normalized key (collapses whitespace/newlines,
        case-insensitive) so column renames don't silently break stage computation.
        A step counts as complete when its cell is 'Done' or 'Yes'.
        """
        def _nk(s):
            return " ".join(str(s).split()).strip().lower()
        nrow = {_nk(k): (str(val).strip() if isinstance(val, str) else val)
                for k, val in row.items()}

        def v(*keys):
            for k in keys:
                val = nrow.get(_nk(k))
                if val not in (None, ''):
                    return str(val).strip()
            return ''

        def done(val):
            return val in ('Done', 'Yes')

        if v('NOC Received', 'NOC_Received') != 'Yes':
            return 'NOC Pending'
        if v('Service Agreement Signed', 'Service_Agreement_Signed') != 'Yes':
            return 'Agreement Pending'
        shed = v('Shed Installation Status', 'Shed Status', 'Shed_Status')
        if shed and not done(shed) and shed != 'Not Required':
            return 'Shed Pending'
        elec = v('Electrical Work status', 'Electrical Connection for Installation')
        if elec and not done(elec) and elec != 'Not Required':
            return 'Electrical Pending'
        inet = v('Internet Status', 'Internet_Status')
        if inet and not done(inet) and inet != 'Not Required':
            return 'Internet Pending'
        cctv = v('CCTV Installation Status')
        if cctv and not done(cctv) and cctv != 'Not Required':
            return 'CCTV Pending'
        if not done(v('RVM Delivery')):
            return 'Machine Delivery Pending'
        if not done(v('Machine install', 'RVM install', 'RVM Deployed with Base Fixing')):
            return 'Machine Installation Pending'
        if not done(v('RVM Working Condition Check')):
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
                stage_map[stage.value] = num                          # email_sent â†’ 7
                label = STAGE_LABELS.get(stage, '')
                if label:
                    stage_map[label] = num                            # Email Sent â†’ 7
                    stage_map[label.lower()] = num                    # email sent â†’ 7

            # Legacy mappings
            stage_map['meeting_scheduled'] = 2
            stage_map['Meeting Scheduled'] = 2
            stage_map['follow_up_required'] = 3
            stage_map['Follow Up Required'] = 3
            stage_map['punch_meeting_required'] = 4

            # Read all rows (columns N and O: Current_Stage and Stage_Number)
            all_values = _gs_retry(worksheet.get_all_values)
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
                # New user â€” append row
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
                pass  # No progress yet â€” all users will show 0

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
    # Matches auto-appended DOD lines in Outreach_Notes, e.g.:
    # "[2026-07-09 10:15|Shilpa] STATUS_CHANGE: Meeting aligned -> OB Form Filled"
    HORECA_STATUS_CHANGE_RE = re.compile(
        r'^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\|([^\]]*)\]\s*STATUS_CHANGE:\s*(.*?)\s*->\s*(.*)$'
    )
    # Matches auto-appended attempt-log lines, e.g.:
    # "[2026-07-09 10:15|Shilpa] ATTEMPT_LOGGED: owner asked to call back tomorrow"
    HORECA_ATTEMPT_RE = re.compile(
        r'^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\|([^\]]*)\]\s*ATTEMPT_LOGGED(?::\s*(.*))?$'
    )

    # The team roster for the Overall Daily dashboard, in the order given.
    HORECA_ASSOCIATE_WHITELIST = [
        'varsha.madhyan@recykal.com',
        'aruna.shanmugam@recykal.com',
        'isabella.alexander@recykal.com',
        'shilpa.lazar@recykal.com',
        'rahul.das@recykal.com',
        'anil.goswami@recykal.com',
        'ayaan.sharif@recykal.com',
        'justin.nunes@recykal.com',
        'jagannath.pawar@recykal.com',
        'tynan.joshua@recykal.com',
    ]

    # Maps the free-text name variants actually seen in Assigned_To /
    # Updated_By / STATUS_CHANGE log entries to their canonical email.
    # Built from the live sheet's real distinct values. Deliberately does
    # NOT merge "Ayaansh" (23 occurrences in Updated_By) into "Ayaan" (72
    # occurrences) â€” these may be two different people, not a typo, so it's
    # left unmapped rather than guessed.
    HORECA_ASSOCIATE_ALIASES = {
        'varsha': 'varsha.madhyan@recykal.com',
        'aruna': 'aruna.shanmugam@recykal.com',
        'isabella': 'isabella.alexander@recykal.com',
        'shilpa': 'shilpa.lazar@recykal.com',
        'rahul das': 'rahul.das@recykal.com',
        'rahul': 'rahul.das@recykal.com',
        'anil': 'anil.goswami@recykal.com',
        'ayaan': 'ayaan.sharif@recykal.com',
        'justin': 'justin.nunes@recykal.com',
        'jagannath': 'jagannath.pawar@recykal.com',
        'jagganath': 'jagannath.pawar@recykal.com',
        'jaganath': 'jagannath.pawar@recykal.com',
        'tynan': 'tynan.joshua@recykal.com',
    }

    @classmethod
    def _resolve_associate_email(cls, raw_name):
        """Map a free-text associate name to a canonical whitelisted email,
        case/whitespace-insensitive. Returns None if unrecognized."""
        if not raw_name:
            return None
        return cls.HORECA_ASSOCIATE_ALIASES.get(raw_name.strip().lower())

    @staticmethod
    def _associate_display_name(email):
        local = email.split('@')[0]
        return ' '.join(part.capitalize() for part in local.split('.'))

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
        all_values = _gs_retry(worksheet.get_all_values)

        if len(all_values) < 2:
            _horeca_crm_cache['data'] = []
            _horeca_crm_cache['headers'] = []
            _horeca_crm_cache['clusters'] = ({}, {})
            _horeca_crm_cache['expiry'] = now + _HORECA_CACHE_TTL
            return [], []

        headers = all_values[0]
        rows = all_values[1:]

        _horeca_crm_cache['data'] = rows
        _horeca_crm_cache['headers'] = headers
        _horeca_crm_cache['clusters'] = self._get_horeca_duplicate_clusters(rows, headers)
        _horeca_crm_cache['expiry'] = now + _HORECA_CACHE_TTL
        return rows, headers

    def _get_horeca_clusters_cached(self):
        """Duplicate-cluster map for the currently cached HoReCa rows.
        (place_id -> cluster_root, cluster_root -> {members, primary})"""
        global _horeca_crm_cache
        self._get_horeca_crm_cache()  # ensures cache (and clusters) are populated/fresh
        return _horeca_crm_cache.get('clusters') or ({}, {})

    @staticmethod
    def _normalize_horeca_name(name):
        name = (name or '').lower().strip()
        name = re.sub(r'[^a-z0-9 ]', '', name)
        name = re.sub(r'\s+', ' ', name)
        return name

    @staticmethod
    def _haversine_meters(lat1, lng1, lat2, lng2):
        from math import radians, sin, cos, asin, sqrt
        try:
            lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)
        except (TypeError, ValueError):
            return None
        if not (lat1 or lng1) or not (lat2 or lng2):
            return None
        r = 6371000
        p1, p2 = radians(lat1), radians(lat2)
        dphi = radians(lat2 - lat1)
        dlmb = radians(lng2 - lng1)
        a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
        return 2 * r * asin(sqrt(a))

    # Same-name rows within this distance are treated as the same physical
    # outlet. Matches the scale of the offline ETL's own examples in the
    # "Duplicates" tab (6m-175m) â€” deliberately tight, since a common
    # generic name (e.g. "Aangan Restaurant") can legitimately recur at
    # unrelated locations many km apart and must NOT be merged.
    HORECA_DUPLICATE_GEO_THRESHOLD_M = 300

    def _get_horeca_duplicate_clusters(self, rows, headers):
        """Group Enhanced rows representing the same real-world business.

        Two signals, since the offline enrichment pipeline's own duplicate
        flags are unreliable in practice (Is_Duplicate is never TRUE in the
        live sheet, and Merged_Place_IDs is usually just self-referential):
          1) Merged_Place_IDs, when it points to a DIFFERENT Place ID than
             its own row â€” trust it, it's a genuine ETL-detected link.
          2) Exact match on normalized name + close geo proximity (<= 300m)
             â€” catches slip-throughs the ETL never flagged (e.g. two
             identical-name rows from different source batches that are
             actually the same physical outlet). Geo proximity, not the
             City text column, is the disambiguator: City values are
             inconsistently entered, while two rows genuinely 30+ km apart
             sharing a common name (verified real case: two unrelated
             "Aangan Restaurant"s) must never be merged just because the
             city field happens to match or be blank on both.

        Returns (place_to_cluster, cluster_info) where cluster_info maps a
        cluster root id -> {'members': [place_id, ...], 'primary': place_id}
        for every cluster with 2+ members. Singleton businesses aren't
        included â€” callers should treat "not present" as "not a duplicate".
        """
        h = {hdr: i for i, hdr in enumerate(headers)}
        pid_idx = h.get('Place ID', 0)
        name_idx = h.get('Name', 1)
        lat_idx = h.get('Latitude', 10)
        lng_idx = h.get('Longitude', 11)
        merged_idx = h.get('Merged_Place_IDs')
        last_updated_idx = h.get('Last_Updated', 63)

        def g(row, idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ''

        parent = {}

        def find(x):
            root = x
            while parent.get(root, root) != root:
                root = parent[root]
            while parent.get(x, x) != root:
                parent[x], x = root, parent.get(x, root)
            return root

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        place_ids = []
        name_buckets = {}  # normalized name -> [(place_id, lat, lng), ...]
        row_by_pid = {}

        for row in rows:
            pid = g(row, pid_idx)
            if not pid:
                continue
            place_ids.append(pid)
            row_by_pid[pid] = row
            parent.setdefault(pid, pid)

            if merged_idx is not None:
                merged = g(row, merged_idx)
                if merged and merged != pid:
                    for other in re.split(r'[,;|]', merged):
                        other = other.strip()
                        if other and other != pid:
                            parent.setdefault(other, other)
                            union(pid, other)

            norm_name = self._normalize_horeca_name(g(row, name_idx))
            if norm_name:
                lat, lng = g(row, lat_idx), g(row, lng_idx)
                name_buckets.setdefault(norm_name, []).append((pid, lat, lng))

        # Within each same-name bucket, union pairs that are also geographically
        # close â€” O(n^2) per bucket, but buckets are tiny (a handful of rows
        # sharing an exact normalized name out of ~16k total).
        for members in name_buckets.values():
            if len(members) < 2:
                continue
            for i in range(len(members)):
                pid_a, lat_a, lng_a = members[i]
                for j in range(i + 1, len(members)):
                    pid_b, lat_b, lng_b = members[j]
                    dist = self._haversine_meters(lat_a, lng_a, lat_b, lng_b)
                    if dist is not None and dist <= self.HORECA_DUPLICATE_GEO_THRESHOLD_M:
                        union(pid_a, pid_b)

        clusters = {}
        for pid in place_ids:
            clusters.setdefault(find(pid), []).append(pid)

        def last_updated_of(pid):
            row = row_by_pid.get(pid)
            return g(row, last_updated_idx) if row else ''

        place_to_cluster = {}
        cluster_info = {}
        for root, members in clusters.items():
            if len(members) < 2:
                continue
            primary = max(members, key=lambda pid: last_updated_of(pid) or '')
            cluster_info[root] = {'members': members, 'primary': primary}
            for m in members:
                place_to_cluster[m] = root

        return place_to_cluster, cluster_info

    def _collapse_horeca_duplicates(self, rows, headers):
        """Collapse duplicate-cluster rows down to one (the freshest) per
        cluster. Read-time only â€” never mutates the sheet. Returns
        (collapsed_rows, merge_meta) where merge_meta maps the surviving
        primary's Place ID -> {'merged_place_ids': [...], 'cluster_size': N}.
        """
        place_to_cluster, cluster_info = self._get_horeca_clusters_cached()
        if not cluster_info:
            return rows, {}

        h = {hdr: i for i, hdr in enumerate(headers)}
        pid_idx = h.get('Place ID', 0)

        collapsed = []
        merge_meta = {}
        for row in rows:
            pid = row[pid_idx] if pid_idx < len(row) else ''
            root = place_to_cluster.get(pid)
            if root is None:
                collapsed.append(row)
                continue
            info = cluster_info[root]
            if pid != info['primary']:
                continue  # skip non-primary duplicate rows entirely
            collapsed.append(row)
            merge_meta[pid] = {
                'merged_place_ids': [m for m in info['members'] if m != pid],
                'cluster_size': len(info['members']),
            }
        return collapsed, merge_meta

    def _parse_horeca_status_changes(self, notes_text, place_id='', name=''):
        """Extract STATUS_CHANGE events auto-logged into Outreach_Notes."""
        events = []
        if not notes_text:
            return events
        for line in notes_text.split('\n'):
            line = line.strip()
            if not line or line == '---':
                continue
            m = self.HORECA_STATUS_CHANGE_RE.match(line)
            if not m:
                continue
            date_s, time_s, associate, from_status, to_status = m.groups()
            events.append({
                'place_id': place_id,
                'name': name,
                'date': date_s,
                'time': time_s,
                'timestamp': f'{date_s} {time_s}',
                'associate': associate.strip(),
                'from_status': from_status.strip(),
                'to_status': to_status.strip(),
            })
        return events

    def _parse_horeca_attempts(self, notes_text, place_id='', name=''):
        """Extract ATTEMPT_LOGGED events auto-logged into Outreach_Notes.
        Attempts are tracked going forward only â€” there's no way to
        recover contact-attempt history for businesses touched before this
        existed, so this is genuinely empty for most pre-existing leads."""
        attempts = []
        if not notes_text:
            return attempts
        for line in notes_text.split('\n'):
            line = line.strip()
            if not line or line == '---':
                continue
            m = self.HORECA_ATTEMPT_RE.match(line)
            if not m:
                continue
            date_s, time_s, associate, note = m.groups()
            attempts.append({
                'place_id': place_id,
                'name': name,
                'date': date_s,
                'time': time_s,
                'timestamp': f'{date_s} {time_s}',
                'associate': associate.strip(),
                'note': (note or '').strip(),
            })
        return attempts

    def log_horeca_attempt(self, place_id, note='', author='Team', actor_email='', actor_name=''):
        """Append a contact-attempt entry into Outreach_Notes (same
        append-only convention as STATUS_CHANGE â€” no new sheet structure).
        Returns the attempt count for this business so far (this session
        onward only)."""
        try:
            row_num = self.find_horeca_row(place_id)
            if not row_num:
                raise ValueError(f"HoReCa record not found: {place_id}")

            spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
            worksheet = spreadsheet.sheet1

            associate = actor_name or actor_email or author or 'Team'
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            suffix = f': {note}' if note else ''
            log_line = f'[{timestamp}|{associate}] ATTEMPT_LOGGED{suffix}'

            existing_notes = worksheet.acell(f'BJ{row_num}').value or ''
            combined_notes = f'{log_line}\n---\n{existing_notes}' if existing_notes else log_line
            worksheet.update(f'BJ{row_num}', [[combined_notes]])
            worksheet.update(f'BL{row_num}', [[datetime.now().isoformat()]])
            worksheet.update(f'BM{row_num}', [[associate]])

            global _horeca_crm_cache
            _horeca_crm_cache['expiry'] = None

            attempt_count = len(self._parse_horeca_attempts(combined_notes))
            return {'success': True, 'attempt_count': attempt_count}
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to log HoReCa attempt: {e}")

    def _horeca_row_to_dict(self, row, headers, merge_meta=None):
        """Convert a HoReCa row to a frontend-friendly dict"""
        def safe_get(idx):
            return row[idx] if idx < len(row) else ''

        # Build a header-index map for key columns
        h = {}
        for i, hdr in enumerate(headers):
            h[hdr] = i

        place_id = safe_get(h.get('Place ID', 0))
        merge_info = (merge_meta or {}).get(place_id)

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
            'place_id': place_id,
            'is_merged': bool(merge_info),
            'merged_place_ids': merge_info['merged_place_ids'] if merge_info else [],
            'cluster_size': merge_info['cluster_size'] if merge_info else 1,
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
            # Meso zone fields (5 kmÂ²) â€” indices updated after 7 micro col deletion
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
            'pan_number': safe_get(h['PAN_Number']) if 'PAN_Number' in h else '',
            'gst_number': safe_get(h['GST_Number']) if 'GST_Number' in h else '',
        }

    def get_horeca_map_data(self) -> dict:
        """Compact HoReCa dataset for the deployment map.

        pins  = outlets with an Outreach_Status OR a Superset-ACTIVE link
                (onboarded/pipeline), full detail
        heat  = [lat, lng] pairs for not-yet-contacted outlets (density heatmap)
        De-listed, duplicate and temporarily-closed rows are excluded.

        Onboarded truth comes from Superset (the system of record): a pin is
        onboarded if its Enhanced row is linked to a Superset ACTIVE record
        (AppSheet_Lead_ID / PAN / GST / FSSAI), with Outreach_Status ==
        'OB Form Filled' kept as a fallback for self-reported-but-unmatched
        rows. Superset-ACTIVE businesses with no Enhanced pin get their own
        pin from app_sheet's Location column when available; the remainder
        is counted in counts.onboarded_nocoord.
        """
        rows, headers = self._get_horeca_crm_cache()
        h = {hdr: i for i, hdr in enumerate(headers)}

        def val(row, name, default_idx=None):
            idx = h.get(name, default_idx)
            return row[idx].strip() if idx is not None and idx < len(row) else ''

        def fnum(s):
            try:
                v = float(s)
                return v if v != 0 else None
            except (ValueError, TypeError):
                return None

        rows, _ = self._collapse_horeca_duplicates(rows, headers)

        # --- Superset-ACTIVE link sets from the (cached) classification ---
        active_items = []
        try:
            validation = self.get_horeca_superset_validation() or {}
            cls = validation.get('classification') or {}
            active_items = (cls.get('organic') or []) + (cls.get('inorganic') or [])
        except Exception:
            pass

        # Map each link key -> the Superset business (item index) it belongs
        # to, so onboarded can be counted as DISTINCT Superset businesses
        # (not per-Enhanced-row â€” duplicate PAN rows must not inflate it).
        linked = {'A': {}, 'P': {}, 'G': {}, 'F': {}}  # id -> onboarded_date
        key_to_item = {}   # (tag, id) -> item index
        item_keys = []     # parallel to active_items: list of link keys per item
        item_has_coord = [False] * len(active_items)
        for idx, it in enumerate(active_items):
            keys = []
            for tag, field in (('A', 'appsheet_id'), ('P', 'pan'),
                               ('G', 'gst'), ('F', 'fssai')):
                v = (it.get(field) or '').strip()
                if v:
                    linked[tag].setdefault(v, it.get('onboarded_date') or '')
                    key_to_item.setdefault((tag, v), idx)
                    keys.append((tag, v))
            item_keys.append(keys)

        # app_sheet ID -> "lat,lng" for the no-Enhanced-coords fallback pins
        app_loc_by_id = {}
        try:
            app_rows, app_headers = self._get_appsheet_cache()
            ah = {hdr: i for i, hdr in enumerate(app_headers)}
            aid_i, aloc_i = ah.get('ID'), ah.get('Location')
            for arow in app_rows:
                aid = arow[aid_i].strip() if aid_i is not None and aid_i < len(arow) else ''
                aloc = arow[aloc_i].strip() if aloc_i is not None and aloc_i < len(arow) else ''
                if aid and aloc:
                    app_loc_by_id[aid] = aloc
        except Exception:
            pass

        pins, heat = [], []
        counts = {'onboarded': 0, 'pipeline': 0, 'unreached': 0,
                  'onboarded_nocoord': 0}
        consumed = set()  # (tag, id) link keys already represented by a pin
        for row in rows:
            lat = fnum(val(row, 'Latitude', 10))
            lng = fnum(val(row, 'Longitude', 11))
            status = val(row, 'Outreach_Status', 53)
            if status == 'De-listed':
                continue

            # Is this Enhanced row linked to a Superset ACTIVE record?
            row_keys = []
            for tag, v in (('A', val(row, 'AppSheet_Lead_ID')),
                           ('P', val(row, 'PAN_Number').upper()),
                           ('G', val(row, 'GST_Number').upper()),
                           ('F', val(row, 'FSSAI_Number'))):
                if v and v in linked[tag]:
                    row_keys.append((tag, v))
            is_linked = bool(row_keys)

            if lat is None or lng is None:
                continue  # no coords: superset link (if any) handled below

            if status or is_linked:
                # Onboarded = confirmed by Superset (system of record) ONLY,
                # and counted per DISTINCT Superset business â€” so the map
                # total ties to Superset's ACTIVE figure (~1,112), never
                # inflated by self-reported claims or duplicate Enhanced rows.
                onboarded = is_linked
                if not onboarded:
                    counts['pipeline'] += 1
                ob_date = ''
                for tag, v in row_keys:
                    consumed.add((tag, v))
                    item_idx = key_to_item.get((tag, v))
                    if item_idx is not None:
                        item_has_coord[item_idx] = True  # this business has a real location
                    if not ob_date:
                        ob_date = linked[tag].get(v, '')
                pins.append({
                    'name': val(row, 'Name', 1),
                    'type': val(row, 'HoReCa_Type', 34) or val(row, 'Primary Type', 3),
                    'city': val(row, 'City', 6),
                    'lat': round(lat, 5),
                    'lng': round(lng, 5),
                    'status': status or 'Onboarded (Superset)',
                    'onboarded': onboarded,
                    'ob_date': ob_date,
                    'source': 'enhanced',
                })
            else:
                if val(row, 'Business Status', 28) == 'CLOSED_TEMPORARILY':
                    continue
                counts['unreached'] += 1
                heat.append([round(lat, 5), round(lng, 5)])

        # --- Superset-ACTIVE businesses not represented by any Enhanced pin:
        # draw them from app_sheet Location where available.
        for idx, (it, keys) in enumerate(zip(active_items, item_keys)):
            if item_has_coord[idx] or any(k in consumed for k in keys):
                continue
            for k in keys:
                consumed.add(k)
            appid = (it.get('appsheet_id') or '').strip()
            a_lat = a_lng = None
            if appid and appid in app_loc_by_id:
                a_lat, a_lng = self._parse_latlng(app_loc_by_id[appid])
            if a_lat is not None and a_lng is not None:
                item_has_coord[idx] = True
                pins.append({
                    'name': it.get('superset_name') or '',
                    'type': '', 'city': it.get('city') or '',
                    'lat': round(a_lat, 5), 'lng': round(a_lng, 5),
                    'status': 'Onboarded (Superset)',
                    'onboarded': True,
                    'ob_date': it.get('onboarded_date') or '',
                    'source': 'appsheet-coords',
                })

        # Onboarded counts are per DISTINCT Superset business â†’ tie to ACTIVE.
        counts['onboarded'] = sum(1 for v in item_has_coord if v)
        counts['onboarded_nocoord'] = len(active_items) - counts['onboarded']

        return {'pins': pins, 'heat': heat, 'counts': counts}

    def get_horeca_crm_data(self, search='', status='', htype='',
                            zone='', city='', assigned_to='', page=1, page_size=50):
        """Get filtered, paginated HoReCa CRM data"""
        try:
            rows, headers = self._get_horeca_crm_cache()
            if not rows:
                return {'records': [], 'total': 0, 'page': 1, 'total_pages': 0}

            rows, merge_meta = self._collapse_horeca_duplicates(rows, headers)

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

            records = [self._horeca_row_to_dict(r, headers, merge_meta) for r in page_rows]

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

    def _ensure_enhanced_pan_gst_columns(self):
        """One-time, idempotent migration: add PAN_Number, GST_Number, and
        FSSAI_Number columns to Enhanced (same safe pattern as
        AppSheet_Lead_ID â€” verify empty before claiming). Returns
        {'PAN_Number': idx, 'GST_Number': idx, 'FSSAI_Number': idx}
        (1-based column indices)."""
        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        worksheet = spreadsheet.sheet1
        header_row = worksheet.row_values(1)
        result = {}
        col_names = ('PAN_Number', 'GST_Number', 'FSSAI_Number')
        needed = [c for c in col_names if c not in header_row]

        for col_name in col_names:
            if col_name in header_row:
                result[col_name] = header_row.index(col_name) + 1

        if not needed:
            return result

        next_col_idx = len(header_row) + 1
        for col_name in needed:
            sample_cells = worksheet.range(2, next_col_idx, 20, next_col_idx)
            if any(c.value for c in sample_cells):
                raise RuntimeError(
                    f'Column {next_col_idx} on Enhanced is not empty â€” refusing to claim it as {col_name}'
                )
            if worksheet.col_count < next_col_idx:
                worksheet.resize(cols=next_col_idx)
            worksheet.update_cell(1, next_col_idx, col_name)
            result[col_name] = next_col_idx
            header_row.append(col_name)
            next_col_idx += 1

        global _horeca_crm_cache
        _horeca_crm_cache['expiry'] = None
        return result

    def update_horeca_outreach(self, place_id, updates, author='Team', actor_email='', actor_name=''):
        """Update outreach fields for a HoReCa record"""
        try:
            row_num = self.find_horeca_row(place_id)
            if not row_num:
                raise ValueError(f"HoReCa record not found: {place_id}")

            spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
            worksheet = spreadsheet.sheet1

            # Capture the prior status before any writes below, so a real
            # transition can be auto-logged into Outreach_Notes afterward
            # (DOD day-on-day tracking â€” see bottom of this method).
            new_status = updates.get('outreach_status')
            from_status = ''
            if new_status:
                from_status = worksheet.acell(f'BB{row_num}').value or ''

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
                new_entry = f"[{timestamp}|{author}] â†’ {assignee}"

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

            # PAN/GST resolved by header name (not a hardcoded letter) since
            # these columns were added after HORECA_CRM_COL_MAP was written.
            pan_val = updates.get('pan_number')
            gst_val = updates.get('gst_number')
            if pan_val is not None or gst_val is not None:
                col_idx_by_name = self._ensure_enhanced_pan_gst_columns()
                if pan_val is not None and 'PAN_Number' in col_idx_by_name:
                    worksheet.update_cell(row_num, col_idx_by_name['PAN_Number'], str(pan_val))
                if gst_val is not None and 'GST_Number' in col_idx_by_name:
                    worksheet.update_cell(row_num, col_idx_by_name['GST_Number'], str(gst_val))

            # Always update Last_Updated and Updated_By
            worksheet.update(f'BL{row_num}', [[datetime.now().isoformat()]])
            worksheet.update(f'BM{row_num}', [[author]])

            # Auto-log real status transitions into Outreach_Notes (existing,
            # already-append-only column â€” no new sheet structure). This is
            # what powers the Day-on-Day view and per-business timeline.
            # Never let a logging hiccup break the update the user is waiting on.
            if new_status and new_status != from_status:
                try:
                    associate = actor_name or actor_email or author or 'Team'
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                    log_line = f"[{timestamp}|{associate}] STATUS_CHANGE: {from_status or '(none)'} -> {new_status}"
                    existing_notes = worksheet.acell(f'BJ{row_num}').value or ''
                    combined_notes = f"{log_line}\n---\n{existing_notes}" if existing_notes else log_line
                    worksheet.update(f'BJ{row_num}', [[combined_notes]])
                except Exception:
                    pass

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
            if data.get('pan_number') or data.get('gst_number'):
                self._ensure_enhanced_pan_gst_columns()
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
            if 'PAN_Number' in h: row[h['PAN_Number']] = data.get('pan_number', '')
            if 'GST_Number' in h: row[h['GST_Number']] = data.get('gst_number', '')
            if 'Last_Updated' in h: row[h['Last_Updated']] = datetime.now().isoformat()
            if 'Updated_By' in h: row[h['Updated_By']] = 'Manual Entry'

            # Assignment
            if data.get('assigned_to'):
                if 'Assigned_To' in h: row[h['Assigned_To']] = data['assigned_to']
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                if 'Assignment_History' in h:
                    row[h['Assignment_History']] = f"[{timestamp}|Manual Entry] â†’ {data['assigned_to']}"

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

            rows, _ = self._collapse_horeca_duplicates(rows, headers)

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

    def get_horeca_associate_status_snapshot(self):
        """Current-state snapshot for the Overall Daily dashboard: for each
        whitelisted associate, how many businesses they're responsible for
        sit at each Outreach_Status right now. This is a live count of
        current holdings, not a history of events â€” a business counts once,
        under whatever status it's at today, however many times that status
        has changed. Duplicate-cluster rows are collapsed first so a merged
        business isn't double-counted under two associates.

        Only the roster in HORECA_ASSOCIATE_WHITELIST is returned (all 10,
        even with zero counts) â€” free-text Assigned_To values that don't
        resolve to one of them (via HORECA_ASSOCIATE_ALIASES) are counted
        in 'unmapped_count' but not attributed to anyone, rather than
        guessed."""
        rows, headers = self._get_horeca_crm_cache()
        rows, _ = self._collapse_horeca_duplicates(rows, headers)
        h = {hdr: i for i, hdr in enumerate(headers)}
        assigned_idx = h.get('Assigned_To', 65)
        status_idx = h.get('Outreach_Status', 53)

        by_associate = {
            email: {s: 0 for s in self.HORECA_OUTREACH_STATUSES}
            for email in self.HORECA_ASSOCIATE_WHITELIST
        }
        unmapped_count = 0
        for row in rows:
            assignee = row[assigned_idx].strip() if assigned_idx < len(row) else ''
            if not assignee:
                continue
            status = row[status_idx].strip() if status_idx < len(row) else ''
            if status not in self.HORECA_OUTREACH_STATUSES:
                continue
            email = self._resolve_associate_email(assignee)
            if not email:
                unmapped_count += 1
                continue
            by_associate[email][status] += 1

        return {
            'statuses': self.HORECA_OUTREACH_STATUSES,
            'associates': {
                self._associate_display_name(email): bucket
                for email, bucket in by_associate.items()
            },
            'unmapped_count': unmapped_count,
        }

    def get_horeca_business_timeline(self, place_id):
        """Chronological status-change history for a business, merged across
        any duplicate cluster it belongs to (so a duplicate pair shows one
        combined feed instead of two separate ones)."""
        rows, headers = self._get_horeca_crm_cache()
        place_to_cluster, cluster_info = self._get_horeca_clusters_cached()
        h = {hdr: i for i, hdr in enumerate(headers)}
        pid_idx = h.get('Place ID', 0)
        notes_idx = h.get('Outreach_Notes', 61)
        name_idx = h.get('Name', 1)

        root = place_to_cluster.get(place_id)
        member_ids = set(cluster_info[root]['members']) if root else {place_id}

        events = []
        attempts = []
        for row in rows:
            pid = row[pid_idx] if pid_idx < len(row) else ''
            if pid not in member_ids:
                continue
            name = row[name_idx] if name_idx < len(row) else ''
            notes = row[notes_idx] if notes_idx < len(row) else ''
            events.extend(self._parse_horeca_status_changes(notes, pid, name))
            attempts.extend(self._parse_horeca_attempts(notes, pid, name))

        events.sort(key=lambda e: e['timestamp'])
        attempts.sort(key=lambda a: a['timestamp'])
        return {
            'place_id': place_id,
            'is_merged': len(member_ids) > 1,
            'cluster_size': len(member_ids),
            'events': events,
            'attempts': attempts,
            'attempt_count': len(attempts),
        }

    def get_horeca_cycle_time(self, place_id):
        """Approximate lead-to-OB-Filled cycle time from auto-logged
        STATUS_CHANGE events. For businesses that existed before this
        tracking was added, the first tracked event only marks when the
        feature first observed them â€” not their true original lead date â€”
        so this is exact only for businesses created after this shipped."""
        timeline = self.get_horeca_business_timeline(place_id)
        events = timeline['events']
        if not events:
            return {'place_id': place_id, 'cycle_days': None, 'reason': 'no tracked activity yet'}

        ob_filled_event = next((e for e in events if e['to_status'] == 'OB Form Filled'), None)
        if not ob_filled_event:
            return {'place_id': place_id, 'cycle_days': None, 'reason': 'not yet OB Form Filled'}

        fmt = '%Y-%m-%d %H:%M'
        first_event = events[0]
        start = datetime.strptime(first_event['timestamp'], fmt)
        end = datetime.strptime(ob_filled_event['timestamp'], fmt)
        days = (end - start).total_seconds() / 86400
        return {
            'place_id': place_id,
            'cycle_days': round(days, 1),
            'first_tracked': first_event['timestamp'],
            'ob_filled_at': ob_filled_event['timestamp'],
            'approximate': True,
        }

    def get_horeca_cycle_time_overview(self):
        """Aggregate lead-to-OB-Filled cycle time across ALL businesses,
        using ONLY real tracked STATUS_CHANGE history (never the
        approximate backfill â€” a single snapshot point can't tell you how
        long a journey took). Since real tracking only started recently,
        this will show a small or zero sample size for a while; that's
        surfaced explicitly via sample_size rather than faked."""
        rows, headers = self._get_horeca_crm_cache()
        rows, _ = self._collapse_horeca_duplicates(rows, headers)
        h = {hdr: i for i, hdr in enumerate(headers)}
        notes_idx = h.get('Outreach_Notes', 61)
        pid_idx = h.get('Place ID', 0)
        name_idx = h.get('Name', 1)

        fmt = '%Y-%m-%d %H:%M'
        cycle_days = []
        for row in rows:
            notes = row[notes_idx] if notes_idx < len(row) else ''
            if not notes:
                continue
            pid = row[pid_idx] if pid_idx < len(row) else ''
            name = row[name_idx] if name_idx < len(row) else ''
            real_events = self._parse_horeca_status_changes(notes, pid, name)
            if not real_events:
                continue
            ob_event = next((e for e in real_events if e['to_status'] == 'OB Form Filled'), None)
            if not ob_event:
                continue
            real_events.sort(key=lambda e: e['timestamp'])
            start = datetime.strptime(real_events[0]['timestamp'], fmt)
            end = datetime.strptime(ob_event['timestamp'], fmt)
            cycle_days.append((end - start).total_seconds() / 86400)

        if not cycle_days:
            return {'sample_size': 0, 'avg_days': None, 'median_days': None}

        cycle_days.sort()
        n = len(cycle_days)
        mid = n // 2
        median = cycle_days[mid] if n % 2 else (cycle_days[mid - 1] + cycle_days[mid]) / 2
        return {
            'sample_size': n,
            'avg_days': round(sum(cycle_days) / n, 1),
            'median_days': round(median, 1),
        }

    def get_horeca_metrics_overview(self, stuck_threshold_days=14):
        """Top-line metrics for the HoReCa Metrics dashboard: conversion
        rate (both denominators â€” worked leads and total database), a
        current funnel snapshot, a stuck-lead count, and the real-only
        cycle-time aggregate above."""
        rows, headers = self._get_horeca_crm_cache()
        rows, _ = self._collapse_horeca_duplicates(rows, headers)
        h = {hdr: i for i, hdr in enumerate(headers)}
        status_idx = h.get('Outreach_Status', 53)
        last_updated_idx = h.get('Last_Updated', 63)

        TERMINAL_STATUSES = {'OB Form Filled', 'De-listed'}
        total = len(rows)
        worked = 0
        ob_filled = 0
        funnel = {s: 0 for s in self.HORECA_OUTREACH_STATUSES}
        stuck = 0
        now = datetime.now()

        for row in rows:
            status = row[status_idx].strip() if status_idx < len(row) else ''
            if not status:
                continue
            worked += 1
            if status in self.HORECA_OUTREACH_STATUSES:
                funnel[status] += 1
            if status == 'OB Form Filled':
                ob_filled += 1
            if status not in TERMINAL_STATUSES:
                last_updated = row[last_updated_idx].strip() if last_updated_idx < len(row) else ''
                dt = self._parse_enhanced_datetime(last_updated)
                if dt and (now - dt).days >= stuck_threshold_days:
                    stuck += 1

        return {
            'total_businesses': total,
            'worked_leads': worked,
            'ob_filled': ob_filled,
            'conversion_rate_worked': round(ob_filled / worked * 100, 1) if worked else 0,
            'conversion_rate_total': round(ob_filled / total * 100, 1) if total else 0,
            'funnel': funnel,
            'stuck_leads': stuck,
            'stuck_threshold_days': stuck_threshold_days,
            'cycle_time': self.get_horeca_cycle_time_overview(),
        }

    def _get_appsheet_onboarded(self):
        """Businesses associates have marked 'OB Form filled' in app_sheet â€”
        the LIVE onboarded source (moves within the ~2-min cache the moment
        an associate updates, no Superset paste needed). One entry per row:
        name, id, lat, lng (parsed from Location, may be None), date (from
        'Last updated Date', may be None), pan, gst."""
        out = []
        try:
            app_rows, app_headers = self._get_appsheet_cache()
            ai = {hd: i for i, hd in enumerate(app_headers)}

            def ag(row, col):
                i = ai.get(col)
                return row[i].strip() if i is not None and i < len(row) else ''

            for arow in app_rows:
                if ag(arow, 'Lead Stage').lower().strip() != 'ob form filled':
                    continue
                lat, lng = self._parse_latlng(ag(arow, 'Location'))
                d = None
                try:
                    v = ag(arow, 'Last updated Date')
                    if v:
                        d = datetime.fromisoformat(v.strip()[:10]).date()
                except ValueError:
                    d = None
                dt = ag(arow, 'Document_Type').upper()
                dn = ag(arow, 'Document_Number').upper()
                out.append({
                    'name': ag(arow, 'HoReCa Name'), 'id': ag(arow, 'ID'),
                    'lat': lat, 'lng': lng, 'date': d,
                    'city': ag(arow, 'City'), 'poc': ag(arow, 'Lead POC'),
                    'pan': dn if 'PAN' in dt else '', 'gst': dn if 'GST' in dt else '',
                })
        except Exception:
            pass
        return out

    def warm_horeca_caches(self):
        """Force-refresh the heavy HoReCa caches so a user request never
        triggers the ~9s cold Sheets read. Called on an interval by the in-app
        `_cache_warmer` thread (endpoints.py) — no external scheduler involved.
        Clears the sheet-cache expiries, reloads them fresh, then recomputes the
        Overview and Insight (validation) views into their caches."""
        global _horeca_crm_cache, _appsheet_cache, _superset_cache, _superset_v1_cache
        # Clear + reload each cache one at a time so no cache sits empty longer
        # than its own reload — a concurrent user read still finds the others warm.
        _horeca_crm_cache['expiry'] = None
        self._get_horeca_crm_cache()
        _appsheet_cache['expiry'] = None
        self._get_appsheet_cache()
        _superset_cache['expiry'] = None
        self._get_superset_cache()
        _superset_v1_cache['expiry'] = None
        self._get_superset_v1_cache()
        # Recompute derived views (read the now-warm sheet caches) into their caches.
        self.get_horeca_overview()
        self._compute_superset_validation()

    def get_horeca_overview(self, target=10000, run_rate_window_days=30):
        """Overview tab: funnel KPIs (cumulative, from Enhanced), the REAL
        onboarded count (Superset ACTIVE) shown alongside our self-reported
        OB Form Filled, conversion ratios, a run-rate/target projection, and
        Day-on-Day + Month-on-Month movement tables.

        DoD/MoM movement is derived from each Enhanced row's Last_Updated
        date bucketed under its current status tier â€” approximate for history
        (Last_Updated only marks the latest touch), exact going forward. The
        onboarded TOTAL is reconciled against Superset (the real backend), so
        the headline number is trustworthy even though per-day attribution is
        Enhanced-based."""
        rows, headers = self._get_horeca_crm_cache()
        rows, _ = self._collapse_horeca_duplicates(rows, headers)
        h = {hdr: i for i, hdr in enumerate(headers)}
        status_idx = h.get('Outreach_Status', 53)
        # DoD/MoM are dated off "Updated Date" (the field team's own work date),
        # NOT "Last_Updated" â€” the latter is an app timestamp that gets bumped
        # by any edit (incl. bulk sync/backfill ops), which produced impossible
        # single-day spikes. "Updated Date" reflects when work actually happened.
        updated_date_idx = h.get('Updated Date')
        notes_idx = h.get('Outreach_Notes', 61)
        pid_idx = h.get('Place ID', 0)
        name_idx = h.get('Name', 1)
        appid_idx = h.get('AppSheet_Lead_ID')
        pan_idx = h.get('PAN_Number')
        gst_idx = h.get('GST_Number')
        lastupd_idx = h.get('Last_Updated', 63)

        def parse_work_date(val):
            if not val:
                return None
            try:
                return datetime.fromisoformat(val.strip()[:10]).date()
            except ValueError:
                return None

        order = self.HORECA_OUTREACH_STATUSES
        reached_bar = order.index('Meeting done')
        started_bar = order.index('OB Form Opened')

        def rank(status):
            try:
                return order.index(status)
            except ValueError:
                return -1

        total_db = len(rows)
        no_status = 0
        delisted = 0
        reached = 0          # Meeting done or beyond (real connections)
        ob_opened = 0        # OB Form Opened or Filled
        ob_filled = 0        # self-reported onboarded
        touch_base = 0       # any non-blank status
        undated_onboarded = 0  # OB Filled with no work date (historical)
        first_onboard_date = None

        now = datetime.now()
        today = now.date()

        # Day, week and month buckets: date -> {reached, started, onboarded}
        dod = {}
        wow = {}
        mom = {}

        def bucket(store, key):
            return store.setdefault(key, {'reached': 0, 'started': 0, 'onboarded': 0})

        for row in rows:
            status = row[status_idx].strip() if status_idx < len(row) else ''
            if not status:
                no_status += 1
                continue
            touch_base += 1
            r = rank(status)
            if status == 'De-listed':
                delisted += 1
            if r >= reached_bar:
                reached += 1
            if r >= started_bar:
                ob_opened += 1
            if status == 'OB Form Filled':
                ob_filled += 1

            # Enhanced contributes only the "reached" movement; started &
            # onboarded movement come from Superset below (the accurate,
            # deduped system of record). REAL status-change history first:
            # every logged transition to 'Meeting done'-or-beyond counts on
            # ITS OWN day (a business reached on the 1st, 3rd and 5th shows on
            # all three); rows with no tracked history fall back to
            # current-status-at-"Updated Date".
            def add_movement(wd, field):
                day_key = wd.isoformat()
                week_key = (wd - timedelta(days=wd.weekday())).isoformat()  # Monday of that week
                month_key = wd.strftime('%Y-%m')
                for store, key in ((dod, day_key), (wow, week_key), (mom, month_key)):
                    bucket(store, key)[field] += 1

            def add_reached(wd):
                add_movement(wd, 'reached')

            notes = row[notes_idx] if notes_idx < len(row) else ''
            real_events = self._parse_horeca_status_changes(notes) if notes else []
            if real_events:
                for ev in real_events:
                    if rank(ev['to_status']) >= reached_bar:
                        ev_wd = parse_work_date(ev['date'])
                        if ev_wd is not None:
                            add_reached(ev_wd)
                continue

            wd = parse_work_date(row[updated_date_idx]) if updated_date_idx is not None and updated_date_idx < len(row) else None
            if wd is None:
                continue
            if r >= reached_bar:
                add_reached(wd)

        # ONBOARDED (headline) = ACTIVE businesses in the Superset_v1 tab â€” a
        # direct, daily-refreshed Superset dump that is the system of record
        # for confirmed onboardings. Each ACTIVE business is dated by its
        # 'updated_day' (the onboarding date) so the weekly & monthly buckets
        # are driven straight off Superset_v1; 'created_day' drives the
        # 'started onboarding' movement. (PAN/GST/FSSAI still come from the
        # separate 'Superset' tab, used only for identity matching.)
        superset_active = 0
        try:
            sup_rows, sup_headers = self._get_superset_v1_cache()
            shx = {hd: i for i, hd in enumerate(sup_headers)}

            def sup(row, col):
                i = shx.get(col)
                return row[i].strip() if i is not None and i < len(row) else ''

            def sup_onboard_date(row):
                # Onboarding date = updated_day (fallback created_day / Date).
                return parse_work_date(
                    sup(row, 'updated_day') or sup(row, 'created_day') or sup(row, 'Date'))

            for srow in sup_rows:
                # 'started onboarding' movement â€” created_day if present.
                created = parse_work_date(sup(srow, 'created_day')) or parse_work_date(sup(srow, 'Date'))
                if created:
                    dk, wk, mk = created.isoformat(), (created - timedelta(days=created.weekday())).isoformat(), created.strftime('%Y-%m')
                    for store, key in ((dod, dk), (wow, wk), (mom, mk)):
                        bucket(store, key)['started'] += 1
                if sup(srow, 'status').upper() == 'ACTIVE':
                    superset_active += 1
                    # Date each onboarded business by its Superset onboarding date
                    d = sup_onboard_date(srow)
                    if d is None:
                        undated_onboarded += 1
                        continue
                    if first_onboard_date is None or d < first_onboard_date:
                        first_onboard_date = d
                    dk, wk, mk = d.isoformat(), (d - timedelta(days=d.weekday())).isoformat(), d.strftime('%Y-%m')
                    for store, key in ((dod, dk), (wow, wk), (mom, mk)):
                        bucket(store, key)['onboarded'] += 1
        except Exception:
            pass

        # app_sheet OB-Filled kept only as a secondary "reported by associates"
        # reference figure â€” no longer the headline or the bucket driver.
        try:
            onboarded_reported = len(self._get_appsheet_onboarded())
        except Exception:
            onboarded_reported = 0

        onboarded_real = superset_active              # headline = Superset ACTIVE
        superset_confirmed = superset_active          # same figure (kept for compat)

        # Keep the funnel monotonic. Onboarded comes from Superset (the system
        # of record), while reached / OB-opened / OB-filled / touch_base come
        # from Enhanced statuses â€” which associates DON'T always update (they
        # work app_sheet/Superset), so the upstream stages under-count and can
        # fall below onboarded. But every onboarded business logically passed
        # through each earlier stage, so floor each stage at the one below it:
        # touch_base >= reached >= ob_opened >= ob_filled >= onboarded.
        ob_filled = max(ob_filled, onboarded_real)
        ob_opened = max(ob_opened, ob_filled)
        reached = max(reached, ob_opened)
        touch_base = max(touch_base, reached)

        # Run rate: total onboarded Ã· days since onboarding first began.
        # first_onboard_date comes from the earliest "Updated Date" among
        # OB-Filled rows; days_active is inclusive of today.
        if first_onboard_date:
            days_active = max(1, (today - first_onboard_date).days + 1)
        else:
            days_active = None
        daily_rate = round(onboarded_real / days_active, 2) if days_active else 0
        remaining = max(0, target - onboarded_real)
        days_to_target = round(remaining / daily_rate) if daily_rate > 0 else None

        def rowify(store):
            # conv_touch_base / conv_overall are CUMULATIVE: total onboarded
            # up to and including that period, over the fixed denominators â€”
            # so the columns read as "where we stood as of that day/month",
            # not just that period's isolated contribution.
            out = []
            cumulative = 0
            for key in sorted(store.keys()):  # oldest first for the running total
                b = store[key]
                cumulative += b['onboarded']
                # Per-period funnel must stay monotonic too: an onboarded
                # business was necessarily reached in that same period, so
                # floor reached at onboarded (reached is sourced from Enhanced
                # statuses, which under-count vs Superset onboardings).
                period_reached = max(b['reached'], b['onboarded'])
                out.append({
                    'period': key,
                    'reached': period_reached,
                    'started': b['started'],
                    'onboarded': b['onboarded'],
                    'cumulative_onboarded': cumulative,
                    'conv_day': round(b['onboarded'] / period_reached * 100, 1) if period_reached else 0,
                    'conv_touch_base': round(cumulative / touch_base * 100, 2) if touch_base else 0,
                    'conv_overall': round(cumulative / total_db * 100, 2) if total_db else 0,
                })
            out.reverse()  # newest first for display
            return out

        return {
            'total_database': total_db,
            'no_status': no_status,
            'delisted': delisted,
            'reached': reached,
            'ob_opened': ob_opened,
            'ob_filled': ob_filled,
            'onboarded_real': onboarded_real,
            'superset_confirmed': superset_confirmed,
            'onboarded_reported': onboarded_reported,
            'touch_base': touch_base,
            'conversion_vs_touch_base': round(onboarded_real / touch_base * 100, 1) if touch_base else 0,
            'conversion_vs_overall': round(onboarded_real / total_db * 100, 1) if total_db else 0,
            'run_rate': {
                'daily_rate': daily_rate,
                'days_active': days_active,
                'first_onboard_date': first_onboard_date.isoformat() if first_onboard_date else None,
                'target': target,
                'remaining': remaining,
                'days_to_target': days_to_target,
            },
            'undated_onboarded': undated_onboarded,
            'totals': {k: (lambda s: {
                'reached': sum(b['reached'] for b in s.values()),
                'started': sum(b['started'] for b in s.values()),
                'onboarded': sum(b['onboarded'] for b in s.values()),
                'conv': round(
                    sum(b['onboarded'] for b in s.values())
                    / max(1, sum(b['reached'] for b in s.values())) * 100, 1),
            })(store) for k, store in (('dod', dod), ('wow', wow), ('mom', mom))},
            'dod': rowify(dod),
            'wow': rowify(wow),
            'mom': rowify(mom),
        }

    def build_horeca_digest(self, for_date_str=None):
        """Personal, letter-style HoReCa ONBOARDING update â€” written in the
        first person, with a couple of inline line graphs (daily + weekly
        onboarding trend) and a simple monthly table. Onboarding only.
        Read-only. Returns (subject, html_body, inline_images) where
        inline_images is {content_id: png_bytes} for cid: <img> references."""
        def esc(v):
            return (str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

        def n(v):
            try:
                return f"{int(round(float(v))):,}"
            except (ValueError, TypeError):
                return esc(v)

        INK = "#1a1a1a"
        MUTED = "#555555"
        LINE = "#dddddd"
        TEAL = "#1e6b5c"
        FONT = "Arial,Helvetica,sans-serif"

        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        today_d = ist_now.date()
        yesterday_d = today_d - timedelta(days=1)
        is_monday = today_d.weekday() == 0

        ov = self.get_horeca_overview() or {}
        dod = ov.get('dod') or []
        wow = ov.get('wow') or []
        mom = ov.get('mom') or []
        rr = ov.get('run_rate') or {}
        total_onb = ov.get('onboarded_real')
        images = {}

        def parse_d(s):
            try:
                return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return None

        def find(rows, period):
            return next((r for r in rows if str(r.get('period')) == str(period)), None)

        def onb(r):
            try:
                return int(round(float(r.get('onboarded') or 0)))
            except (ValueError, TypeError):
                return 0

        # ---------- inline line-graph (PIL -> PNG bytes, referenced via cid:) ----------
        def line_png(rows, label_fn, cid, limit=None, oldest_first=True):
            try:
                from PIL import Image, ImageDraw, ImageFont
            except Exception:
                return None
            data = list(rows)[:limit] if limit else list(rows)
            if oldest_first:
                data = list(reversed(data))
            vals = [onb(r) for r in data]
            if len(vals) < 2:
                return None

            def load_font(sz):
                for p in ('DejaVuSans.ttf',
                          '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                          'C:\\Windows\\Fonts\\arial.ttf'):
                    try:
                        return ImageFont.truetype(p, sz)
                    except Exception:
                        continue
                return ImageFont.load_default()

            S = 2  # supersample for crisp anti-aliasing
            BASE_W, BASE_H = 920, 300
            W, H = BASE_W * S, BASE_H * S
            ml, mr, mt, mb = 48 * S, 20 * S, 30 * S, 40 * S  # extra top room for value labels
            img = Image.new('RGB', (W, H), '#ffffff')
            d = ImageDraw.Draw(img)
            f_sm = load_font(12 * S)
            f_val = load_font(13 * S)
            def load_bold(sz):
                for p in ('DejaVuSans-Bold.ttf',
                          '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                          'C:\\Windows\\Fonts\\arialbd.ttf'):
                    try:
                        return ImageFont.truetype(p, sz)
                    except Exception:
                        continue
                return f_val
            f_val_b = load_bold(13 * S)
            plot_w = W - ml - mr
            plot_h = H - mt - mb
            vmax = max(vals) or 1
            # gridlines + y labels (0, mid, max)
            for frac in (0.0, 0.5, 1.0):
                y = mt + plot_h - frac * plot_h
                d.line([(ml, y), (W - mr, y)], fill='#eeeeee', width=1 * S)
                lbl = n(round(vmax * frac))
                d.text((ml - 8 * S, y), lbl, font=f_sm, fill='#999999', anchor='rm')
            # points
            def xy(i, v):
                x = ml + (plot_w * (i / (len(vals) - 1)))
                y = mt + plot_h - (plot_h * (v / vmax))
                return (x, y)
            pts = [xy(i, v) for i, v in enumerate(vals)]
            d.line(pts, fill=TEAL, width=3 * S, joint='curve')
            for (x, y), v in zip(pts, vals):
                r = 4 * S
                d.ellipse([x - r, y - r, x + r, y + r], fill=TEAL,
                          outline='#ffffff', width=2 * S)
                # value label: bold dark text with a white halo so it stays
                # readable over the line/gridlines. Flip below the marker when
                # the point sits near the top so the label never clips.
                near_top = (y - mt) < 22 * S
                ly = (y + 11 * S) if near_top else (y - 10 * S)
                anchor = 'mt' if near_top else 'mb'
                try:
                    d.text((x, ly), n(v), font=f_val_b, fill=INK, anchor=anchor,
                           stroke_width=3 * S, stroke_fill='#ffffff')
                except TypeError:
                    # very old Pillow without stroke support: manual halo
                    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                        d.text((x + dx * S, ly + dy * S), n(v), font=f_val_b,
                               fill='#ffffff', anchor=anchor)
                    d.text((x, ly), n(v), font=f_val_b, fill=INK, anchor=anchor)
            # x labels: show all if few, else thin out to avoid overlap
            step = 1 if len(data) <= 16 else 2
            for i in range(0, len(data), step):
                x, _ = pts[i]
                d.text((x, H - mb + 8 * S), esc(label_fn(data[i])),
                       font=f_sm, fill='#777777', anchor='ma')
            img = img.resize((BASE_W, BASE_H), Image.LANCZOS)
            import io as _io
            buf = _io.BytesIO()
            img.save(buf, format='PNG')
            images[cid] = buf.getvalue()
            return (f'<div style="text-align:center;margin:8px 0 0;">'
                    f'<img src="cid:{cid}" width="{BASE_W}" '
                    f'style="display:inline-block;width:100%;max-width:{BASE_W}px;height:auto;'
                    f'border:1px solid {LINE};border-radius:6px;" alt="onboarding trend"/></div>')

        def wk_lbl(r):
            d = parse_d(r.get('period'))
            return d.strftime('%d %b') if d else str(r.get('period'))

        def mo_lbl(r):
            try:
                return datetime.strptime(str(r.get('period')), '%Y-%m').strftime('%b %y')
            except (ValueError, TypeError):
                return str(r.get('period'))

        def day_lbl(r):
            d = parse_d(r.get('period'))
            return d.strftime('%d %b') if d else str(r.get('period'))

        # ---------- first-person intro ----------
        if is_monday:
            lw_mon = (today_d - timedelta(days=7))
            lw_mon = lw_mon - timedelta(days=lw_mon.weekday())
            lw = find(wow, lw_mon.isoformat())
            span = f"{lw_mon.strftime('%d %b')}â€“{(lw_mon + timedelta(days=6)).strftime('%d %b')}"
            if lw and onb(lw):
                lead = (f"Sharing where we landed on HoReCa onboarding last week ({span}) â€” "
                        f"we brought on <b>{n(onb(lw))}</b> businesses.")
            else:
                lead = f"Sharing our HoReCa onboarding numbers for last week ({span})."
        else:
            y = find(dod, yesterday_d.isoformat())
            if y and onb(y):
                lead = (f"Quick HoReCa onboarding update â€” we added "
                        f"<b>{n(onb(y))}</b> businesses yesterday ({yesterday_d.strftime('%d %b')}).")
            else:
                lead = f"Quick HoReCa onboarding update for {yesterday_d.strftime('%d %b')}."

        if len(wow) >= 2:
            tw, lw2 = onb(wow[0]), onb(wow[1])
            if lw2:
                arrow = "up" if tw > lw2 else ("down" if tw < lw2 else "about the same")
                lead += (f" We're at <b>{n(tw)}</b> so far this week "
                         f"({arrow} vs {n(lw2)} the week before).")

        pace_line = ""
        target, remaining, pace = rr.get('target'), rr.get('remaining'), rr.get('daily_rate')
        if total_onb is not None and target:
            bits = [f"Overall we've onboarded <b>{n(total_onb)}</b> of {n(target)}"]
            if remaining is not None:
                bits.append(f"{n(remaining)} to go")
            if pace:
                try:
                    bits.append(f"running about {float(pace):.0f} a day")
                except (ValueError, TypeError):
                    pass
            pace_line = ", ".join(bits) + "."

        def heading(text):
            return (f'<p style="font-family:{FONT};font-size:15px;font-weight:bold;color:{INK};'
                    f'margin:26px 0 2px;">{esc(text)}</p>')

        def para(html_text, color=INK, size=14, mt=14):
            return (f'<p style="font-family:{FONT};font-size:{size}px;line-height:1.6;'
                    f'color:{color};margin:{mt}px 0 0;">{html_text}</p>')

        # charts (fallback to a tiny note if PIL/data unavailable)
        daily_chart = line_png(dod, day_lbl, 'chart_daily', limit=14) or \
            para("(Daily trend unavailable.)", color=MUTED, mt=6)
        weekly_chart = line_png(wow, wk_lbl, 'chart_weekly') or \
            para("(Weekly trend unavailable.)", color=MUTED, mt=6)

        # monthly stays a small text table
        def month_table(rows):
            if not rows:
                return para("No monthly data yet.", color=MUTED, mt=6)
            trs = ''
            for r in reversed(list(rows)):
                trs += (
                    f'<tr>'
                    f'<td style="font-family:{FONT};font-size:14px;color:{INK};padding:5px 0;'
                    f'border-bottom:1px solid {LINE};">{esc(mo_lbl(r))}</td>'
                    f'<td style="font-family:{FONT};font-size:14px;color:{INK};padding:5px 0;'
                    f'border-bottom:1px solid {LINE};text-align:right;font-weight:bold;">{n(onb(r))}</td>'
                    f'</tr>')
            return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="300" '
                    f'style="width:300px;max-width:100%;border-collapse:collapse;margin:6px 0 0;">'
                    f'<tr><td style="font-family:{FONT};font-size:12px;color:{MUTED};padding:0 0 4px;'
                    f'border-bottom:2px solid {LINE};">Month</td>'
                    f'<td style="font-family:{FONT};font-size:12px;color:{MUTED};padding:0 0 4px;'
                    f'border-bottom:2px solid {LINE};text-align:right;">Onboarded</td></tr>{trs}</table>')

        # ---------- today's meetings (only if any) ----------
        meetings_html = ''
        try:
            all_mtgs = self.get_meeting_assignments_data() or []
        except Exception:
            all_mtgs = []
        todays = []
        for m in all_mtgs:
            if not isinstance(m, dict):
                continue
            if str(m.get('status') or '').lower() in ('cancelled', 'completed'):
                continue
            if str(m.get('eventDate') or '')[:10] == today_d.isoformat():
                todays.append(m)
        if todays:
            todays.sort(key=lambda x: str(x.get('eventTime') or ''))
            items = ''
            for m in todays:
                is_hor = str(m.get('vpCode') or '').upper().startswith('HORECA')
                who = m.get('vpName') or str(m.get('vpCode') or '').replace('HORECA:', '') or 'â€”'
                typ = m.get('eventTitle') or m.get('eventType') or 'Meeting'
                owner = m.get('assignedTo') or 'â€”'
                tm = m.get('eventTime') or ''
                items += (
                    f'<li style="font-family:{FONT};font-size:14px;line-height:1.6;color:{INK};margin:2px 0;">'
                    f'{esc(tm + " â€” " if tm else "")}<b>{esc(who)}</b> ({esc(typ)}), '
                    f'{"HoReCa" if is_hor else "VP"} Â· owner {esc(owner)}</li>')
            meetings_html = (heading("A few meetings on today")
                             + f'<ul style="margin:4px 0 0;padding-left:20px;">{items}</ul>')

        # ---------- assemble (personal letter) ----------
        body = (
            f'<p style="font-family:{FONT};font-size:15px;color:{INK};margin:0;">Hi Team,</p>'
            + para(lead)
            + heading("Daily onboarding â€” last 2 weeks")
            + daily_chart
            + heading("Weekly onboarding")
            + weekly_chart
            + heading("Monthly onboarding")
            + month_table(mom)
            + meetings_html
            + para("Keep it going ðŸ’ª", mt=22)
            + para("Best,<br>Ashwin", color=INK, mt=18)
        )

        html = (f'<div style="background:#ffffff;padding:24px 26px;width:100%;'
                f'max-width:960px;margin:0;text-align:left;box-sizing:border-box;">{body}</div>')
        subject = f"RAVISHING Â· HoReCa Onboarding Update Â· {today_d.strftime('%A, %d %b %Y')}"
        return subject, html, images

    def build_rvm_digest(self, for_date_str=None):
        """Personal, letter-style RVM DEPLOYMENT update. RVM data has no
        install dates, so instead of a time trend this shows the deployment
        funnel and block-wise deployed counts as horizontal bar charts.
        Read-only. Returns (subject, html_body, inline_images)."""
        def esc(v):
            return (str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

        def n(v):
            try:
                return f"{int(round(float(v))):,}"
            except (ValueError, TypeError):
                return esc(v)

        INK = "#1a1a1a"
        MUTED = "#555555"
        LINE = "#dddddd"
        TEAL = "#1e6b5c"
        FONT = "Arial,Helvetica,sans-serif"

        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        today_d = ist_now.date()
        images = {}

        # ---------- pull + aggregate ----------
        locs = self.get_deployment_data() or []
        try:
            plan_total = self.get_planned_rvms_total() or 0
        except Exception:
            plan_total = 0

        def done(k, vals=('Yes', 'Done')):
            return sum(1 for l in locs if str(l.get(k, '')).strip() in vals)

        total_loc = len(locs)
        noc = done('nocReceived')
        agr = done('agreementSigned')
        shed = done('shedStatus')
        delivered = done('rvmDelivery')
        deployed = done('rvmDeployed')
        electrical = done('electricalDone')
        internet = done('internetStatus')
        live = done('machineLive')

        from collections import Counter
        by_block = Counter(l.get('block', '') or 'â€”'
                           for l in locs if str(l.get('rvmDeployed', '')).strip() in ('Yes', 'Done'))

        # ---------- horizontal bar chart (PNG via PIL, referenced by cid:) ----------
        def hbar_png(pairs, cid, ref=None):
            try:
                from PIL import Image, ImageDraw, ImageFont
            except Exception:
                return None
            pairs = [(str(a), int(b)) for a, b in pairs]
            if not pairs:
                return None

            def load_font(sz):
                for p in ('DejaVuSans.ttf',
                          '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                          'C:\\Windows\\Fonts\\arial.ttf'):
                    try:
                        return ImageFont.truetype(p, sz)
                    except Exception:
                        continue
                return ImageFont.load_default()

            S = 2
            row_h = 34
            BASE_W = 920
            BASE_H = 24 + row_h * len(pairs) + 12
            W, H = BASE_W * S, BASE_H * S
            lblw = 190 * S            # left label column
            valw = 70 * S             # right value column
            ml, mr, mt = 12 * S, 12 * S, 12 * S
            img = Image.new('RGB', (W, H), '#ffffff')
            d = ImageDraw.Draw(img)
            f = load_font(13 * S)
            f_b = load_font(13 * S)
            peak = max([v for _, v in pairs] + ([ref] if ref else []) + [1])
            bar_x0 = ml + lblw
            bar_x1 = W - mr - valw
            bar_area = bar_x1 - bar_x0
            for i, (label, val) in enumerate(pairs):
                cy = mt + row_h * S * i + (row_h * S) // 2
                d.text((ml, cy), label, font=f, fill='#333333', anchor='lm')
                bh = 16 * S
                d.rounded_rectangle([bar_x0, cy - bh // 2, bar_x1, cy + bh // 2],
                                    radius=4 * S, fill='#eef2f1')
                w = int(bar_area * (val / peak)) if peak else 0
                if w > 0:
                    d.rounded_rectangle([bar_x0, cy - bh // 2, bar_x0 + w, cy + bh // 2],
                                        radius=4 * S, fill=TEAL)
                d.text((W - mr, cy), n(val), font=f_b, fill=INK, anchor='rm')
            img = img.resize((BASE_W, BASE_H), Image.LANCZOS)
            import io as _io
            buf = _io.BytesIO()
            img.save(buf, format='PNG')
            images[cid] = buf.getvalue()
            return (f'<div style="text-align:center;margin:8px 0 0;">'
                    f'<img src="cid:{cid}" width="{BASE_W}" '
                    f'style="display:inline-block;width:100%;max-width:{BASE_W}px;height:auto;'
                    f'border:1px solid {LINE};border-radius:6px;" alt="rvm chart"/></div>')

        funnel = [
            ("Locations identified", total_loc),
            ("NOC received", noc),
            ("Agreement signed", agr),
            ("Shed ready", shed),
            ("RVM delivered", delivered),
            ("RVM deployed", deployed),
        ]
        funnel_chart = hbar_png(funnel, 'rvm_funnel', ref=plan_total)
        block_pairs = by_block.most_common()
        block_chart = hbar_png(block_pairs, 'rvm_blocks') if block_pairs else None

        def heading(text):
            return (f'<p style="font-family:{FONT};font-size:15px;font-weight:bold;color:{INK};'
                    f'margin:26px 0 2px;">{esc(text)}</p>')

        def para(html_text, color=INK, size=14, mt=14):
            return (f'<p style="font-family:{FONT};font-size:{size}px;line-height:1.6;'
                    f'color:{color};margin:{mt}px 0 0;">{html_text}</p>')

        lead = (f"Quick RVM deployment update â€” we've deployed <b>{n(deployed)}</b> "
                f"machines of {n(plan_total)} planned, across {n(total_loc)} identified "
                f"locations. {n(delivered)} machines are delivered and {n(shed)} sheds are ready.")

        readiness = (f"Still to close: electrical done at {n(electrical)} sites, "
                     f"internet at {n(internet)}, and {n(live)} machines have cleared the "
                     f"final live check so far.")

        body = (
            f'<p style="font-family:{FONT};font-size:15px;color:{INK};margin:0;">Hi Team,</p>'
            + para(lead)
            + heading("Deployment funnel")
            + (funnel_chart or para("(Funnel chart unavailable.)", color=MUTED, mt=6))
            + heading("Deployed by block")
            + (block_chart or para("No machines deployed yet.", color=MUTED, mt=6))
            + heading("Readiness")
            + para(readiness, mt=6)
            + para("Best,<br>Ashwin", color=INK, mt=22)
        )

        html = (f'<div style="background:#ffffff;padding:24px 26px;width:100%;'
                f'max-width:960px;margin:0;text-align:left;box-sizing:border-box;">{body}</div>')
        subject = (f"RAVISHING Â· RVM Deployment Update Â· {today_d.strftime('%A, %d %b %Y')} "
                   f"Â· {n(deployed)} deployed")
        return subject, html, images

    def _collect_horeca_status_events(self):
        """Flat list of every status-reached event across all (collapsed)
        Enhanced businesses: real auto-logged STATUS_CHANGE entries where
        they exist, plus a one-time read-only approximation â€” current
        Outreach_Status dated to Last_Updated â€” for businesses with no real
        tracked history at all (everything from before this feature
        shipped, when Outreach_Status only ever held one value at a time).
        Nothing is written back to the sheet. Shared by the Day-on-Day grid
        and the Associate windowed view so both agree on the same events.
        """
        rows, headers = self._get_horeca_crm_cache()
        rows, _ = self._collapse_horeca_duplicates(rows, headers)
        h = {hdr: i for i, hdr in enumerate(headers)}
        notes_idx = h.get('Outreach_Notes', 61)
        status_idx = h.get('Outreach_Status', 53)
        last_updated_idx = h.get('Last_Updated', 63)
        updated_by_idx = h.get('Updated_By', 64)
        pid_idx = h.get('Place ID', 0)
        name_idx = h.get('Name', 1)

        events = []
        for row in rows:
            pid = row[pid_idx] if pid_idx < len(row) else ''
            name = row[name_idx] if name_idx < len(row) else ''
            notes = row[notes_idx] if notes_idx < len(row) else ''
            real_events = self._parse_horeca_status_changes(notes, pid, name)

            if real_events:
                for ev in real_events:
                    events.append({**ev, 'approximate': False})
                continue

            # No real tracked history â€” approximate from current snapshot.
            status = row[status_idx].strip() if status_idx < len(row) else ''
            last_updated = row[last_updated_idx].strip() if last_updated_idx < len(row) else ''
            if status not in self.HORECA_OUTREACH_STATUSES or not last_updated:
                continue
            enh_dt = self._parse_enhanced_datetime(last_updated)
            if not enh_dt:
                continue
            associate = row[updated_by_idx].strip() if updated_by_idx < len(row) else ''
            events.append({
                'place_id': pid,
                'name': name,
                'date': enh_dt.date().isoformat(),
                'associate': associate,
                'to_status': status,
                'approximate': True,
            })

        return events

    def get_horeca_dod_grid(self, start_date_str, end_date_str):
        """Status x date grid for the Overall Daily dashboard's Day-on-Day
        section: rows are dates in the range, columns are the canonical
        outreach statuses, values are how many businesses reached that
        status on that day (real tracked events, plus a read-only
        approximation for businesses with no tracked history â€” see
        _collect_horeca_status_events)."""
        try:
            start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('start/end must be YYYY-MM-DD')

        date_list = []
        d = start
        while d <= end:
            date_list.append(d.isoformat())
            d += timedelta(days=1)

        grid = {status: {ds: 0 for ds in date_list} for status in self.HORECA_OUTREACH_STATUSES}
        approximate_count = 0

        for ev in self._collect_horeca_status_events():
            if ev['to_status'] in grid and ev['date'] in grid[ev['to_status']]:
                grid[ev['to_status']][ev['date']] += 1
                if ev['approximate']:
                    approximate_count += 1

        return {
            'dates': date_list,
            'statuses': self.HORECA_OUTREACH_STATUSES,
            'grid': grid,
            'approximate_count': approximate_count,
        }

    def get_horeca_associate_events_summary(self, start_date_str, end_date_str):
        """Associate x status counts for the given window, from real
        tracked transitions + the same read-only approximation used by the
        Day-on-Day grid. Only the whitelisted roster is returned; anyone
        else is counted in 'unmapped_count' rather than guessed."""
        try:
            start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('start/end must be YYYY-MM-DD')

        by_associate = {
            email: {s: 0 for s in self.HORECA_OUTREACH_STATUSES}
            for email in self.HORECA_ASSOCIATE_WHITELIST
        }
        unmapped_count = 0

        for ev in self._collect_horeca_status_events():
            try:
                ev_date = datetime.strptime(ev['date'], '%Y-%m-%d').date()
            except ValueError:
                continue
            if not (start <= ev_date <= end):
                continue
            if ev['to_status'] not in self.HORECA_OUTREACH_STATUSES:
                continue
            email = self._resolve_associate_email(ev['associate'])
            if not email:
                unmapped_count += 1
                continue
            by_associate[email][ev['to_status']] += 1

        return {
            'start': start_date_str,
            'end': end_date_str,
            'statuses': self.HORECA_OUTREACH_STATUSES,
            'associates': {
                self._associate_display_name(email): bucket
                for email, bucket in by_associate.items()
            },
            'unmapped_count': unmapped_count,
        }

    def get_horeca_associate_performance(self, granularity='month',
                                         start=None, end=None):
        """Associates tab: reached + onboarded per associate per period.

        Reached  = real (approximate==False) STATUS_CHANGE events whose
                   to_status ranks at or beyond 'Meeting done', attributed
                   via _resolve_associate_email; unresolved -> 'Other'.
        Onboarded = Superset ACTIVE rows (post-QA classification), dated by
                   updated_day, attributed via the matched our-side record:
                   app_sheet Lead POC email first, else Enhanced Assigned_To
                   (both resolved through the whitelist/aliases);
                   unresolved -> 'Other'.
        Read-only; nothing is written to any sheet."""
        if granularity not in ('day', 'week', 'month'):
            raise ValueError("granularity must be 'day', 'week' or 'month'")

        def parse_d(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(str(s).strip()[:10]).date()
            except ValueError:
                return None

        start_d, end_d = parse_d(start), parse_d(end)

        def period_key(d):
            if granularity == 'day':
                return d.isoformat()
            if granularity == 'week':
                return (d - timedelta(days=d.weekday())).isoformat()
            return d.strftime('%Y-%m')

        wl = set(self.HORECA_ASSOCIATE_WHITELIST)

        def resolve(raw):
            if not raw:
                return None
            r = raw.strip().lower()
            if r in wl:
                return r
            return self._resolve_associate_email(raw)

        order = self.HORECA_OUTREACH_STATUSES
        reached_bar = order.index('Meeting done')

        def rank(status):
            try:
                return order.index(status)
            except ValueError:
                return -1

        data = {}     # period -> email/'Other' -> {'reached','onboarded'}
        alltime = {}  # email/'Other' -> {'reached','onboarded'}

        def bump(d, raw_email, field):
            if start_d and d < start_d:
                return
            if end_d and d > end_d:
                return
            email = raw_email or 'Other'
            p = period_key(d)
            data.setdefault(p, {}).setdefault(
                email, {'reached': 0, 'onboarded': 0})[field] += 1
            alltime.setdefault(email, {'reached': 0, 'onboarded': 0})[field] += 1

        # --- Reached: real tracked events preferred; if the sheet has NO
        # real STATUS_CHANGE history at all yet (verified live 2026-07:
        # zero real events), fall back to the approximate events (current
        # status @ Last_Updated) â€” same fallback the Overview uses.
        all_events = self._collect_horeca_status_events()
        real_events = [e for e in all_events if not e.get('approximate')]
        reached_source = 'real'
        events = real_events
        if not real_events:
            events = all_events
            reached_source = 'approximate_fallback'
        for ev in events:
            if rank(ev.get('to_status', '')) < reached_bar:
                continue
            d = parse_d(ev.get('date'))
            if d is None:
                continue
            bump(d, resolve(ev.get('associate')), 'reached')

        # --- Onboarded: Superset ACTIVE via classification ---
        active_items = []
        try:
            validation = self.get_horeca_superset_validation() or {}
            cls = validation.get('classification') or {}
            active_items = (cls.get('organic') or []) + (cls.get('inorganic') or [])
        except Exception:
            pass

        # Attribution maps
        app_poc_by_id = {}
        try:
            app_rows, app_headers = self._get_appsheet_cache()
            ah = {hdr: i for i, hdr in enumerate(app_headers)}
            aid_i, apoc_i = ah.get('ID'), ah.get('Lead POC')
            for arow in app_rows:
                aid = arow[aid_i].strip() if aid_i is not None and aid_i < len(arow) else ''
                poc = arow[apoc_i].strip() if apoc_i is not None and apoc_i < len(arow) else ''
                if aid and poc:
                    app_poc_by_id[aid] = poc
        except Exception:
            pass

        assigned_by_key = {}  # ('A'|'P'|'G'|'F', id) -> Assigned_To
        try:
            enh_rows, enh_headers = self._get_horeca_crm_cache()
            eh = {hdr: i for i, hdr in enumerate(enh_headers)}

            def ev_(row, col, dflt=None):
                i = eh.get(col, dflt)
                return row[i].strip() if i is not None and i < len(row) else ''

            for erow in enh_rows:
                assignee = ev_(erow, 'Assigned_To', 65)
                if not assignee:
                    continue
                for tag, v in (('A', ev_(erow, 'AppSheet_Lead_ID')),
                               ('P', ev_(erow, 'PAN_Number').upper()),
                               ('G', ev_(erow, 'GST_Number').upper()),
                               ('F', ev_(erow, 'FSSAI_Number'))):
                    if v:
                        assigned_by_key.setdefault((tag, v), assignee)
        except Exception:
            pass

        for it in active_items:
            d = parse_d(it.get('onboarded_date'))
            if d is None:
                continue
            appid = (it.get('appsheet_id') or '').strip()
            email = resolve(app_poc_by_id.get(appid)) if appid else None
            if not email:
                for tag, field in (('A', 'appsheet_id'), ('P', 'pan'),
                                   ('G', 'gst'), ('F', 'fssai')):
                    v = (it.get(field) or '').strip()
                    if v and (tag, v) in assigned_by_key:
                        email = resolve(assigned_by_key[(tag, v)])
                        if email:
                            break
            bump(d, email, 'onboarded')

        # --- Shape the response ---
        display = {email: self._associate_display_name(email)
                   for email in self.HORECA_ASSOCIATE_WHITELIST}
        associates = [display[e] for e in self.HORECA_ASSOCIATE_WHITELIST] + ['Other']

        def _floor(cell):
            # An onboarded business was necessarily reached by that associate,
            # so keep reached >= onboarded (reached is sourced from Enhanced
            # STATUS_CHANGE events, which under-count vs Superset onboardings).
            reached = max(cell.get('reached', 0), cell.get('onboarded', 0))
            return {'reached': reached, 'onboarded': cell.get('onboarded', 0)}

        def named(bucket):
            out = {}
            for email in self.HORECA_ASSOCIATE_WHITELIST:
                out[display[email]] = _floor(bucket.get(email, {'reached': 0, 'onboarded': 0}))
            out['Other'] = _floor(bucket.get('Other', {'reached': 0, 'onboarded': 0}))
            return out

        matrix = []
        for p in sorted(data.keys(), reverse=True):
            per = named(data[p])
            matrix.append({
                'period': p,
                'associates': per,
                'totals': {
                    'reached': sum(v['reached'] for v in per.values()),
                    'onboarded': sum(v['onboarded'] for v in per.values()),
                },
            })

        summary = []
        for name, v in named(alltime).items():
            conv = round(v['onboarded'] / v['reached'] * 100, 1) if v['reached'] else 0
            summary.append({'name': name, 'reached': v['reached'],
                            'onboarded': v['onboarded'], 'conversion': conv})
        summary.sort(key=lambda s: (-s['onboarded'], -s['reached']))

        return {
            'granularity': granularity,
            'reached_source': reached_source,
            'start': start_d.isoformat() if start_d else None,
            'end': end_d.isoformat() if end_d else None,
            'periods': sorted(data.keys(), reverse=True),
            'associates': associates,
            'matrix': matrix,
            'summary': summary,
        }

    # ==================== HoReCa app_sheet -> Enhanced sync (preview only) ====================
    # app_sheet is the tab the field team actively updates (confirmed live â€”
    # real recent dates, real associate emails); the web CRM only ever reads
    # "Enhanced". The two tabs share no ID (Enhanced uses Google Place IDs,
    # app_sheet uses its own short lead code), so matching is done by
    # normalized name + geo-distance on app_sheet's own "Location" column
    # (lat,lng as a single string) against Enhanced's Latitude/Longitude â€”
    # validated against live data at ~97% clean unambiguous match rate.
    APPSHEET_TAB_NAME = 'app_sheet'
    APPSHEET_GEO_THRESHOLD_M = 500

    # Best-effort mapping from app_sheet's free-text "Lead Stage" values onto
    # Enhanced's canonical Outreach_Status vocabulary. Only high-confidence,
    # high-volume mappings are included â€” anything else is left unmapped and
    # surfaced as "needs review" rather than guessed, since a wrong status
    # write is worse than no write.
    APPSHEET_STATUS_MAP = {
        'ob form filled': 'OB Form Filled',
        'lead created': '',
        'meeting scheduled': 'Meeting aligned',
        'meeting completed': 'Meeting done',
        'meeting done': 'Meeting done',
        'no response': 'Call not answered',
    }

    @classmethod
    def _status_rank(cls, status):
        """Position of a status in the outreach funnel (0=earliest). None if
        blank/unrecognized â€” callers must treat None as "unknown", not 0."""
        if not status:
            return None
        try:
            return cls.HORECA_OUTREACH_STATUSES.index(status)
        except ValueError:
            return None

    def _get_appsheet_cache(self):
        """Get or initialize the app_sheet cache (separate tab, same spreadsheet)."""
        global _appsheet_cache
        now = datetime.now()
        if (_appsheet_cache['data'] is not None
                and _appsheet_cache['expiry']
                and now < _appsheet_cache['expiry']):
            return _appsheet_cache['data'], _appsheet_cache['headers']

        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        worksheet = spreadsheet.worksheet(self.APPSHEET_TAB_NAME)
        all_values = _gs_retry(worksheet.get_all_values)

        if len(all_values) < 2:
            _appsheet_cache['data'] = []
            _appsheet_cache['headers'] = []
            _appsheet_cache['expiry'] = now + _HORECA_CACHE_TTL
            return [], []

        headers = all_values[0]
        rows = all_values[1:]
        _appsheet_cache['data'] = rows
        _appsheet_cache['headers'] = headers
        _appsheet_cache['expiry'] = now + _HORECA_CACHE_TTL
        return rows, headers

    SUPERSET_TAB_NAME = 'Superset'

    # Test/dummy businesses to exclude from ALL Superset-derived numbers
    # (matches the team's own Superset SQL exclusion regex). Applied at read
    # time so no matter what lands in the Superset tab, these never count.
    SUPERSET_TEST_TERMS = (
        'recykal', 'sample', 'test', 'abhay', 'sandeep malku', 'lettuce eat',
        'leo roar', 'mewo', 'malbar resort', 'bishal sao and associates',
        'rahul', 'moonson family bar and restaurant', 'bay breeze hotels & resort',
        'revanth estates', 'urdki', 'reyckal',
    )

    @classmethod
    def _is_superset_test_row(cls, name):
        n = (name or '').lower()
        return any(term in n for term in cls.SUPERSET_TEST_TERMS)

    def _get_superset_cache(self):
        """Get or initialize the Superset export cache (separate tab, same
        spreadsheet â€” a plain-values import, not formula-driven). Test/dummy
        businesses (SUPERSET_TEST_TERMS) are filtered out here so every
        downstream number excludes them automatically."""
        global _superset_cache
        now = datetime.now()
        if (_superset_cache['data'] is not None
                and _superset_cache['expiry']
                and now < _superset_cache['expiry']):
            return _superset_cache['data'], _superset_cache['headers']

        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        worksheet = spreadsheet.worksheet(self.SUPERSET_TAB_NAME)
        all_values = _gs_retry(worksheet.get_all_values)

        if len(all_values) < 2:
            _superset_cache['data'] = []
            _superset_cache['headers'] = []
            _superset_cache['expiry'] = now + _HORECA_CACHE_TTL
            return [], []

        # Canonicalize header names â€” the export's schema has changed across
        # versions (pan_number -> PAN, etc.); downstream code always sees the
        # canonical names regardless of which export version is in the tab.
        CANON = {'pan': 'pan_number', 'gst': 'gstin_number', 'fssai': 'fssai_number',
                 'city': 'city', 'region_name': 'region_name'}
        headers = [CANON.get(h.strip().lower(), h.strip()) for h in all_values[0]]
        name_idx = headers.index('business_name') if 'business_name' in headers else 1
        rows = [
            r for r in all_values[1:]
            if not (name_idx < len(r) and self._is_superset_test_row(r[name_idx]))
        ]
        _superset_cache['data'] = rows
        _superset_cache['headers'] = headers
        _superset_cache['expiry'] = now + _HORECA_CACHE_TTL
        return rows, headers

    SUPERSET_V1_TAB_NAME = 'Superset_v1'

    def _get_superset_v1_cache(self):
        """Superset_v1 tab â€” a direct, daily-refreshed Superset dump that is
        the system of record for the ONBOARDED count and onboarding dates
        (columns: business_name, status, created_day, updated_day, ...).
        Row 1 is a 'Last updated: ...' stamp, so the real header row is
        detected (the row carrying 'status'/'business_name') rather than
        assumed to be row 1. Test/dummy businesses are filtered out here.
        PAN/GST/FSSAI still come from the separate 'Superset' tab."""
        global _superset_v1_cache
        now = datetime.now()
        if (_superset_v1_cache['data'] is not None
                and _superset_v1_cache['expiry']
                and now < _superset_v1_cache['expiry']):
            return _superset_v1_cache['data'], _superset_v1_cache['headers']

        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        worksheet = spreadsheet.worksheet(self.SUPERSET_V1_TAB_NAME)
        all_values = _gs_retry(worksheet.get_all_values)

        # Find the header row (skips the leading "Last updated: ..." stamp row).
        hdr_idx = None
        for i, row in enumerate(all_values[:5]):
            low = [c.strip().lower() for c in row]
            if 'status' in low or 'business_name' in low:
                hdr_idx = i
                break
        if hdr_idx is None or len(all_values) <= hdr_idx + 1:
            _superset_v1_cache.update(data=[], headers=[],
                                      expiry=now + _HORECA_CACHE_TTL)
            return [], []

        headers = [h.strip() for h in all_values[hdr_idx]]
        name_idx = headers.index('business_name') if 'business_name' in headers else 1
        rows = [
            r for r in all_values[hdr_idx + 1:]
            if any(c.strip() for c in r)
            and not (name_idx < len(r) and self._is_superset_test_row(r[name_idx]))
        ]
        _superset_v1_cache.update(data=rows, headers=headers,
                                  expiry=now + _HORECA_CACHE_TTL)
        return rows, headers

    EXCISE_TAB_NAME = 'Consumption'

    def get_excise_outlets(self):
        """Excise liquor-outlet geocode data — now living in the 'Consumption' tab
        of the HoReCa CRM workbook itself (moved 2026-07-22 from the standalone
        excise sheet so it sits alongside Enhanced/Superset/app_sheet instead of
        a separate spreadsheet). Same columns as before: OWNER_NAME, SHOP_NAME,
        LOCATION, LIC_TYPE, ADDRESS, MOBILE_NO, LATITUDE, LONGITUDE,
        LOCATION_TYPE, GOOGLE_FORMATTED_ADDRESS.

        The sheet itself carries no onboarding flag, so 'onboarded' is derived
        by name-matching each outlet against Superset ACTIVE businesses (the
        same distinctive-token Jaccard match used by get_horeca_superset_validation),
        using an inverted token index so 8k+ rows match in well under a second."""
        global _excise_cache
        now = datetime.now()
        if (_excise_cache['data'] is not None
                and _excise_cache['expiry']
                and now < _excise_cache['expiry']):
            return _excise_cache['data']

        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        worksheet = spreadsheet.worksheet(self.EXCISE_TAB_NAME)
        all_values = _gs_retry(worksheet.get_all_values)
        if len(all_values) < 2:
            _excise_cache.update(data=[], expiry=now + _HORECA_CACHE_TTL)
            return []

        headers = [h.strip() for h in all_values[0]]
        h = {hd: i for i, hd in enumerate(headers)}

        def g(row, col, default=''):
            i = h.get(col)
            return row[i].strip() if i is not None and i < len(row) else default

        # Onboarded-name pool = Superset ACTIVE businesses (system of record)
        try:
            sup_rows, sup_headers = self._get_superset_v1_cache()
        except Exception:
            sup_rows, sup_headers = [], []
        shx = {hd: i for i, hd in enumerate(sup_headers)}
        name_i = shx.get('business_name')
        status_i = shx.get('status')
        token_index = {}
        pool_names = []
        if name_i is not None and status_i is not None:
            for srow in sup_rows:
                if status_i >= len(srow) or srow[status_i].strip().upper() != 'ACTIVE':
                    continue
                nm = srow[name_i].strip() if name_i < len(srow) else ''
                toks = self._distinctive_name_tokens(nm)
                if len(toks) < 2:
                    continue
                idx = len(pool_names)
                pool_names.append((toks, nm))
                for t in toks:
                    token_index.setdefault(t, []).append(idx)

        def best_match(shop_tokens):
            if len(shop_tokens) < 2 or not token_index:
                return None, 0.0
            counts = {}
            for t in shop_tokens:
                for idx in token_index.get(t, ()):
                    counts[idx] = counts.get(idx, 0) + 1
            best_j, best_nm = 0.0, None
            for idx, shared in counts.items():
                if shared < self.SUPERSET_MIN_SHARED_TOKENS:
                    continue
                toks, nm = pool_names[idx]
                union = len(shop_tokens | toks)
                j = shared / union if union else 0.0
                if j > best_j:
                    best_j, best_nm = j, nm
            return best_nm, best_j

        outlets = []
        for row in all_values[1:]:
            shop_name = g(row, 'SHOP_NAME')
            if not shop_name:
                continue
            try:
                lat_f = float(g(row, 'LATITUDE'))
                lng_f = float(g(row, 'LONGITUDE'))
            except ValueError:
                continue
            toks = self._distinctive_name_tokens(shop_name)
            match_nm, score = best_match(toks)
            onboarded = bool(match_nm) and score >= self.SUPERSET_NAME_SIM_THRESHOLD
            outlets.append({
                'name': shop_name,
                'owner': g(row, 'OWNER_NAME'),
                'block': g(row, 'LOCATION'),
                'address': g(row, 'ADDRESS') or g(row, 'GOOGLE_FORMATTED_ADDRESS'),
                'lic_type': g(row, 'LIC_TYPE'),
                'lat': lat_f,
                'lng': lng_f,
                'onboarded': onboarded,
                'matched_name': match_nm if onboarded else None,
            })

        _excise_cache.update(data=outlets, expiry=now + _HORECA_CACHE_TTL)
        return outlets

    def get_horeca_superset_data(self, search='', page=1, page_size=50):
        """Paginated read of the Superset export tab â€” a raw viewer only,
        no matching against Enhanced/app_sheet yet."""
        rows, headers = self._get_superset_cache()
        if not rows:
            return {'records': [], 'total': 0, 'page': 1, 'total_pages': 0}

        h = {hdr: i for i, hdr in enumerate(headers)}

        def g(row, col):
            i = h.get(col)
            return row[i].strip() if i is not None and i < len(row) else ''

        search_lower = search.lower().strip()
        filtered = rows
        if search_lower:
            name_idx = h.get('business_name')
            filtered = [r for r in rows if name_idx is not None and name_idx < len(r)
                        and search_lower in r[name_idx].lower()]

        total = len(filtered)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(page, 1), total_pages)
        start = (page - 1) * page_size
        page_rows = filtered[start:start + page_size]

        records = [{
            'business_name': g(r, 'business_name'),
            'status': g(r, 'status'),
            'pan_number': g(r, 'pan_number'),
            'gstin_number': g(r, 'gstin_number'),
            'fssai_number': g(r, 'fssai_number'),
            'kind_of_business': g(r, 'kind_of_business'),
            'city': g(r, 'city') or g(r, 'region_name'),
            'street': g(r, 'street'),
            'pin_code': g(r, 'pin_code'),
        } for r in page_rows]

        return {
            'records': records,
            'total': total,
            'page': page,
            'total_pages': total_pages,
        }

    # ==================== Superset <-> Enhanced validation ====================
    # Words that carry no identity in a Goan hospitality business name â€”
    # generic industry terms plus locality/place names. Two unrelated
    # businesses routinely share these, so they must not count as evidence
    # of a match (verified live: "Baga 24 Bar" wrongly matched "De baga
    # deck" on the shared neighbourhood name alone before this list).
    HORECA_NAME_STOPWORDS = frozenset({
        'bar', 'restaurant', 'restaurants', 'cafe', 'kitchen', 'resort', 'resorts',
        'hotel', 'hotels', 'and', 'the', 'by', 'pub', 'lounge', 'grill', 'food',
        'foods', 'family', 'multi', 'cuisine', 'dine', 'dining', 'deck', 'house',
        'garden', 'palace', 'corner', 'view', 'point', 'side', 'beach', 'club',
        'inn', 'bakery', 'bistro', 'shack', 'joint', 'eatery', 'grille', 'grub',
        'goa', 'goan', 'of', 'at', 'in', 'to', 'near', 'opp', 'road', 'wine',
        'shop', 'spot', 'zone', 'hub', 'place', 'stop', 'sea', 'ocean',
        'baga', 'anjuna', 'calangute', 'candolim', 'panaji', 'panjim', 'vagator',
        'arpora', 'assagao', 'siolim', 'mapusa', 'margao', 'madgaon', 'colva',
        'benaulim', 'cavelossim', 'varca', 'majorda', 'betalbatim', 'sinquerim',
        'morjim', 'ashwem', 'mandrem', 'arambol', 'chapora', 'ponda', 'verna',
        'cortalim', 'bicholim', 'bardez', 'salcete', 'tiswadi', 'pernem',
        'canacona', 'quepem', 'sanguem', 'dabolim', 'vasco', 'sangolda',
        'corjuem', 'bambolim', 'mormugaon', 'sancoale', 'upasnagar', 'aldona',
        'saligao', 'porvorim', 'reis', 'magos', 'santa', 'cruz', 'dona', 'paula',
    })
    SUPERSET_NAME_SIM_THRESHOLD = 0.6
    SUPERSET_MIN_SHARED_TOKENS = 2

    @classmethod
    def _distinctive_name_tokens(cls, name):
        s = re.sub(r'[^a-z0-9 ]', ' ', (name or '').lower())
        return frozenset(
            t for t in s.split() if len(t) > 2 and t not in cls.HORECA_NAME_STOPWORDS
        )

    def get_horeca_superset_validation(self):
        """Validate our tracker against the Superset export (the authoritative
        onboarding record: status ACTIVE = onboarded, DRAFT = onboarding
        started but pending).

        Matching, per Superset business, first tier wins:
          exact PAN -> exact GST -> exact FSSAI -> confident name
          (>=2 shared distinctive tokens, Jaccard >= 0.6, same pincode,
          Superset alias-name columns also checked and flagged) -> no match.
        Exact tiers strengthen automatically as PAN/GST/FSSAI populate on
        the Enhanced side (fed by the app_sheet document auto-copy).

        Collisions (two Enhanced rows claiming one Superset row â€” the
        multi-location-brand case) are demoted to needs_review: counted in
        neither matched nor unmatched, listed for human review instead.

        Read-only: computes live from the cached tabs, writes nothing.
        """
        global _superset_validation_cache
        now = datetime.now()
        if _superset_validation_cache['data'] is not None:
            fresh = (_superset_validation_cache['expiry']
                     and now < _superset_validation_cache['expiry'])
            if fresh:
                return _superset_validation_cache['data']
            # Stale-while-revalidate: hand back the previous result instantly
            # and recompute in a background thread, so the Insights tab never
            # blocks the user on a full re-validation.
            if not _superset_validation_cache.get('refreshing'):
                _superset_validation_cache['refreshing'] = True

                def _refresh():
                    try:
                        self._compute_superset_validation()
                    except Exception:
                        pass
                    finally:
                        _superset_validation_cache['refreshing'] = False
                import threading
                threading.Thread(target=_refresh, daemon=True).start()
            return _superset_validation_cache['data']

        return self._compute_superset_validation()

    def _compute_superset_validation(self):
        """The actual validation computation (see get_horeca_superset_validation)."""
        global _superset_validation_cache
        now = datetime.now()

        enh_rows, enh_headers = self._get_horeca_crm_cache()
        enh_rows, _ = self._collapse_horeca_duplicates(enh_rows, enh_headers)
        eh = {hdr: i for i, hdr in enumerate(enh_headers)}

        def eg(row, col, default_idx=None):
            i = eh.get(col, default_idx)
            return row[i].strip() if i is not None and i < len(row) else ''

        sup_rows, sup_headers = self._get_superset_cache()
        sh = {hdr: i for i, hdr in enumerate(sup_headers)}

        def sg(row, col):
            i = sh.get(col)
            return row[i].strip() if i is not None and i < len(row) else ''

        # --- Enhanced-side indexes ---
        enh_by_pan, enh_by_gst, enh_by_fssai = {}, {}, {}
        enh_by_pincode = {}
        for erow in enh_rows:
            pan = eg(erow, 'PAN_Number').upper()
            gst = eg(erow, 'GST_Number').upper()
            fssai = eg(erow, 'FSSAI_Number')
            if pan:
                enh_by_pan.setdefault(pan, erow)
            if gst:
                enh_by_gst.setdefault(gst, erow)
            if fssai:
                enh_by_fssai.setdefault(fssai, erow)
            pin = eg(erow, 'Pincode')
            if pin:
                enh_by_pincode.setdefault(pin, []).append(erow)

        alias_cols = ['other_name_pan', 'other_name_gst_legal', 'other_name_gst_trade', 'other_name_fssai']

        def is_associate_sourced(erow):
            if eg(erow, 'AppSheet_Lead_ID'):
                return True
            if eg(erow, 'Assigned_To', 65):
                return True
            return eg(erow, 'Place ID', 0).startswith('MANUAL_')

        matches = []       # per Superset row: dict or None
        for srow in sup_rows:
            sname = sg(srow, 'business_name')
            if not sname:
                matches.append(None)
                continue
            span = sg(srow, 'pan_number').upper()
            sgst = sg(srow, 'gstin_number').upper()
            sfssai = sg(srow, 'fssai_number')

            erow, method, via, score = None, None, 'primary', 1.0
            if span and span in enh_by_pan:
                erow, method = enh_by_pan[span], 'exact_pan'
            elif sgst and sgst in enh_by_gst:
                erow, method = enh_by_gst[sgst], 'exact_gst'
            elif sfssai and sfssai in enh_by_fssai:
                erow, method = enh_by_fssai[sfssai], 'exact_fssai'
            else:
                pin = sg(srow, 'pin_code')
                candidates = enh_by_pincode.get(pin, []) if pin else []
                cand_names = [(sname, 'primary')] + [
                    (sg(srow, c), 'alias') for c in alias_cols if sg(srow, c)
                ]
                best_score, best_row, best_via = 0.0, None, 'primary'
                for nm, nm_via in cand_names:
                    s_tok = self._distinctive_name_tokens(nm)
                    if len(s_tok) < self.SUPERSET_MIN_SHARED_TOKENS:
                        continue
                    for cand in candidates:
                        c_tok = self._distinctive_name_tokens(cand[eh.get('Name', 1)] if eh.get('Name', 1) < len(cand) else '')
                        shared = len(s_tok & c_tok)
                        union = len(s_tok | c_tok)
                        j = shared / union if union else 0.0
                        if j > best_score and shared >= self.SUPERSET_MIN_SHARED_TOKENS:
                            best_score, best_row, best_via = j, cand, nm_via
                if best_row is not None and best_score >= self.SUPERSET_NAME_SIM_THRESHOLD:
                    erow, method, via, score = best_row, 'name_confident', best_via, best_score

            matches.append(None if erow is None else {
                'erow': erow, 'method': method, 'via': via, 'score': round(score, 2),
            })

        # --- Collision demotion: 2+ Superset rows claiming one Enhanced row,
        # or (equivalently) matches sharing a Place ID â€” only one can be
        # right, so trust none of them automatically.
        pid_claims = {}
        for m in matches:
            if m:
                pid = m['erow'][eh.get('Place ID', 0)]
                pid_claims[pid] = pid_claims.get(pid, 0) + 1
        for m in matches:
            if m and pid_claims[m['erow'][eh.get('Place ID', 0)]] > 1:
                m['method'] = 'needs_review'

        # --- Roll everything up ---
        method_counts = {'exact_pan': 0, 'exact_gst': 0, 'exact_fssai': 0,
                         'name_confident': 0, 'needs_review': 0, 'no_match': 0}
        agree = over_claim = blind_spot = 0
        associate_matched = organic_matched = 0
        over_claims, blind_spots, collisions, organic_candidates = [], [], [], []
        matched_place_ids = set()

        for srow, m in zip(sup_rows, matches):
            sname = sg(srow, 'business_name')
            sstatus = sg(srow, 'status')
            base = {'superset_name': sname, 'superset_status': sstatus,
                    'city': sg(srow, 'city') or sg(srow, 'region_name'),
                    'pin_code': sg(srow, 'pin_code')}
            if m is None:
                method_counts['no_match'] += 1
                organic_candidates.append(base)
                continue
            method_counts[m['method']] += 1
            detail = {**base, 'enhanced_name': eg(m['erow'], 'Name', 1),
                      'place_id': eg(m['erow'], 'Place ID', 0),
                      'our_status': eg(m['erow'], 'Outreach_Status', 53),
                      'method': m['method'], 'via': m['via'], 'score': m['score']}
            if m['method'] == 'needs_review':
                collisions.append(detail)
                continue
            matched_place_ids.add(detail['place_id'])
            if is_associate_sourced(m['erow']):
                associate_matched += 1
            else:
                organic_matched += 1
            ours_claimed = detail['our_status'] == 'OB Form Filled'
            if sstatus == 'ACTIVE' and ours_claimed:
                agree += 1
            elif sstatus != 'ACTIVE' and ours_claimed:
                over_claim += 1
                over_claims.append(detail)
            elif sstatus == 'ACTIVE' and not ours_claimed:
                blind_spot += 1
                blind_spots.append(detail)

        # Our OB-Filled rows with no Superset match at all = over-claims too
        # (we say onboarded; the system of record has never heard of them).
        for erow in enh_rows:
            if eg(erow, 'Outreach_Status', 53) == 'OB Form Filled' \
                    and eg(erow, 'Place ID', 0) not in matched_place_ids:
                over_claims.append({
                    'superset_name': '(no Superset record)', 'superset_status': '-',
                    'enhanced_name': eg(erow, 'Name', 1),
                    'place_id': eg(erow, 'Place ID', 0),
                    'our_status': 'OB Form Filled',
                    'method': 'no_match', 'via': '-', 'score': 0,
                    'city': eg(erow, 'City', 6), 'pin_code': eg(erow, 'Pincode'),
                })

        # Touch base = every business we've connected with in any way
        # (any non-blank status counts, per the user's definition).
        touch_base = sum(1 for r in enh_rows if eg(r, 'Outreach_Status', 53))
        status_counts = {}
        for r in enh_rows:
            st = eg(r, 'Outreach_Status', 53)
            if st:
                status_counts[st] = status_counts.get(st, 0) + 1

        # Onboarded headline (ACTIVE) + in-progress (DRAFT) come from the
        # Superset_v1 tab â€” the daily-refreshed system of record â€” so Insight
        # matches the dashboard. PAN/GST/FSSAI matching above still uses the
        # separate 'Superset' tab (which carries the identity columns).
        try:
            v1_rows, v1_headers = self._get_superset_v1_cache()
            v1_status_i = {hd: i for i, hd in enumerate(v1_headers)}.get('status')

            def _v1st(r):
                return r[v1_status_i].strip().upper() if v1_status_i is not None and v1_status_i < len(r) else ''
            active_total = sum(1 for r in v1_rows if _v1st(r) == 'ACTIVE')
            draft_total = sum(1 for r in v1_rows if _v1st(r) == 'DRAFT')
        except Exception:
            active_total = sum(1 for r in sup_rows if sg(r, 'status') == 'ACTIVE')
            draft_total = sum(1 for r in sup_rows if sg(r, 'status') == 'DRAFT')
        matched_total = associate_matched + organic_matched

        classification = self._classify_superset_rows(
            sup_rows, sg, matches, eh, eg, active_total, draft_total)

        result = {
            'classification': classification,
            'superset_total': len(sup_rows),
            'onboarded_active': active_total,
            'pending_draft': draft_total,
            'touch_base': touch_base,
            'total_database': len(enh_rows),
            'status_counts': status_counts,
            'conversion_vs_touch_base': round(active_total / touch_base * 100, 1) if touch_base else 0,
            'conversion_vs_overall': round(active_total / len(enh_rows) * 100, 1) if enh_rows else 0,
            'matched': matched_total,
            'associate_matched': associate_matched,
            'organic_matched': organic_matched,
            'superset_unmatched': method_counts['no_match'],
            'agree': agree,
            'over_claim_count': len(over_claims),
            'blind_spot_count': blind_spot,
            'needs_review_count': len(collisions),
            'method_counts': method_counts,
            'over_claims': over_claims,
            'blind_spots': blind_spots,
            'collisions': collisions,
            'organic_candidates': organic_candidates,
        }
        _superset_validation_cache['data'] = result
        _superset_validation_cache['expiry'] = now + _HORECA_CACHE_TTL
        return result

    def _classify_superset_rows(self, sup_rows, sg, matches, eh, eg,
                                active_total, draft_total):
        """Classify every Superset business.

        Universe = Superset rows. DRAFT -> onboarding_in_progress.
        Every ACTIVE business is EXACTLY ONE of:
          Inorganic â€” its PAN or GST (normalized upper/strip) exists in the
            associate pool (Enhanced PAN_Number/GST_Number + app_sheet
            Document_Number via _classify_document): captured on BOTH sides.
          Organic â€” everything else.

        QA queues are OVERLAYS â€” a row keeps its organic/inorganic bucket
        AND appears in any queue it qualifies for:
          qa_dup_pan / qa_dup_gst / qa_dup_fssai â€” the ID is shared by 2+
            Superset rows.
          qa_name_both â€” the Superset business_name confidently matches an
            Enhanced or app_sheet name (_distinctive_name_tokens matching).

        Decisions affect counts: a disapproved row is OFFBOARDED â€” dropped
        from organic/inorganic and collected in 'offboarded';
        onboarded_after_qa = ACTIVE - offboarded. Approved rows stay
        counted and leave qa_pending. Read-only; nothing is written back.
        """
        # --- associate ID pool: Enhanced + app_sheet ---
        # Alongside membership, remember OUR side's record per ID:
        # app_sheet ID, business name and status â€” so every row can show
        # the Ravishing record next to the Superset one.
        pool_pan, pool_gst = set(), set()
        our_by_pan, our_by_gst, our_by_fssai = {}, {}, {}
        enh_rows_all, enh_headers_all = self._get_horeca_crm_cache()
        ehp = {hdr: i for i, hdr in enumerate(enh_headers_all)}
        pan_i, gst_i = ehp.get('PAN_Number'), ehp.get('GST_Number')
        fssai_i = ehp.get('FSSAI_Number')
        name_i = ehp.get('Name', 1)
        stat_i = ehp.get('Outreach_Status', 53)
        appid_i = ehp.get('AppSheet_Lead_ID')

        def _ev(erow, i):
            return erow[i].strip() if i is not None and i < len(erow) else ''

        # Name index over Enhanced + app_sheet for the qa_name_both overlay
        name_pool = []  # (tokens, appsheet_id, name, status)

        for erow in enh_rows_all:
            ename = _ev(erow, name_i)
            estat = _ev(erow, stat_i)
            eappid = _ev(erow, appid_i)
            rec = {'appsheet_id': eappid, 'name': ename, 'status': estat}
            p = _ev(erow, pan_i).upper()
            g = _ev(erow, gst_i).upper()
            f = _ev(erow, fssai_i)
            if p:
                pool_pan.add(p)
                our_by_pan.setdefault(p, rec)
            if g:
                pool_gst.add(g)
                our_by_gst.setdefault(g, rec)
            if f:
                our_by_fssai.setdefault(f, rec)
            toks = self._distinctive_name_tokens(ename)
            if len(toks) >= self.SUPERSET_MIN_SHARED_TOKENS:
                name_pool.append((toks, eappid, ename, estat))

        app_rows, app_headers = self._get_appsheet_cache()
        ah = {hdr: i for i, hdr in enumerate(app_headers)}

        def ag(row, col):
            i = ah.get(col)
            return row[i].strip() if i is not None and i < len(row) else ''

        google_leads = new_leads = 0
        new_leads_list = []
        for arow in app_rows:
            # Lead-source KPIs (Google vs everything else non-blank)
            src = ag(arow, 'Lead Source')
            if src:
                if src.strip().lower() == 'google':
                    google_leads += 1
                else:
                    new_leads += 1
                    new_leads_list.append({
                        'appsheet_id': ag(arow, 'ID'),
                        'superset_name': ag(arow, 'HoReCa Name'),
                        'source': src,
                        'matched_status': ag(arow, 'Lead Stage'),
                        'poc': ag(arow, 'Lead POC'),
                        'onboarded_date': ag(arow, 'Last updated Date'),
                        'queue': 'new_lead',
                    })
            aname = ag(arow, 'HoReCa Name')
            arec = {'appsheet_id': ag(arow, 'ID'), 'name': aname,
                    'status': ag(arow, 'Lead Stage')}
            col_name, num = self._classify_document(
                ag(arow, 'Document_Type'), ag(arow, 'Document_Number'))
            if col_name == 'PAN_Number':
                pool_pan.add(num)
                our_by_pan.setdefault(num, arec)
            elif col_name == 'GST_Number':
                pool_gst.add(num)
                our_by_gst.setdefault(num, arec)
            elif col_name == 'FSSAI_Number':
                our_by_fssai.setdefault(num, arec)
            toks = self._distinctive_name_tokens(aname)
            if len(toks) >= self.SUPERSET_MIN_SHARED_TOKENS:
                name_pool.append((toks, arec['appsheet_id'], aname, arec['status']))

        def best_name_match(sname):
            """Confident our-side name match (same thresholds as the
            validation engine): >=2 shared distinctive tokens AND
            Jaccard >= SUPERSET_NAME_SIM_THRESHOLD."""
            s_tok = self._distinctive_name_tokens(sname)
            if len(s_tok) < self.SUPERSET_MIN_SHARED_TOKENS:
                return None
            best, best_j = None, 0.0
            for toks, appid, nm, st in name_pool:
                shared = len(s_tok & toks)
                if shared < self.SUPERSET_MIN_SHARED_TOKENS:
                    continue
                union = len(s_tok | toks)
                j = shared / union if union else 0.0
                if j > best_j:
                    best_j, best = j, {'appsheet_id': appid, 'name': nm, 'status': st}
            if best is not None and best_j >= self.SUPERSET_NAME_SIM_THRESHOLD:
                return best
            return None

        # --- duplicates WITHIN Superset ---
        pan_counts, gst_counts, fssai_counts, name_counts = {}, {}, {}, {}
        for srow in sup_rows:
            p = sg(srow, 'pan_number').upper()
            g = sg(srow, 'gstin_number').upper()
            f = sg(srow, 'fssai_number')
            n = self._normalize_horeca_name(sg(srow, 'business_name'))
            if p:
                pan_counts[p] = pan_counts.get(p, 0) + 1
            if g:
                gst_counts[g] = gst_counts.get(g, 0) + 1
            if f:
                fssai_counts[f] = fssai_counts.get(f, 0) + 1
            if n:
                name_counts[n] = name_counts.get(n, 0) + 1
        dup_pans = {p for p, c in pan_counts.items() if c > 1}
        dup_gsts = {g for g, c in gst_counts.items() if c > 1}
        dup_fssais = {f for f, c in fssai_counts.items() if c > 1}
        dup_names = {n for n, c in name_counts.items() if c > 1}

        decisions = self._read_qa_decisions()

        # --- duplicate names WITHIN Enhanced (Ravishing), restricted to
        # rows already claimed as onboarded (OB Form Filled). Decidable via
        # RNAME:<norm> keys; informational for classification counts. ---
        rav_city_i, rav_pin_i = ehp.get('City'), ehp.get('Pincode')
        rav_upd_i = ehp.get('Updated Date')
        rav_name_counts, rav_candidates = {}, []
        for erow in enh_rows_all:
            if _ev(erow, stat_i) != 'OB Form Filled':
                continue
            nm = _ev(erow, name_i)
            norm = self._normalize_horeca_name(nm)
            if not norm:
                continue
            rav_name_counts[norm] = rav_name_counts.get(norm, 0) + 1
            rav_candidates.append((norm, erow))
        rav_dup_norms = {n for n, c in rav_name_counts.items() if c > 1}
        dup_names_ravishing = []
        for norm, erow in rav_candidates:
            if norm not in rav_dup_norms:
                continue
            key = f'RNAME:{norm}'
            it = {
                'superset_name': _ev(erow, name_i),
                'superset_status': '',
                'appsheet_id': _ev(erow, appid_i),
                'pan': _ev(erow, pan_i).upper(),
                'gst': _ev(erow, gst_i).upper(),
                'fssai': _ev(erow, fssai_i),
                'city': _ev(erow, rav_city_i),
                'pin_code': _ev(erow, rav_pin_i),
                'matched_name': _ev(erow, name_i),
                'matched_status': 'OB Form Filled',
                'onboarded_date': _ev(erow, rav_upd_i),
                'key': key, 'queue': 'dup_name_rav',
            }
            dec = decisions.get(key)
            if dec:
                it['decision'] = dec['decision']
                it['decided_by'] = dec.get('decided_by', '')
            dup_names_ravishing.append(it)

        organic, inorganic = [], []
        qa_name_both, qa_dup_pan, qa_dup_gst, qa_dup_fssai = [], [], [], []
        dup_name_rows, offboarded, in_progress = [], [], []
        pending_doc_update = []  # onboarded yesterday+, PAN/GST/FSSAI not yet refreshed
        docs_not_updated = 0     # ALL ACTIVE businesses with no PAN/GST/FSSAI in Superset yet
        _yesterday = (datetime.now() - timedelta(days=1)).date()

        def _s_onboard_date(srow):
            v = (sg(srow, 'Date') or sg(srow, 'updated_day') or '').strip()[:10]
            try:
                return datetime.fromisoformat(v).date()
            except ValueError:
                return None
        # Unique-undecided tracking (by Superset row id) for the three
        # duplicate-ID queues only â€” name queues are NOT counted (B3).
        pending_ids = {'dup_pan': set(), 'dup_gst': set(), 'dup_fssai': set()}

        for row_idx, (srow, m) in enumerate(zip(sup_rows, matches)):
            sname = sg(srow, 'business_name')
            span = sg(srow, 'pan_number').upper()
            sgst = sg(srow, 'gstin_number').upper()
            sfssai = sg(srow, 'fssai_number')
            sstatus = sg(srow, 'status')
            norm_name = self._normalize_horeca_name(sname)

            # Our-side (Ravishing) record: by ID first, then confident name.
            ours = (our_by_pan.get(span) or our_by_gst.get(sgst)
                    or our_by_fssai.get(sfssai))
            name_hit = None
            if m is not None and m.get('method') in ('name_confident', 'needs_review'):
                erow = m['erow']
                name_hit = {'appsheet_id': eg(erow, 'AppSheet_Lead_ID'),
                            'name': eg(erow, 'Name', 1),
                            'status': eg(erow, 'Outreach_Status', 53)}
            if name_hit is None:
                name_hit = best_name_match(sname)
            if not ours:
                ours = name_hit

            row_id = sg(srow, 'id') or f'row-{row_idx}'

            item = {
                'row_id': row_id,
                'superset_name': sname,
                'superset_status': sstatus,
                'appsheet_id': (ours or {}).get('appsheet_id', '') or '',
                'pan': span, 'gst': sgst, 'fssai': sfssai,
                'city': sg(srow, 'city') or sg(srow, 'region_name'),
                'pin_code': sg(srow, 'pin_code'),
                'matched_name': (ours or {}).get('name', '') or '',
                'matched_status': (ours or {}).get('status', '') or '',
                # Superset updated_day = the onboarding date (team convention)
                'onboarded_date': sg(srow, 'updated_day'),
            }

            # Duplicate business names â€” informational; onboarded-only
            # (Superset ACTIVE), matching dup_names_ravishing's OB-only rule.
            if norm_name and norm_name in dup_names and sstatus == 'ACTIVE':
                dup_name_rows.append({**item, 'queue': 'dup_name',
                                      'key': f'NAME:{norm_name}|{item["pin_code"]}'})

            if sstatus == 'DRAFT':
                in_progress.append(item)
                continue
            if sstatus != 'ACTIVE':
                continue

            # Every queue this row qualifies for (overlays, not tiers)
            queue_keys = []
            if span and span in dup_pans:
                queue_keys.append(('dup_pan', f'PAN:{span}'))
            if sgst and sgst in dup_gsts:
                queue_keys.append(('dup_gst', f'GST:{sgst}'))
            if sfssai and sfssai in dup_fssais:
                queue_keys.append(('dup_fssai', f'FSSAI:{sfssai}'))
            if name_hit is not None:
                queue_keys.append(('name_both', f'NAME:{norm_name}|{item["pin_code"]}'))

            # --- Decision cascade (B2): a decision on ANY identity key of
            # this business (PAN / GST / FSSAI / NAME) propagates to the
            # whole business. ALL its keys participate, not just the ones
            # that landed it in a queue â€” so approving PAN:x decides every
            # row bearing PAN:x, and their GST/FSSAI groups count those
            # rows as decided too. Disapproved beats approved.
            all_keys = []
            if span:
                all_keys.append(('PAN', f'PAN:{span}'))
            if sgst:
                all_keys.append(('GST', f'GST:{sgst}'))
            if sfssai:
                all_keys.append(('FSSAI', f'FSSAI:{sfssai}'))
            if norm_name:
                all_keys.append(('NAME', f'NAME:{norm_name}|{item["pin_code"]}'))

            eff_decision = eff_via = eff_key = eff_by = None
            for want in ('disapproved', 'approved'):
                for ktype, k in all_keys:
                    d = decisions.get(k)
                    if d and d.get('decision') == want:
                        eff_decision, eff_via, eff_key = want, ktype, k
                        eff_by = d.get('decided_by', '')
                        break
                if eff_decision:
                    break

            # Effectively disapproved (directly or via cascade) -> offboarded
            if eff_decision == 'disapproved':
                off_queue = next((q for q, k in queue_keys if k == eff_key),
                                 queue_keys[0][0] if queue_keys else 'cascade')
                offboarded.append({**item, 'queue': off_queue, 'key': eff_key,
                                   'decision': 'disapproved',
                                   'decided_via': f'{eff_via} cascade',
                                   'decided_by': eff_by})
                continue

            # Pending doc update: onboarded yesterday-or-later but with no
            # PAN/GST/FSSAI in the Superset tab yet (the identity refresh lags
            # a day behind onboarding). Park these separately so the lag does
            # not inflate organic â€” they reclassify automatically once the
            # docs land.
            if not (span or sgst or sfssai):
                _d = _s_onboard_date(srow)
                if _d is not None and _d >= _yesterday:
                    pending_doc_update.append({**item, 'queue': 'pending_doc_update'})
                    continue

            # Base bucket: inorganic (ID on both sides) vs organic
            if (span and span in pool_pan) or (sgst and sgst in pool_gst):
                inorganic.append({**item,
                                  'matched_via': 'PAN' if (span and span in pool_pan) else 'GST'})
            else:
                organic.append(item)

            # Queue overlays (row also stays in its bucket above)
            queue_lists = {'dup_pan': qa_dup_pan, 'dup_gst': qa_dup_gst,
                           'dup_fssai': qa_dup_fssai, 'name_both': qa_name_both}
            for queue, key in queue_keys:
                it = {**item, 'key': key, 'queue': queue}
                dec = decisions.get(key)
                if dec:
                    # Direct decision on this exact key
                    it['decision'] = dec['decision']
                    it['decided_by'] = dec.get('decided_by', '')
                    it['decided_via'] = 'direct'
                elif eff_decision:
                    # Cascaded from a sibling key of the same business
                    it['decision'] = eff_decision
                    it['decided_by'] = eff_by
                    it['decided_via'] = f'{eff_via} cascade'
                elif queue in pending_ids:
                    pending_ids[queue].add(row_id)
                queue_lists[queue].append(it)

        def group_stats(lst, field):
            vals = {it[field] for it in lst if it.get(field)}
            return len(vals), len(lst)

        dup_pan_groups, dup_pan_rows = group_stats(qa_dup_pan, 'pan')
        dup_gst_groups, dup_gst_rows = group_stats(qa_dup_gst, 'gst')
        dup_fssai_groups, dup_fssai_rows = group_stats(qa_dup_fssai, 'fssai')

        # qa_pending (B3): UNIQUE undecided businesses (by Superset row id)
        # appearing in at least one duplicate-ID queue, after the cascade.
        qa_pending = len(pending_ids['dup_pan'] | pending_ids['dup_gst']
                         | pending_ids['dup_fssai'])
        qa_pending_breakdown = {q: len(ids) for q, ids in pending_ids.items()}

        # 'PAN/GST/FSSAI not updated in Superset' = businesses that are
        # onboarded (ACTIVE in the daily Superset_v1 tab) but whose identity
        # is not yet present in the 'Superset' matching tab (name has no
        # doc-bearing row there). This is the sheet-refresh lag â€” surfaced so
        # it isn't mistaken for a real matching gap.
        try:
            _sup_names_withdoc = set()
            for r in sup_rows:
                nm = self._normalize_horeca_name(sg(r, 'business_name'))
                if nm and (sg(r, 'pan_number') or sg(r, 'gstin_number') or sg(r, 'fssai_number')):
                    _sup_names_withdoc.add(nm)
            _v1_rows, _v1_headers = self._get_superset_v1_cache()
            _vhx = {h: i for i, h in enumerate(_v1_headers)}
            _vn, _vs = _vhx.get('business_name'), _vhx.get('status')
            docs_not_updated = 0
            for r in _v1_rows:
                st = r[_vs].strip().upper() if _vs is not None and _vs < len(r) else ''
                if st != 'ACTIVE':
                    continue
                nm = self._normalize_horeca_name(r[_vn] if _vn is not None and _vn < len(r) else '')
                if nm and nm not in _sup_names_withdoc:
                    docs_not_updated += 1
        except Exception:
            docs_not_updated = 0

        return {
            'total_onboarded': active_total,
            'onboarded_after_qa': active_total - len(offboarded),
            'offboarded_count': len(offboarded),
            'onboarding_in_progress_count': draft_total,
            'google_leads': google_leads,
            'new_leads': new_leads,
            'organic_count': len(organic),
            'inorganic_count': len(inorganic),
            'pending_doc_update_count': len(pending_doc_update),
            'pending_doc_update': pending_doc_update,
            'docs_not_updated_count': docs_not_updated,
            'qa_pending': qa_pending,
            'qa_pending_breakdown': qa_pending_breakdown,
            'dup_names_ravishing': dup_names_ravishing,
            'new_leads_list': new_leads_list,
            'organic': organic,
            'inorganic': inorganic,
            'qa_name_both': qa_name_both,
            'qa_name_matches': qa_name_both,  # backward-compat alias
            'qa_dup_pan': qa_dup_pan,
            'qa_dup_gst': qa_dup_gst,
            'qa_dup_fssai': qa_dup_fssai,
            'dup_names': dup_name_rows,
            'offboarded': offboarded,
            'disapproved': offboarded,  # backward-compat alias
            'onboarding_in_progress': in_progress,
            'group_counts': {
                'dup_pan_groups': dup_pan_groups, 'dup_pan_rows': dup_pan_rows,
                'dup_gst_groups': dup_gst_groups, 'dup_gst_rows': dup_gst_rows,
                'dup_fssai_groups': dup_fssai_groups, 'dup_fssai_rows': dup_fssai_rows,
            },
        }

    # ==================== QA decisions (approve / disapprove) ====================
    QA_DECISIONS_TAB_NAME = 'QA-Decisions'
    QA_DECISIONS_HEADERS = ['Timestamp', 'Key', 'Queue', 'Business_Name',
                            'Decision', 'Decided_By']

    def _get_qa_decisions_worksheet(self, create=False):
        """QA-Decisions tab handle. Lazily created on FIRST WRITE only â€”
        reads never create it. This is the sole tab this feature writes to;
        Enhanced / app_sheet / Superset are never written."""
        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        try:
            return spreadsheet.worksheet(self.QA_DECISIONS_TAB_NAME)
        except gspread.exceptions.WorksheetNotFound:
            if not create:
                return None
            ws = spreadsheet.add_worksheet(
                title=self.QA_DECISIONS_TAB_NAME, rows=1000, cols=6)
            ws.append_row(self.QA_DECISIONS_HEADERS)
            return ws

    def _read_qa_decisions(self):
        """Latest decision per key from the append-only QA-Decisions tab
        (later rows win). Empty dict if the tab doesn't exist yet."""
        try:
            ws = self._get_qa_decisions_worksheet(create=False)
        except Exception:
            return {}
        if ws is None:
            return {}
        decisions = {}
        for row in ws.get_all_values()[1:]:
            if len(row) >= 5 and row[1].strip():
                decisions[row[1].strip()] = {
                    'decision': row[4].strip().lower(),
                    'decided_by': row[5].strip() if len(row) > 5 else '',
                    'timestamp': row[0],
                }
        return decisions

    def record_horeca_qa_decision(self, key, queue, business_name,
                                  decision, decided_by):
        """Append one approve/disapprove decision. Append-only audit trail â€”
        re-deciding a key appends a new row; the latest row wins on read."""
        decision = (decision or '').strip().lower()
        if decision not in ('approved', 'disapproved'):
            raise ValueError("decision must be 'approved' or 'disapproved'")
        key = (key or '').strip()
        if not key:
            raise ValueError('key is required')
        ws = self._get_qa_decisions_worksheet(create=True)
        ws.append_row([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            key, (queue or '').strip(), (business_name or '').strip(),
            decision, (decided_by or '').strip(),
        ], value_input_option='RAW')
        global _superset_validation_cache
        _superset_validation_cache['data'] = None
        _superset_validation_cache['expiry'] = None
        return {'success': True, 'key': key, 'decision': decision}

    @staticmethod
    def _parse_latlng(loc_str):
        try:
            lat_s, lng_s = loc_str.split(',')
            return float(lat_s.strip()), float(lng_s.strip())
        except (ValueError, AttributeError):
            return None, None

    def _build_enhanced_name_index(self, enh_rows, enh_headers):
        h = {hdr: i for i, hdr in enumerate(enh_headers)}
        idx = {}
        for row in enh_rows:
            name_i = h.get('Name', 1)
            name = row[name_i].strip() if name_i < len(row) else ''
            norm = self._normalize_horeca_name(name)
            if norm:
                idx.setdefault(norm, []).append(row)
        return idx, h

    def get_horeca_appsheet_sync_preview(self, page=1, page_size=25, filter_mode='all'):
        """Read-only, step-by-step preview of what an app_sheet -> Enhanced
        sync would do for each app_sheet lead: the matched Enhanced record
        (if any), each side's current data, and the decision the sync would
        make. Writes nothing â€” this exists so the matching/reconciliation
        logic can be inspected and trusted before it's ever allowed to write.
        """
        app_rows, app_headers = self._get_appsheet_cache()
        ah = {hdr: i for i, hdr in enumerate(app_headers)}
        enh_rows, enh_headers = self._get_horeca_crm_cache()
        name_index, eh = self._build_enhanced_name_index(enh_rows, enh_headers)

        def ag(row, col):
            i = ah.get(col)
            return row[i].strip() if i is not None and i < len(row) else ''

        def eg(row, col):
            i = eh.get(col)
            return row[i].strip() if i is not None and i < len(row) else ''

        results = []
        for arow in app_rows:
            name = ag(arow, 'HoReCa Name')
            if not name:
                continue

            entry = {
                'app_sheet_id': ag(arow, 'ID'),
                'name': name,
                'lead_source': ag(arow, 'Lead Source'),
                'lead_stage_raw': ag(arow, 'Lead Stage'),
                'lead_poc': ag(arow, 'Lead POC'),
                'last_updated_appsheet': ag(arow, 'Last updated Date'),
                'match': None,
                'enhanced': None,
                'decision': None,
                'decision_detail': '',
            }

            norm = self._normalize_horeca_name(name)
            candidates = name_index.get(norm, [])
            if not candidates:
                entry['decision'] = 'no_match'
                entry['decision_detail'] = 'No Enhanced record with this name â€” new lead, not yet enriched.'
                results.append(entry)
                continue

            a_lat, a_lng = self._parse_latlng(ag(arow, 'Location'))
            within = []
            for erow in candidates:
                dist = self._haversine_meters(a_lat, a_lng, eg(erow, 'Latitude'), eg(erow, 'Longitude'))
                if dist is not None and dist <= self.APPSHEET_GEO_THRESHOLD_M:
                    within.append((erow, dist))

            if not within:
                entry['decision'] = 'no_match'
                entry['decision_detail'] = f"{len(candidates)} Enhanced record(s) share this name but none are within {self.APPSHEET_GEO_THRESHOLD_M}m â€” likely a different business with the same name."
                results.append(entry)
                continue

            if len(within) > 1:
                entry['decision'] = 'ambiguous_match'
                entry['decision_detail'] = f'{len(within)} Enhanced records both match by name and distance â€” needs manual review, not auto-synced.'
                results.append(entry)
                continue

            erow, dist = within[0]
            entry['match'] = {
                'place_id': eg(erow, 'Place ID'),
                'distance_m': round(dist, 1),
            }
            entry['enhanced'] = {
                'outreach_status': eg(erow, 'Outreach_Status'),
                'assigned_to': eg(erow, 'Assigned_To'),
                'last_updated': eg(erow, 'Last_Updated'),
                'updated_by': eg(erow, 'Updated_By'),
            }

            mapped_status = self.APPSHEET_STATUS_MAP.get(entry['lead_stage_raw'].lower())
            entry['lead_stage_mapped'] = mapped_status
            if mapped_status is None:
                entry['decision'] = 'unmapped_status'
                entry['decision_detail'] = f"app_sheet Lead Stage \"{entry['lead_stage_raw']}\" has no confident mapping to an Enhanced status â€” needs review."
                results.append(entry)
                continue

            if not mapped_status:
                entry['decision'] = 'no_change_needed'
                entry['decision_detail'] = 'app_sheet lead not yet worked (Lead Created) â€” nothing to sync.'
                results.append(entry)
                continue

            if mapped_status == entry['enhanced']['outreach_status']:
                entry['decision'] = 'no_change_needed'
                entry['decision_detail'] = 'Enhanced already reflects this status.'
                results.append(entry)
                continue

            # Never move a business backward in the pipeline, regardless of what
            # the timestamps say â€” a "newer" app_sheet edit to an unrelated
            # field (contact info, remarks) still bumps its Last Updated Date
            # even though Lead Stage is stale, and a downgrade from e.g.
            # "OB Form Filled" back to "Meeting done" would be a real data
            # loss. Verified against live data: without this guard, "Kentuckee
            # Seafood Restaurant" (Enhanced: OB Form Filled) would have been
            # wrongly downgraded to "Meeting done" from a stale app_sheet row.
            current_rank = self._status_rank(entry['enhanced']['outreach_status'])
            new_rank = self._status_rank(mapped_status)
            if current_rank is not None and new_rank is not None and new_rank < current_rank:
                entry['decision'] = 'no_change_needed'
                entry['decision_detail'] = f"app_sheet shows an earlier stage (\"{mapped_status}\") than Enhanced already has (\"{entry['enhanced']['outreach_status']}\") â€” never moving a business backward."
                results.append(entry)
                continue

            # Most-recent-timestamp-wins reconciliation. A missing/unparseable
            # timestamp on either side is NOT treated as "older" â€” it means we
            # have no evidence, so the side we can't date never wins.
            app_dt = self._parse_appsheet_datetime(entry['last_updated_appsheet'])
            enh_dt = self._parse_enhanced_datetime(entry['enhanced']['last_updated'])

            if enh_dt is None:
                entry['decision'] = 'would_sync'
                entry['decision_detail'] = f"Enhanced has no recorded update yet â€” would set Outreach_Status to \"{mapped_status}\"."
            elif app_dt is None:
                entry['decision'] = 'no_change_needed'
                entry['decision_detail'] = f"Enhanced already has a timestamped status ({entry['enhanced']['last_updated']}) and app_sheet has no parseable update date â€” can't prove app_sheet is newer, keeping Enhanced as-is."
            elif app_dt > enh_dt:
                entry['decision'] = 'would_sync'
                entry['decision_detail'] = f"app_sheet was updated more recently ({entry['last_updated_appsheet']}) than Enhanced ({entry['enhanced']['last_updated']}) â€” would set Outreach_Status to \"{mapped_status}\"."
            else:
                entry['decision'] = 'enhanced_is_newer'
                entry['decision_detail'] = f"Enhanced was updated more recently ({entry['enhanced']['last_updated']}) than app_sheet ({entry['last_updated_appsheet']}) â€” Enhanced wins, no sync."

            results.append(entry)

        if filter_mode and filter_mode != 'all':
            results = [r for r in results if r['decision'] == filter_mode]

        total = len(results)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(page, 1), total_pages)
        start = (page - 1) * page_size
        page_results = results[start:start + page_size]

        counts = {}
        for r in results:
            counts[r['decision']] = counts.get(r['decision'], 0) + 1

        return {
            'results': page_results,
            'total': total,
            'page': page,
            'total_pages': total_pages,
            'counts': counts,
        }

    @staticmethod
    def _parse_appsheet_datetime(s):
        if not s:
            return None
        for fmt in ('%m/%d/%Y %H:%M:%S', '%m/%d/%Y'):
            try:
                return datetime.strptime(s.split(' ')[0] if fmt == '%m/%d/%Y' else s, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_enhanced_datetime(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    def _ensure_enhanced_appsheet_id_column(self):
        """One-time, idempotent migration: add an AppSheet_Lead_ID column to
        Enhanced â€” the crosswalk join key the sync job maintains itself,
        nobody on the team ever types into it. Deliberately placed on
        Enhanced, NOT app_sheet: Enhanced is a plain, directly-edited sheet,
        while app_sheet is driven by a live IMPORTRANGE formula spilling
        across 29 columns (A:AC) that broke the first time a write landed
        inside its real (but visually blank) output range. Enhanced carries
        none of that risk, so this is the safer place for the crosswalk.
        Still verifies the target column is actually empty first, out of
        caution. Returns the column's 1-based index either way."""
        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        worksheet = spreadsheet.sheet1
        header_row = worksheet.row_values(1)
        if 'AppSheet_Lead_ID' in header_row:
            return header_row.index('AppSheet_Lead_ID') + 1

        col_idx = len(header_row) + 1
        sample_cells = worksheet.range(2, col_idx, 20, col_idx)
        if any(c.value for c in sample_cells):
            raise RuntimeError(
                f'Column {col_idx} on Enhanced is not empty â€” refusing to claim it as AppSheet_Lead_ID'
            )

        if worksheet.col_count < col_idx:
            worksheet.resize(cols=col_idx)
        worksheet.update_cell(1, col_idx, 'AppSheet_Lead_ID')
        global _horeca_crm_cache
        _horeca_crm_cache['expiry'] = None
        return col_idx

    def create_horeca_lead_from_appsheet(self, app_row, app_headers):
        """Create a new Enhanced row for a genuinely-new app_sheet lead,
        reusing the exact same path as the manual '+ Add Lead' flow
        (add_horeca_record). Enrichment-only fields â€” photos, priority
        score, zone assignment â€” are left blank, since only the offline
        Google-Places pipeline can populate those; everything else (CRM
        list, Board, Overall Daily, Metrics) works fine without them."""
        ah = {hdr: i for i, hdr in enumerate(app_headers)}

        def ag(col):
            i = ah.get(col)
            return app_row[i].strip() if i is not None and i < len(app_row) else ''

        lat, lng = self._parse_latlng(ag('Location'))
        mapped_status = self.APPSHEET_STATUS_MAP.get(ag('Lead Stage').lower())
        lead_poc = ag('Lead POC')
        assignee = self._associate_display_name(lead_poc).split(' ')[0] if '@' in lead_poc else ''

        data = {
            'name': ag('HoReCa Name'),
            'type': ag('HoReCa  Type'),
            'address': ag('Locality'),
            'city': ag('City'),
            'pincode': ag('Pincode'),
            'lat': lat if lat is not None else '',
            'lng': lng if lng is not None else '',
            'owner_name': ag('Contact Person Name'),
            'owner_phone': ag('Contact Number'),
            'assigned_to': assignee,
            'note': f"Auto-created from app_sheet lead {ag('ID')} (Lead Source: {ag('Lead Source')})",
        }
        if mapped_status:
            data['status'] = mapped_status

        return self.add_horeca_record(data)

    def sync_new_horeca_leads(self, dry_run=False):
        """Automatic app_sheet -> Enhanced sync for NEW leads. The crosswalk
        lives entirely on Enhanced's AppSheet_Lead_ID column (see
        _ensure_enhanced_appsheet_id_column) â€” app_sheet is never written
        to by this job, at all, ever.

        For every app_sheet lead whose ID isn't already recorded in some
        Enhanced row's AppSheet_Lead_ID:
          - no name match in Enhanced at all -> genuinely new, create a
            fresh Enhanced row and crosswalk it.
          - exactly one Enhanced match within the geo threshold -> link the
            crosswalk to that existing business, no new row.
          - zero or multiple candidates within threshold -> ambiguous
            (same name, wrong distance, or multiple plausible matches) â€”
            left unlinked and simply re-evaluated next run rather than
            auto-created (avoids duplicating a business that already
            exists under a slightly different name).
        """
        app_rows, app_headers = self._get_appsheet_cache()
        ah = {hdr: i for i, hdr in enumerate(app_headers)}
        name_idx = ah.get('HoReCa Name')
        id_idx = ah.get('ID')
        loc_idx = ah.get('Location')
        dt_idx = ah.get('Document_Type')
        dn_idx = ah.get('Document_Number')

        enh_rows, enh_headers = self._get_horeca_crm_cache()
        name_index, eh = self._build_enhanced_name_index(enh_rows, enh_headers)
        pid_idx = eh.get('Place ID', 0)
        lat_idx = eh.get('Latitude', 10)
        lng_idx = eh.get('Longitude', 11)
        appsheet_id_idx = eh.get('AppSheet_Lead_ID')
        pan_idx = eh.get('PAN_Number')
        gst_idx = eh.get('GST_Number')
        fssai_idx = eh.get('FSSAI_Number')

        def eg(erow, idx):
            return erow[idx].strip() if idx is not None and idx < len(erow) else ''

        def ag(arow, idx):
            return arow[idx].strip() if idx is not None and idx < len(arow) else ''

        # Enhanced identity indexes (any ONE of PAN/GST/FSSAI is enough) +
        # the set of Enhanced businesses already crosswalked to some app lead,
        # so we never attach a second app_id to a row that already has one.
        enh_by_pan, enh_by_gst, enh_by_fssai = {}, {}, {}
        already_linked_ids = set()
        linked_place_ids = set()
        for erow in enh_rows:
            if appsheet_id_idx is not None and eg(erow, appsheet_id_idx):
                already_linked_ids.add(eg(erow, appsheet_id_idx))
                pid = eg(erow, pid_idx)
                if pid:
                    linked_place_ids.add(pid)
            p = eg(erow, pan_idx).upper()
            g = eg(erow, gst_idx).upper()
            f = eg(erow, fssai_idx)
            if p:
                enh_by_pan.setdefault(p, erow)
            if g:
                enh_by_gst.setdefault(g, erow)
            if f:
                enh_by_fssai.setdefault(f, erow)

        created = 0
        linked_existing = 0
        doc_linked = 0
        doc_collision = 0
        ambiguous = 0
        skipped_already_done = 0
        errors = []
        pending_crosswalk = []  # (place_id, app_lead_id)

        for arow in app_rows:
            name = arow[name_idx].strip() if name_idx is not None and name_idx < len(arow) else ''
            if not name:
                continue
            app_id = arow[id_idx].strip() if id_idx is not None and id_idx < len(arow) else ''
            if app_id and app_id in already_linked_ids:
                skipped_already_done += 1
                continue

            # Tier 1 â€” deterministic identity match: if the app_sheet lead's
            # captured document (PAN or GST or FSSAI, any one) matches an
            # Enhanced row, link the crosswalk to it. This resolves leads that
            # name+geo would otherwise skip as "ambiguous" (blank coords or a
            # same-name twin) without risking a duplicate. Guarded so we never
            # double-claim an Enhanced row already linked to another lead.
            col, num = self._classify_document(ag(arow, dt_idx), ag(arow, dn_idx))
            doc_erow = None
            if col == 'PAN_Number' and num in enh_by_pan:
                doc_erow = enh_by_pan[num]
            elif col == 'GST_Number' and num in enh_by_gst:
                doc_erow = enh_by_gst[num]
            elif col == 'FSSAI_Number' and num in enh_by_fssai:
                doc_erow = enh_by_fssai[num]
            if doc_erow is not None:
                dpid = eg(doc_erow, pid_idx)
                if dpid and dpid not in linked_place_ids:
                    doc_linked += 1
                    if not dry_run:
                        pending_crosswalk.append((dpid, app_id))
                    linked_place_ids.add(dpid)
                else:
                    doc_collision += 1
                continue

            norm = self._normalize_horeca_name(name)
            candidates = name_index.get(norm, [])

            if not candidates:
                if dry_run:
                    created += 1
                    continue
                try:
                    result = self.create_horeca_lead_from_appsheet(arow, app_headers)
                    pending_crosswalk.append((result['place_id'], app_id))
                    created += 1
                except Exception as e:
                    errors.append(f'{name}: {e}')
                continue

            raw_loc = arow[loc_idx].strip() if loc_idx is not None and loc_idx < len(arow) else ''
            a_lat, a_lng = self._parse_latlng(raw_loc)
            within = []
            for erow in candidates:
                dist = self._haversine_meters(a_lat, a_lng, eg(erow, lat_idx), eg(erow, lng_idx))
                if dist is not None and dist <= self.APPSHEET_GEO_THRESHOLD_M:
                    within.append(erow)

            if len(within) == 1:
                wpid = eg(within[0], pid_idx)
                if wpid and wpid in linked_place_ids:
                    # that Enhanced row is already crosswalked â€” don't double-claim
                    ambiguous += 1
                else:
                    linked_existing += 1
                    if wpid:
                        linked_place_ids.add(wpid)
                    if not dry_run:
                        pending_crosswalk.append((wpid, app_id))
            else:
                ambiguous += 1

        if pending_crosswalk and not dry_run:
            appsheet_col_idx = self._ensure_enhanced_appsheet_id_column()

            # Force a fresh read so rows created above (via append_row) are
            # included when resolving place_id -> row_num â€” never assume a
            # specific landing position for a freshly appended row.
            global _horeca_crm_cache
            _horeca_crm_cache['expiry'] = None
            fresh_rows, fresh_headers = self._get_horeca_crm_cache()
            fresh_pid_idx = {hdr: i for i, hdr in enumerate(fresh_headers)}.get('Place ID', 0)
            row_num_by_place_id = {
                row[fresh_pid_idx]: idx + 2
                for idx, row in enumerate(fresh_rows)
                if fresh_pid_idx < len(row) and row[fresh_pid_idx]
            }

            cells_to_write = []
            for place_id, app_id in pending_crosswalk:
                row_num = row_num_by_place_id.get(place_id)
                if row_num:
                    cells_to_write.append(gspread.Cell(row_num, appsheet_col_idx, app_id))
                else:
                    errors.append(f'Could not resolve row for place_id {place_id} (app lead {app_id})')

            spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
            worksheet = spreadsheet.sheet1
            # Chunk the batch write â€” a single request covering thousands of
            # cells (e.g. the first-ever catch-up run) risks the Sheets
            # API's per-request size limit; chunking keeps each call small
            # and lets one bad chunk fail without losing the rest.
            CHUNK_SIZE = 1000
            for i in range(0, len(cells_to_write), CHUNK_SIZE):
                chunk = cells_to_write[i:i + CHUNK_SIZE]
                try:
                    worksheet.update_cells(chunk)
                except Exception as e:
                    errors.append(f'crosswalk batch {i}-{i + len(chunk)}: {e}')

            _horeca_crm_cache['expiry'] = None

        return {
            'dry_run': dry_run,
            'created': created,
            'linked_existing': linked_existing,
            'doc_linked': doc_linked,
            'doc_collision': doc_collision,
            'ambiguous_skipped': ambiguous,
            'already_done_skipped': skipped_already_done,
            'errors': errors,
        }

    @staticmethod
    def _classify_document(doc_type, doc_number):
        """Map an app_sheet Document_Type/Document_Number pair onto the
        matching Enhanced column. The form holds ONE document per lead â€”
        PAN or GST or FSSAI â€” signalled by Document_Type, with a format
        sanity-check as backup (PAN=10 alphanumeric, GSTIN=15, FSSAI=14
        digits) since the type field is free-ish text."""
        num = (doc_number or '').strip().upper()
        if not num:
            return None, None
        dt = (doc_type or '').strip().upper()
        if 'FSSAI' in dt or (num.isdigit() and len(num) == 14):
            return 'FSSAI_Number', num
        if 'GST' in dt or len(num) == 15:
            return 'GST_Number', num
        if 'PAN' in dt or len(num) == 10:
            return 'PAN_Number', num
        return None, None

    def sync_appsheet_documents_to_enhanced(self, dry_run=False):
        """Copy PAN/GST/FSSAI captured in app_sheet (Document_Type +
        Document_Number) into the matching Enhanced columns, using the
        AppSheet_Lead_ID crosswalk â€” deterministic, no matching involved.
        Only fills BLANK Enhanced cells; never overwrites an existing value
        (a value already in Enhanced may have been hand-entered via the CRM
        and should win). Enhanced is the master store, so this is what keeps
        it complete as associates capture documents in the field."""
        app_rows, app_headers = self._get_appsheet_cache()
        ah = {hdr: i for i, hdr in enumerate(app_headers)}
        id_idx = ah.get('ID')
        dt_idx = ah.get('Document_Type')
        dn_idx = ah.get('Document_Number')

        def ag(row, idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ''

        docs_by_lead = {}
        for arow in app_rows:
            app_id = ag(arow, id_idx)
            if not app_id:
                continue
            col_name, num = self._classify_document(ag(arow, dt_idx), ag(arow, dn_idx))
            if col_name:
                docs_by_lead[app_id] = (col_name, num)

        enh_rows, enh_headers = self._get_horeca_crm_cache()
        eh = {hdr: i for i, hdr in enumerate(enh_headers)}
        appsheet_idx = eh.get('AppSheet_Lead_ID')
        col_indices = {c: eh.get(c) for c in ('PAN_Number', 'GST_Number', 'FSSAI_Number')}

        would_write = []   # (row_num, col_name, value, business_name)
        skipped_filled = 0
        unlinked_docs = 0
        name_idx = eh.get('Name', 1)

        linked_app_ids = set()
        for row_pos, erow in enumerate(enh_rows):
            app_id = erow[appsheet_idx].strip() if appsheet_idx is not None and appsheet_idx < len(erow) else ''
            if not app_id or app_id not in docs_by_lead:
                continue
            linked_app_ids.add(app_id)
            col_name, num = docs_by_lead[app_id]
            col_idx = col_indices.get(col_name)
            existing = erow[col_idx].strip() if col_idx is not None and col_idx < len(erow) else ''
            if existing:
                skipped_filled += 1
                continue
            bname = erow[name_idx] if name_idx < len(erow) else ''
            would_write.append((row_pos + 2, col_name, num, bname))

        unlinked_docs = len(set(docs_by_lead) - linked_app_ids)

        result = {
            'dry_run': dry_run,
            'would_write' if dry_run else 'written': len(would_write),
            'already_filled_skipped': skipped_filled,
            'docs_on_unlinked_leads': unlinked_docs,
            'sample': [
                {'row': r, 'column': c, 'value': v, 'business': b}
                for r, c, v, b in would_write[:20]
            ],
            'errors': [],
        }

        if dry_run or not would_write:
            return result

        # FSSAI_Number column may not exist yet â€” provision all three
        # (idempotent, verify-empty-before-claim) before writing.
        col_idx_by_name = self._ensure_enhanced_pan_gst_columns()
        spreadsheet = self.gc.open_by_key(self.HORECA_CRM_SHEET_ID)
        worksheet = spreadsheet.sheet1
        cells = [
            gspread.Cell(row_num, col_idx_by_name[col_name], value)
            for row_num, col_name, value, _ in would_write
            if col_name in col_idx_by_name
        ]
        CHUNK_SIZE = 1000
        for i in range(0, len(cells), CHUNK_SIZE):
            try:
                worksheet.update_cells(cells[i:i + CHUNK_SIZE])
            except Exception as e:
                result['errors'].append(f'doc batch {i}: {e}')

        global _horeca_crm_cache
        _horeca_crm_cache['expiry'] = None
        return result

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


# HoReCa CRM cache (process-level). TTL is longer than the in-app cache-warmer
# interval (see endpoints.py `_cache_warmer`) so the heavy Sheets reads are
# always served warm and users never trigger the ~9s cold path. The underlying
# data changes at most every few hours (auto-sync 6h; Superset_v1 daily), so a
# 15-min TTL is safely fresh.
_HORECA_CACHE_TTL = timedelta(minutes=15)
_horeca_crm_cache = {'data': None, 'headers': None, 'clusters': None, 'expiry': None}
_appsheet_cache = {'data': None, 'headers': None, 'expiry': None}
_superset_cache = {'data': None, 'headers': None, 'expiry': None}
_superset_v1_cache = {'data': None, 'headers': None, 'expiry': None}
_superset_validation_cache = {'data': None, 'expiry': None}
_excise_cache = {'data': None, 'expiry': None}

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
        attachments: List[str] = None,
        inline_images: dict = None
    ) -> str:
        """
        Send an email

        Args:
            to: Recipient email
            subject: Email subject
            body: Email body (HTML supported)
            cc: CC recipients
            attachments: List of file paths to attach
            inline_images: {content_id: png_bytes} referenced in HTML as
                           <img src="cid:content_id"> â€” rendered inline by
                           Gmail (unlike data: URIs, which Gmail strips).

        Returns:
            Message ID
        """
        import base64
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email.mime.image import MIMEImage
        from email import encoders

        message = MIMEMultipart('related') if inline_images else MIMEMultipart()
        message['to'] = to
        message['subject'] = subject

        if cc:
            message['cc'] = ', '.join(cc)

        message.attach(MIMEText(body, 'html'))

        if inline_images:
            for cid, png_bytes in inline_images.items():
                img = MIMEImage(png_bytes, _subtype='png')
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline',
                               filename=f'{cid}.png')
                message.attach(img)

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

