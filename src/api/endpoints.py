"""
FastAPI endpoints for the Goa DRS VP CP Mapping system
"""
from datetime import date, datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Union
import tempfile
import os
import json
from pathlib import Path
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired

from ..config.settings import DeploymentStage, GOA_BLOCKS, STAGE_LABELS, Settings
from ..services.tracker import VPTracker
from ..services.google_services import GoogleSheetsService, AuthService
from ..models.entities import MeetingUpdate

settings = Settings()

SUPERADMIN_EMAIL = 'ashwin.singh@recykal.com'

def _parse_device_info(user_agent: str) -> dict:
    ua = (user_agent or '').lower()
    device_type = 'Mobile' if any(x in ua for x in ['mobile', 'android', 'iphone', 'ipad']) else 'Desktop'
    if 'edg' in ua:       browser = 'Edge'
    elif 'chrome' in ua:  browser = 'Chrome'
    elif 'firefox' in ua: browser = 'Firefox'
    elif 'safari' in ua:  browser = 'Safari'
    else:                 browser = 'Other'
    if 'android' in ua:                     os_name = 'Android'
    elif 'iphone' in ua or 'ipad' in ua:    os_name = 'iOS'
    elif 'windows' in ua:                   os_name = 'Windows'
    elif 'mac' in ua:                       os_name = 'macOS'
    elif 'linux' in ua:                     os_name = 'Linux'
    else:                                   os_name = 'Other'
    return {'device_type': device_type, 'browser': browser, 'os': os_name}

# Session cookie config
SESSION_SECRET = os.getenv('SESSION_SECRET', 'goa-drs-default-secret-change-me')
SESSION_COOKIE_NAME = 'drs_session'
SESSION_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds
signer = TimestampSigner(SESSION_SECRET)

app = FastAPI(
    title="Goa DRS VP Collection Point Mapping API",
    description="API for tracking RVM deployment across Village Panchayats in Goa",
    version="1.0.0",
)

# ==================== Auth Helpers ====================

# Paths that don't require authentication
PUBLIC_PATHS = {'/api/auth/login', '/api/auth/logout', '/api/auth/init', '/api/auth/me', '/api/health', '/api/training/init', '/', '/docs', '/openapi.json', '/rl'}


def get_session_user(request: Request) -> Optional[dict]:
    """Read and verify the session cookie. Returns user dict or None."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None
    try:
        unsigned = signer.unsign(cookie, max_age=SESSION_MAX_AGE).decode('utf-8')
        return json.loads(unsigned)
    except (BadSignature, SignatureExpired, json.JSONDecodeError):
        return None


def require_auth(request: Request) -> dict:
    """FastAPI dependency — returns current user or raises 401."""
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ==================== RBAC ====================

ROLE_TAB_PERMISSIONS = {
    'admin': {'vps', 'ulbs', 'dashboard', 'meetings', 'escalation', 'today', 'horeca', 'learning'},
    'vp': {'vps', 'dashboard', 'meetings', 'escalation', 'today', 'learning'},
    'horeca': {'horeca', 'dashboard', 'meetings', 'today', 'learning'},
    'new_joinee': {'learning'},
}

def require_role(request: Request, allowed_roles: set) -> dict:
    """Require auth + role membership. Returns user or raises 403."""
    user = require_auth(request)
    role = user.get('role', 'new_joinee')
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Access denied for your role")
    return user


# GZip compression — cuts static asset transfer size by ~70%
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware — protect all /api/* routes except public paths
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Allow public paths, static files, and RL API (standalone tool)
    if (path in PUBLIC_PATHS
            or path.startswith('/static')
            or path.startswith('/api/rl')
            or not path.startswith('/api')):
        return await call_next(request)

    # Check auth
    user = get_session_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    return await call_next(request)


# Static files - serve frontend
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# Initialize tracker
tracker = VPTracker()


# Request/Response models
class TextUpdateRequest(BaseModel):
    """Request model for text-based updates"""
    text: str
    village_panchayat_name: Optional[str] = None
    block_name: Optional[str] = None
    recorded_by: Optional[str] = None


class StageUpdateRequest(BaseModel):
    """Request model for stage updates"""
    village_panchayat_name: str
    block_name: str
    new_stage: DeploymentStage
    notes: Optional[str] = None


class EmailRequest(BaseModel):
    """Request model for sending confirmation email"""
    village_panchayat_name: str
    block_name: str


# Endpoints
@app.get("/")
async def root():
    """Serve the frontend application"""
    frontend_path = FRONTEND_DIR / "index.html"
    if frontend_path.exists():
        return FileResponse(str(frontend_path))
    return {"status": "healthy", "service": "Goa DRS VP CP Mapping"}


@app.get("/api/health")
async def health():
    """API health check"""
    return {"status": "healthy", "service": "Goa DRS VP CP Mapping"}


@app.get("/blocks")
async def get_blocks():
    """Get list of all blocks in Goa"""
    return {"blocks": GOA_BLOCKS}


@app.get("/stages")
async def get_stages():
    """Get list of all deployment stages"""
    return {
        "stages": [
            {"value": stage.value, "label": STAGE_LABELS[stage]}
            for stage in DeploymentStage
        ]
    }


@app.post("/update/text")
async def process_text_update(request: TextUpdateRequest):
    """
    Process a text-based field update.

    The AI will extract data points from the text and update the tracker.
    """
    context = {
        "village_panchayat_name": request.village_panchayat_name,
        "block_name": request.block_name,
        "recorded_by": request.recorded_by,
    }

    result = await tracker.process_field_update(
        input_text=request.text,
        context=context
    )

    if not result['success']:
        raise HTTPException(status_code=400, detail=result['message'])

    return result


@app.post("/update/voice")
async def process_voice_update(
    audio: UploadFile = File(...),
    language: str = Form("hi-IN"),
    village_panchayat_name: Optional[str] = Form(None),
    block_name: Optional[str] = Form(None),
    recorded_by: Optional[str] = Form(None),
):
    """
    Process a voice-based field update using Sarvam AI.

    Upload an audio file (WAV, MP3, WebM, etc.) and the AI will:
    1. Transcribe the audio (supports Hindi, Marathi, English)
    2. Extract data points automatically
    3. Return structured data for the tracker
    """
    # Save uploaded file temporarily
    suffix = os.path.splitext(audio.filename)[1] if audio.filename else '.webm'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        context = {
            "village_panchayat_name": village_panchayat_name,
            "block_name": block_name,
            "recorded_by": recorded_by,
        }

        # Try Sarvam AI first
        if settings.sarvam_api_key:
            from ..services.sarvam_processor import SarvamAIProcessor
            processor = SarvamAIProcessor(settings.sarvam_api_key)

            meeting_update = await processor.process_voice_input(
                audio_file_path=tmp_path,
                language=language,
                context=context
            )

            return {
                "success": True,
                "transcript": meeting_update.raw_input,
                "language": language,
                "extracted_data": {
                    "secretary_name": meeting_update.secretary_name,
                    "secretary_phone": meeting_update.secretary_phone,
                    "sarpanch_name": meeting_update.sarpanch_name,
                    "sarpanch_phone": meeting_update.sarpanch_phone,
                    "email_id": meeting_update.email_id,
                    "location_description": meeting_update.location_description,
                    "follow_up_date": str(meeting_update.follow_up_date) if meeting_update.follow_up_date else None,
                    "suggested_stage": meeting_update.suggested_stage.value if meeting_update.suggested_stage else None,
                }
            }

        # Fallback to original tracker
        result = await tracker.process_field_update(
            audio_file=tmp_path,
            context=context
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['message'])

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {str(e)}")

    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/stage/update")
async def update_stage(request: StageUpdateRequest):
    """Update the deployment stage for a village panchayat"""
    try:
        tracker.update_stage(
            vp_name=request.village_panchayat_name,
            block_name=request.block_name,
            new_stage=request.new_stage,
            notes=request.notes,
        )
        return {"success": True, "message": f"Stage updated to {request.new_stage.value}"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/email/confirmation")
async def send_confirmation_email(request: EmailRequest):
    """Send confirmation email to a village panchayat"""
    try:
        tracker.send_confirmation_email(
            vp_name=request.village_panchayat_name,
            block_name=request.block_name,
        )
        return {"success": True, "message": "Confirmation email sent"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary/overall")
async def get_overall_summary():
    """Get overall deployment summary"""
    try:
        summary = tracker.get_overall_summary()
        return summary.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary/block/{block_name}")
async def get_block_summary(block_name: str):
    """Get deployment summary for a specific block"""
    try:
        summary = tracker.get_block_summary(block_name)
        return summary.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/followups/pending")
async def get_pending_followups():
    """Get list of VPs with pending follow-ups"""
    try:
        followups = tracker.get_pending_followups()
        return {"pending_followups": followups, "count": len(followups)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vps/stage/{stage}")
async def get_vps_by_stage(stage: DeploymentStage):
    """Get all VPs at a specific deployment stage"""
    try:
        vps = tracker.get_vps_by_stage(stage)
        return {"stage": stage.value, "vps": vps, "count": len(vps)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/pipeline")
async def get_pipeline_analytics():
    """
    Get funnel/pipeline analytics showing conversion through stages
    """
    try:
        summary = tracker.get_overall_summary()

        # Build funnel data
        funnel = []
        cumulative = summary.total_vps

        stage_order = [
            ("Total VPs", summary.total_vps),
            ("Meetings Done", summary.total_vps - summary.stage_counts.get('yet_to_meet', 0)),
            ("Location Finalized", sum(
                summary.stage_counts.get(s.value, 0)
                for s in [
                    DeploymentStage.LOCATION_FINALIZED,
                    DeploymentStage.EMAIL_SENT,
                    DeploymentStage.NOC_PENDING,
                    DeploymentStage.NOC_RECEIVED,
                    DeploymentStage.SERVICE_AGREEMENT_SENT,
                    DeploymentStage.SERVICE_AGREEMENT_SIGNED,
                    DeploymentStage.INFRA_PENDING,
                    DeploymentStage.INFRA_COMPLETE,
                    DeploymentStage.DEVICE_DEPLOYED,
                    DeploymentStage.DEVICE_INSTALLED,
                ]
            )),
            ("NOC Received", summary.nocs_received),
            ("Agreement Signed", summary.agreements_signed),
            ("Infrastructure Ready", summary.infra_complete),
            ("Devices Installed", summary.devices_installed),
        ]

        for label, count in stage_order:
            funnel.append({
                "stage": label,
                "count": count,
                "percentage": round(count / summary.total_vps * 100, 1) if summary.total_vps > 0 else 0
            })

        return {
            "funnel": funnel,
            "blocks_touched": f"{summary.blocks_touched}/12",
            "overall_completion": f"{summary.overall_completion_percentage:.1f}%"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Additional endpoints for frontend

class DirectStageUpdate(BaseModel):
    """Request model for direct stage updates from frontend"""
    vp_code: str
    block: str
    new_stage: str
    meeting_notes: Optional[str] = None
    followup_date: Optional[str] = None
    followup_time: Optional[str] = "10:00"  # HH:MM format, default 10:00 AM
    updated_by: str
    create_calendar_event: bool = False  # Calendar removed — kept for API compat


class RVMLocation(BaseModel):
    """GPS coordinates for an RVM location"""
    lat: float
    lng: float
    accuracy: Optional[float] = None
    timestamp: Optional[str] = None


class VPProfileUpdate(BaseModel):
    """Request model for VP profile updates"""
    vp_code: str
    block: str
    secretary_name: Optional[str] = ""
    secretary_phone: Optional[str] = ""
    sarpanch_name: Optional[str] = ""
    sarpanch_phone: Optional[str] = ""
    vp_email: Optional[str] = ""
    contractor_name: Optional[str] = ""
    contractor_phone: Optional[str] = ""
    planned_rvms: Optional[int] = 1  # Default to 1
    agreed_rvms: Optional[int] = 0
    rvm_locations: Optional[List[RVMLocation]] = []
    # Cost & Operations
    electricity_bearer: Optional[str] = ""  # VP, Recykal, Shared
    internet_bearer: Optional[str] = ""     # VP, Recykal, Shared
    handler_hired_by: Optional[str] = ""    # VP, Recykal
    space_type: Optional[str] = ""          # Free, Rental
    updated_by: str = "Unknown"


class BDOUpdateRequest(BaseModel):
    """Request model for BDO stage updates"""
    block: str
    new_stage: str  # yet_to_meet, follow_up_required, meeting_set_up, meeting_done, communication_sent


class CommentRequest(BaseModel):
    """Request model for direct comments"""
    vp_code: str
    comment: str
    author: str
    comment_type: str = "direct"  # direct, meeting, legacy


# ==================== Auth Endpoints ====================

class LoginRequest(BaseModel):
    email: str
    pin: str


@app.post("/api/auth/login")
async def login(request: LoginRequest, response: Response, http_request: Request):
    """Validate email + PIN and set session cookie"""
    try:
        auth_service = AuthService()
        user = auth_service.validate_user(request.email, request.pin)

        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or PIN")

        # Create signed session cookie
        session_data = json.dumps({
            'email': user['email'],
            'name': user['name'],
            'role': user['role'],
        })
        signed = signer.sign(session_data.encode('utf-8')).decode('utf-8')

        role = user.get('role', 'new_joinee')
        allowed_tabs = sorted(ROLE_TAB_PERMISSIONS.get(role, {'learning'}))
        response = JSONResponse(content={
            "success": True,
            "user": {"name": user['name'], "email": user['email'], "role": role, "allowed_tabs": allowed_tabs}
        })
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=signed,
            max_age=SESSION_MAX_AGE,
            httponly=False,  # JS needs to read user info; cookie is signed
            samesite='lax',
            secure=False,  # Set True if using HTTPS only
        )

        # Log login event (fire and forget)
        try:
            ua = http_request.headers.get('user-agent', '')
            device = _parse_device_info(ua)
            fwd = http_request.headers.get('x-forwarded-for')
            ip = fwd.split(',')[0].strip() if fwd else (http_request.client.host if http_request.client else 'unknown')
            GoogleSheetsService().log_analytics_event({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'user_email': user['email'],
                'user_name': user['name'],
                'event_type': 'login',
                'page': '', 'element': '', 'value': '', 'session_id': '',
                'device_type': device['device_type'],
                'browser': device['browser'],
                'os': device['os'],
                'ip': ip,
            })
        except Exception:
            pass

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/logout")
async def logout(response: Response):
    """Clear session cookie"""
    response = JSONResponse(content={"success": True})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/api/auth/me")
async def get_current_user(request: Request):
    """Return current user info from session cookie"""
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = user.get('role', 'new_joinee')
    allowed_tabs = sorted(ROLE_TAB_PERMISSIONS.get(role, {'learning'}))
    return {"user": {**user, "allowed_tabs": allowed_tabs}}


@app.post("/api/auth/init")
async def init_auth_sheet():
    """One-time: Create Authorized-Users sheet with headers"""
    try:
        auth_service = AuthService()
        result = auth_service.init_authorized_users()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vps/all")
async def get_all_vps(request: Request):
    """Get all VPs data for frontend"""
    require_role(request, {'admin', 'vp'})
    try:
        sheets_service = GoogleSheetsService()
        data = sheets_service.get_tracker_data()
        return data
    except Exception as e:
        # Return empty list if sheets not configured
        return []


@app.post("/api/update/stage")
async def update_stage_direct(request: DirectStageUpdate):
    """Update VP stage directly from frontend"""
    try:
        sheets_service = GoogleSheetsService()

        # Find the row for this VP
        row_num = sheets_service.find_vp_row(request.vp_code)
        if not row_num:
            raise HTTPException(status_code=404, detail=f"VP {request.vp_code} not found")

        # Get stage number
        stage_map = {s.value: i+1 for i, s in enumerate(DeploymentStage)}
        stage_number = stage_map.get(request.new_stage, 1)

        # Update the row (column mapping: AL=Last_Updated, AM=Updated_By after Cost & Operations fields)
        updates = {
            'N': request.new_stage,  # Current_Stage
            'O': str(stage_number),  # Stage_Number
            'P': datetime.now().strftime('%Y-%m-%d'),  # Stage_Date
            'AL': datetime.now().isoformat(),  # Last_Updated
            'AM': request.updated_by,  # Updated_By
        }

        # Append meeting notes with timestamp, type, author (preserve conversation history)
        if request.meeting_notes:
            existing_notes = sheets_service.get_vp_cell_value(row_num, 'Q')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            author = request.updated_by or 'Team'
            new_entry = f"[{timestamp}|meeting|{author}] {request.meeting_notes}"
            if existing_notes:
                updates['Q'] = f"{new_entry}\n---\n{existing_notes}"  # New notes first
            else:
                updates['Q'] = new_entry

        if request.followup_date:
            updates['R'] = request.followup_date  # Follow_Up_Date

        sheets_service.update_vp_row(row_num, updates)

        return {
            "success": True,
            "message": f"Updated {request.vp_code} to {request.new_stage}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/update/profile")
async def update_vp_profile(request: VPProfileUpdate):
    """Update VP profile details (contact info, RVM counts, locations)"""
    try:
        sheets_service = GoogleSheetsService()

        # Find the row for this VP
        row_num = sheets_service.find_vp_row(request.vp_code)
        if not row_num:
            raise HTTPException(status_code=404, detail=f"VP {request.vp_code} not found")

        # Format RVM locations as JSON string
        rvm_locations_str = ""
        if request.rvm_locations:
            locations = [{"lat": loc.lat, "lng": loc.lng} for loc in request.rvm_locations]
            import json
            rvm_locations_str = json.dumps(locations)

        # Update the row - using DRS-Tracker column mapping (updated 2026-02-04)
        # Columns: F=Secretary_Name, G=Secretary_Phone, H=Sarpanch_Name, I=Sarpanch_Phone, J=VP_Email
        # AC=Contractor_Name, AD=Contractor_Phone, AE=Planned_RVMs, AF=Agreed_RVMs, AG=RVM_Locations
        # AH=Electricity_Cost_Bearer, AI=Internet_Cost_Bearer, AJ=Handler_Hired_By, AK=Space_Type
        # AL=Last_Updated, AM=Updated_By
        updates = {
            'F': request.secretary_name,      # Secretary_Name
            'G': request.secretary_phone,     # Secretary_Phone
            'H': request.sarpanch_name,       # Sarpanch_Name
            'I': request.sarpanch_phone,      # Sarpanch_Phone
            'J': request.vp_email,            # VP_Email
            'AC': request.contractor_name,    # Contractor_Name
            'AD': request.contractor_phone,   # Contractor_Phone
            'AE': str(request.planned_rvms) if request.planned_rvms else '1',  # Planned_RVMs (default 1)
            'AF': str(request.agreed_rvms) if request.agreed_rvms else '',     # Agreed_RVMs
            'AG': rvm_locations_str,          # RVM_Locations (JSON)
            'AH': request.electricity_bearer, # Electricity_Cost_Bearer
            'AI': request.internet_bearer,    # Internet_Cost_Bearer
            'AJ': request.handler_hired_by,   # Handler_Hired_By
            'AK': request.space_type,         # Space_Type
            'AL': datetime.now().isoformat(), # Last_Updated
            'AM': request.updated_by,         # Updated_By
        }

        sheets_service.update_vp_row(row_num, updates)

        return {
            "success": True,
            "message": f"Profile updated for {request.vp_code}",
            "rvm_locations_count": len(request.rvm_locations) if request.rvm_locations else 0
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/comment")
async def post_comment(request: CommentRequest):
    """Post a direct comment to a VP without changing status"""
    try:
        sheets_service = GoogleSheetsService()

        # Find the row for this VP
        row_num = sheets_service.find_vp_row(request.vp_code)
        if not row_num:
            raise HTTPException(status_code=404, detail=f"VP {request.vp_code} not found")

        # Get existing notes
        existing_notes = sheets_service.get_vp_cell_value(row_num, 'Q')

        # Format: [timestamp|type|author] content
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        new_entry = f"[{timestamp}|{request.comment_type}|{request.author}] {request.comment}"

        if existing_notes:
            updated_notes = f"{new_entry}\n---\n{existing_notes}"  # New comment first
        else:
            updated_notes = new_entry

        # Update the notes column and last updated
        updates = {
            'Q': updated_notes,  # Meeting_Notes
            'AL': datetime.now().isoformat(),  # Last_Updated
            'AM': request.author,  # Updated_By
        }
        sheets_service.update_vp_row(row_num, updates)

        return {
            "success": True,
            "message": "Comment posted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== BDO Tracker Endpoints ====================

@app.get("/api/bdo/all")
async def get_all_bdo(request: Request):
    """Get all BDO tracking data"""
    require_role(request, {'admin', 'vp'})
    try:
        sheets_service = GoogleSheetsService()
        data = sheets_service.get_bdo_tracker_data()
        return data
    except Exception as e:
        # Return empty list if BDO-Tracker sheet doesn't exist
        return []


@app.post("/api/bdo/update")
async def update_bdo(request: BDOUpdateRequest):
    """Update BDO stage for a block"""
    try:
        sheets_service = GoogleSheetsService()
        success = sheets_service.update_bdo_stage(request.block, request.new_stage)

        if success:
            return {"success": True, "message": f"Updated {request.block} BDO to {request.new_stage}"}
        else:
            raise HTTPException(status_code=404, detail=f"Block {request.block} not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bdo/init")
async def init_bdo_tracker():
    """Initialize BDO-Tracker sheet from DRS-Tracker data (one-time setup)"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.init_bdo_tracker()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Meeting Manager Endpoints ====================

class MeetingCreateRequest(BaseModel):
    """Request model for creating a meeting/event"""
    vp_code: str
    vp_name: str
    block: str
    event_type: str  # calendar_event, task_reminder, milestone
    event_date: str  # YYYY-MM-DD
    event_time: Optional[str] = "10:00"  # HH:MM format
    duration_minutes: Optional[int] = 60
    assigned_to: Optional[str] = ""
    notes: Optional[str] = ""
    secretary_name: Optional[str] = ""
    secretary_phone: Optional[Union[str, int]] = ""
    event_title: Optional[str] = ""  # Custom title (e.g., "Panch Meeting", "First Meeting")
    horeca_place_id: Optional[str] = ""  # HoReCa place ID (when scheduling for HoReCa)
    horeca_name: Optional[str] = ""  # HoReCa name (when scheduling for HoReCa)
    # Deprecated calendar fields — kept for API compat, ignored
    create_calendar: Optional[bool] = False
    send_notifications: Optional[bool] = False
    force_new_event: Optional[bool] = False


class MeetingUpdateRequest(BaseModel):
    """Request model for updating a meeting"""
    meeting_id: str
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None  # scheduled, completed, cancelled
    notes: Optional[str] = None
    event_title: Optional[str] = None  # Meeting title (First Meeting, Panch Meeting, etc.)


@app.get("/api/meetings/all")
async def get_all_meetings():
    """Get all meeting assignments (past and future)"""
    try:
        sheets_service = GoogleSheetsService()
        data = sheets_service.get_meeting_assignments_data()
        return data
    except Exception as e:
        return []


@app.post("/api/meetings/create")
async def create_meeting(request: MeetingCreateRequest):
    """Create a new meeting/event (in-app only, no Google Calendar)."""
    try:
        sheets_service = GoogleSheetsService()

        event_title = request.event_title or ("Reminder" if request.event_type == 'task_reminder' else "Meeting")

        # Create meeting assignment in sheet
        meeting_data = {
            'vp_code': request.vp_code,
            'vp_name': request.vp_name,
            'block': request.block,
            'event_type': request.event_type,
            'event_date': request.event_date,
            'event_time': request.event_time or '10:00',
            'assigned_to': request.assigned_to or '',
            'calendar_event_id': '',
            'notes': request.notes or '',
            'status': 'scheduled',
            'event_title': event_title,
        }

        result = sheets_service.create_meeting_assignment(meeting_data)

        return {
            "success": True,
            "meeting_id": result.get('meeting_id'),
            "calendar_event_id": "",
            "calendar_event_link": "",
            "updated_existing": False,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/meetings/update")
async def update_meeting(request: MeetingUpdateRequest):
    """Update an existing meeting"""
    try:
        sheets_service = GoogleSheetsService()

        updates = {}
        if request.event_date:
            updates['event_date'] = request.event_date
        if request.event_time:
            updates['event_time'] = request.event_time
        if request.assigned_to is not None:
            updates['assigned_to'] = request.assigned_to
        if request.status:
            updates['status'] = request.status
        if request.notes is not None:
            updates['notes'] = request.notes
        if request.event_title is not None:
            updates['event_title'] = request.event_title

        success = sheets_service.update_meeting_assignment(request.meeting_id, updates)

        if not success:
            raise HTTPException(status_code=404, detail=f"Meeting {request.meeting_id} not found")

        return {
            "success": True,
            "message": f"Meeting {request.meeting_id} updated",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str):
    """Delete a meeting (marks as cancelled)"""
    try:
        sheets_service = GoogleSheetsService()

        # Mark meeting as cancelled in sheet
        success = sheets_service.delete_meeting_assignment(meeting_id)

        if success:
            return {"success": True, "message": "Meeting deleted"}
        else:
            raise HTTPException(status_code=404, detail="Meeting not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/meetings/init")
async def init_meeting_assignments():
    """Initialize Meeting-Assignments sheet (one-time setup)"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.init_meeting_assignments()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/migrate/sync-stage-numbers")
async def sync_stage_numbers():
    """One-time: Fix Stage_Number column to match Current_Stage for all VPs"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.sync_stage_numbers()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/migrate/noc-tracking-headers")
async def add_noc_tracking_headers():
    """Add NOC tracking headers (NOC_Email_Sent_Date, Email_Read, Signed_NOC_Date) to DRS-Tracker sheet"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.add_noc_tracking_headers()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/meetings/add-event-title-header")
async def add_event_title_header():
    """Add Event_Title header to Meeting-Assignments sheet (migration for existing sheets)"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.add_event_title_header()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/legacy/import")
async def import_legacy_notes():
    """Import legacy meeting notes from markdown file (one-time operation)"""
    import re
    import time

    try:
        sheets_service = GoogleSheetsService()

        # Path to legacy notes file
        legacy_file = Path(__file__).parent.parent.parent / "Requirements" / "Older meeting notes.md"

        if not legacy_file.exists():
            return {"success": False, "message": "Legacy notes file not found", "imported": 0}

        with open(legacy_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Get all VPs for name matching (single API call)
        all_vps = sheets_service.get_tracker_data()
        vp_map = {vp['vpName'].lower().strip(): vp for vp in all_vps}

        # Build vpCode to row mapping from the data (avoid individual lookups)
        # Row numbers: header is row 1, data starts at row 2
        vp_row_map = {}
        for idx, vp in enumerate(all_vps):
            vp_row_map[vp['vpCode']] = idx + 2  # +2 because header is row 1

        # Parse entries (format: 🏛️ Follow-up: [VP Name] VP ([Block]))
        entries = re.split(r'\n?🏛️ Follow-up:', content)

        # Collect all updates to batch them
        updates_to_make = []
        skipped = []

        for entry in entries:
            if not entry.strip():
                continue

            # Extract VP name from first line
            lines = entry.strip().split('\n')
            first_line = lines[0].strip()

            # Parse: "VP Name VP (BLOCK)"
            vp_match = re.match(r'^([^(]+)\s*VP\s*\(([^)]+)\)', first_line)
            if not vp_match:
                # Try alternate format: "VP Name (BLOCK)"
                vp_match = re.match(r'^([^(]+)\s*\(([^)]+)\)', first_line)

            if not vp_match:
                skipped.append(f"Could not parse: {first_line[:50]}")
                continue

            vp_name_raw = vp_match.group(1).strip()
            block = vp_match.group(2).strip().upper()

            # Clean up VP name (remove trailing "VP", extra spaces, etc.)
            vp_name = re.sub(r'\s*VP$', '', vp_name_raw, flags=re.IGNORECASE).strip()

            # Extract notes (after "Notes: ")
            full_text = '\n'.join(lines)
            notes_match = re.search(r'Notes:\s*(.+?)(?:---\s*Created by Goa DRS Tracker|$)', full_text, re.DOTALL)

            if not notes_match:
                continue

            notes = notes_match.group(1).strip()

            # Skip entries with no meaningful content
            if not notes or notes.lower() in ['no additional notes', 'no notes', '-']:
                continue

            # Clean up notes
            notes = notes.replace('--- Created by Goa DRS Tracker', '').strip()
            if not notes:
                continue

            # Find matching VP in sheet (try exact match first, then fuzzy)
            matched_vp = None

            # Exact match
            if vp_name.lower() in vp_map:
                matched_vp = vp_map[vp_name.lower()]
            else:
                # Try partial/fuzzy match
                for vp_key, vp_data in vp_map.items():
                    if vp_name.lower() in vp_key or vp_key in vp_name.lower():
                        if vp_data.get('block', '').upper() == block:
                            matched_vp = vp_data
                            break

            if not matched_vp:
                skipped.append(f"VP not found: {vp_name} ({block})")
                continue

            # Get row number from our map
            row_num = vp_row_map.get(matched_vp['vpCode'])
            if not row_num:
                skipped.append(f"Row not found for: {matched_vp['vpName']}")
                continue

            # Get existing notes from the cached data
            existing_notes = matched_vp.get('meetingNotes', '') or ''

            # Format legacy entry
            legacy_entry = f"[Legacy (Pre-Feb 2025)|legacy|Team] {notes}"

            # Check if this exact legacy note already exists (avoid duplicates)
            if notes in existing_notes:
                skipped.append(f"Already imported: {matched_vp['vpName']}")
                continue

            # Append legacy note at the END (oldest last)
            if existing_notes:
                updated_notes = f"{existing_notes}\n---\n{legacy_entry}"
            else:
                updated_notes = legacy_entry

            updates_to_make.append({
                'row': row_num,
                'notes': updated_notes,
                'vp_name': matched_vp['vpName']
            })

        # Now batch update with delays to avoid rate limits
        imported_count = 0
        for i, update in enumerate(updates_to_make):
            try:
                sheets_service.update_vp_row(update['row'], {'Q': update['notes']})
                imported_count += 1

                # Add delay every 5 updates to stay under rate limit
                if (i + 1) % 5 == 0 and i < len(updates_to_make) - 1:
                    time.sleep(2)  # 2 second delay every 5 updates
            except Exception as e:
                skipped.append(f"Failed to update {update['vp_name']}: {str(e)[:50]}")

        return {
            "success": True,
            "message": f"Imported {imported_count} legacy notes",
            "imported": imported_count,
            "total_found": len(updates_to_make),
            "skipped": skipped[:20]  # Limit to first 20 skipped items
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RVM Deployment Endpoints ====================

@app.get("/api/deployment/summary")
async def get_deployment_summary(request: Request):
    """Get RVM deployment summary: locations, blocks, CP plan data"""
    require_auth(request)
    try:
        sheets_service = GoogleSheetsService()
        locations = sheets_service.get_deployment_data()
        blocks = sorted(list(set(l['block'] for l in locations if l.get('block'))))
        cp_data = sheets_service.get_cp_tab_data()
        plan_total = sheets_service.get_planned_rvms_total()
        return {
            "locations": locations,
            "blocks": blocks,
            "cpData": cp_data,
            "planTotal": plan_total,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Analytics / Activity Log Endpoints ====================

class AnalyticsEvent(BaseModel):
    event_type: str
    page: str = ''
    element: str = ''
    value: Union[str, int, float] = ''
    session_id: str = ''

@app.post("/api/analytics/track")
async def track_analytics_event(event: AnalyticsEvent, request: Request):
    """Record a frontend analytics event (page view, scroll, click)."""
    user = get_session_user(request)
    if not user:
        return {"ok": False}
    try:
        ua = request.headers.get('user-agent', '')
        device = _parse_device_info(ua)
        fwd = request.headers.get('x-forwarded-for')
        ip = fwd.split(',')[0].strip() if fwd else (request.client.host if request.client else 'unknown')
        GoogleSheetsService().log_analytics_event({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user_email': user['email'],
            'user_name': user['name'],
            'event_type': event.event_type,
            'page': event.page,
            'element': event.element,
            'value': str(event.value),
            'session_id': event.session_id,
            'device_type': device['device_type'],
            'browser': device['browser'],
            'os': device['os'],
            'ip': ip,
        })
    except Exception:
        pass
    return {"ok": True}

@app.get("/api/analytics/log")
async def get_activity_log(request: Request, limit: int = 300):
    """Fetch activity log — superadmin only."""
    user = require_auth(request)
    if user.get('email') != SUPERADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        events = GoogleSheetsService().get_analytics_log(limit=limit)
        return {"events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/profiles")
async def get_user_profiles_analytics(request: Request):
    """Fetch aggregated per-user behaviour profiles — superadmin only."""
    user = require_auth(request)
    if user.get('email') != SUPERADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        profiles = GoogleSheetsService().get_analytics_profiles()
        return {"profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Training Progress Endpoints ====================

class TrainingSyncRequest(BaseModel):
    """Request model for syncing training progress"""
    total_xp: int = 0
    total_stars: int = 0
    modules_completed: int = 0
    chapters_completed: int = 0
    total_time_seconds: int = 0
    current_module: int = 0
    progress_json: str = '{}'


@app.post("/api/training/init")
async def init_training_progress():
    """Initialize Training-Progress sheet (one-time setup)"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.init_training_progress()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/training/progress")
async def get_training_progress(request: Request):
    """Get training progress for the authenticated user from Google Sheet"""
    user = require_auth(request)
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.get_training_progress(email=user.get('email', ''))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/training/sync")
async def sync_training_progress(request: Request, body: TrainingSyncRequest):
    """Sync training progress for the authenticated user"""
    user = require_auth(request)
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.sync_training_progress(
            email=user.get('email', ''),
            name=user.get('name', ''),
            data=body.model_dump()
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/training/leaderboard")
async def get_training_leaderboard(request: Request):
    """Get training leaderboard"""
    require_auth(request)
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.get_training_leaderboard()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/training/reset")
async def reset_training_progress(request: Request, email: str = Form(...)):
    """Admin-only: reset a user's training progress to zero"""
    user = require_role(request, {'admin'})
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.sync_training_progress(
            email=email,
            name='',  # Will be updated on next real sync
            data={'total_xp': 0, 'total_stars': 0, 'modules_completed': 0,
                  'chapters_completed': 0, 'total_time_seconds': 0,
                  'current_module': 0, 'progress_json': '{}'}
        )
        return {'success': True, 'message': f'Reset training for {email}', **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HoReCa CRM Endpoints ====================

class HoReCaOutreachUpdate(BaseModel):
    """Request model for updating HoReCa outreach fields"""
    place_id: str
    outreach_status: Optional[str] = None
    owner_name: Optional[str] = None
    owner_number: Optional[str] = None
    spoc_name: Optional[str] = None
    spoc_number: Optional[str] = None
    spoc_designation: Optional[str] = None
    outreach_email: Optional[str] = None
    bottles_per_week: Optional[str] = None
    note: Optional[str] = None
    follow_up_date: Optional[str] = None
    assigned_to: Optional[str] = None
    updated_by: str = 'Team'


@app.get("/api/horeca/crm")
async def get_horeca_crm(
    request: Request,
    search: str = '',
    status: str = '',
    type: str = '',
    zone: str = '',
    city: str = '',
    assigned_to: str = '',
    page: int = 1,
    page_size: int = 50,
):
    """Get filtered, paginated HoReCa CRM data"""
    require_role(request, {'admin', 'horeca'})
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.get_horeca_crm_data(
            search=search, status=status, htype=type,
            zone=zone, city=city, assigned_to=assigned_to,
            page=page, page_size=page_size,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/horeca/crm/update")
async def update_horeca_crm(request: HoReCaOutreachUpdate):
    """Update outreach fields for a HoReCa record"""
    try:
        sheets_service = GoogleSheetsService()

        updates = {}
        for field in ['outreach_status', 'owner_name', 'owner_number', 'spoc_name',
                       'spoc_number', 'spoc_designation', 'outreach_email',
                       'bottles_per_week', 'follow_up_date', 'assigned_to']:
            val = getattr(request, field, None)
            if val is not None:
                updates[field] = val

        # Note is handled separately in the service
        if request.note:
            updates['note'] = request.note

        result = sheets_service.update_horeca_outreach(
            place_id=request.place_id,
            updates=updates,
            author=request.updated_by,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/horeca/crm/summary")
async def get_horeca_crm_summary(assigned_to: str = ''):
    """Get HoReCa CRM dashboard summary"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.get_horeca_crm_summary(assigned_to=assigned_to)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/horeca/crm/statuses")
async def get_horeca_crm_statuses():
    """Get valid outreach status list"""
    return {'statuses': GoogleSheetsService.HORECA_OUTREACH_STATUSES}


@app.post("/api/horeca/crm/init")
async def init_horeca_crm():
    """One-time: Add CRM column headers to the HoReCa sheet"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.add_horeca_crm_headers()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/horeca/crm/migrate-assignment")
async def migrate_horeca_assignment_headers():
    """One-time: Add Assigned_To and Assignment_History headers (BN-BO)"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.migrate_horeca_assignment_headers()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class HoReCaAddLeadRequest(BaseModel):
    """Request model for adding a new HoReCa lead"""
    name: str
    type: Optional[str] = ''
    address: Optional[str] = ''
    city: Optional[str] = ''
    pincode: Optional[str] = ''
    rating: Optional[str] = ''
    lat: Optional[str] = ''
    lng: Optional[str] = ''
    owner_name: Optional[str] = ''
    owner_phone: Optional[str] = ''
    spoc_name: Optional[str] = ''
    spoc_phone: Optional[str] = ''
    spoc_designation: Optional[str] = ''
    email: Optional[str] = ''
    serves_beer: Optional[bool] = False
    serves_wine: Optional[bool] = False
    bottles_per_week: Optional[str] = ''
    status: Optional[str] = 'Call not answered'
    assigned_to: Optional[str] = ''
    note: Optional[str] = ''


@app.post("/api/horeca/crm/add")
async def add_horeca_lead(request: HoReCaAddLeadRequest):
    """Add a new HoReCa lead manually"""
    try:
        sheets_service = GoogleSheetsService()
        result = sheets_service.add_horeca_record(request.dict())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Reverse Logistics Routes ====================

from ..services.reverse_logistics import (
    rl_get_months, rl_run_model, rl_get_mom,
    rl_save_defaults, rl_load_defaults, rl_get_sensitivity,
)

RL_HTML_PATH = FRONTEND_DIR / "reverse-logistics.html"


@app.get("/rl")
async def serve_rl_page():
    """Serve the Reverse Logistics standalone HTML page"""
    if RL_HTML_PATH.exists():
        return FileResponse(str(RL_HTML_PATH))
    raise HTTPException(status_code=404, detail="Reverse Logistics page not found")


@app.get("/api/rl/months")
async def api_rl_months():
    """Return available months for Reverse Logistics model"""
    return rl_get_months()


@app.get("/api/rl/run")
async def api_rl_run_get(month: str = None):
    """Run RL model for a month (GET — default params)"""
    try:
        return rl_run_model(month=month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/rl/run")
async def api_rl_run_post(request: Request, month: str = None):
    """Run RL model with parameter overrides (POST)"""
    body = await request.json()
    overrides = body.get("overrides", {})
    try:
        return rl_run_model(month=month, overrides=overrides if overrides else None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/rl/mom")
async def api_rl_mom():
    """Return month-over-month fleet requirement table"""
    return rl_get_mom()


@app.post("/api/rl/save-defaults")
async def api_rl_save_defaults(request: Request):
    """Save RL parameter defaults"""
    data = await request.json()
    return rl_save_defaults(data)


@app.get("/api/rl/load-defaults")
async def api_rl_load_defaults():
    """Load saved RL parameter defaults"""
    return rl_load_defaults()


@app.get("/api/rl/sensitivity")
async def api_rl_sensitivity(refresh: str = None):
    """Run aggregate sensitivity analysis (cached on disk)"""
    return rl_get_sensitivity(refresh=bool(refresh))


# ==================== SPA Catch-All Route ====================
# Must be the LAST route — serves index.html for all frontend paths
# so that URL-based routing (e.g. /VPs, /Dashboard, /Learning/module-0) works
FRONTEND_ROUTES = {'VPs', 'ULBs', 'Dashboard', 'Meetings', 'Escalation', 'Today', 'HoReCa', 'Learning'}

@app.get("/{path:path}")
async def spa_catch_all(path: str):
    """Serve index.html for all frontend routes (SPA catch-all)"""
    # Serve Reverse Logistics standalone page
    if path == 'rl':
        rl_path = FRONTEND_DIR / "reverse-logistics.html"
        if rl_path.exists():
            return FileResponse(str(rl_path))
        raise HTTPException(status_code=404, detail="Reverse Logistics page not found")
    # Don't intercept /api, /static, or file requests (e.g. .json, .js, .css)
    if path.startswith('api/') or path.startswith('static/') or '.' in path.split('/')[-1]:
        raise HTTPException(status_code=404, detail="Not found")
    # Serve index.html for known frontend routes and Learning sub-routes
    frontend_path = FRONTEND_DIR / "index.html"
    if frontend_path.exists():
        return FileResponse(str(frontend_path))
    raise HTTPException(status_code=404, detail="Not found")


