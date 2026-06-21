"""
Data models for Goa DRS VP CP Mapping system
"""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum

from ..config.settings import DeploymentStage, InfraStatus


class BDO(BaseModel):
    """Block Divisional Officer model"""
    id: int
    name: str
    block_name: str
    district: str
    phone: Optional[str] = None
    email: Optional[str] = None
    meeting_date: Optional[date] = None
    meeting_done: bool = False
    notes: Optional[str] = None


class VillagePanchayat(BaseModel):
    """Village Panchayat model with all tracking data points"""
    id: Optional[int] = None
    block_id: int
    code: Optional[str] = None
    name: str

    # Contact details
    secretary_name: Optional[str] = None
    secretary_phone: Optional[str] = None
    sarpanch_name: Optional[str] = None
    sarpanch_phone: Optional[str] = None
    email_id: Optional[str] = None

    # Location details
    location_address: Optional[str] = None
    location_landmark: Optional[str] = None
    location_gps_lat: Optional[float] = None
    location_gps_lng: Optional[float] = None

    # Infrastructure status
    electricity_status: InfraStatus = InfraStatus.NOT_AVAILABLE
    internet_status: InfraStatus = InfraStatus.NOT_AVAILABLE
    shed_available: bool = False
    flat_surface_available: bool = False

    # Current stage
    current_stage: DeploymentStage = DeploymentStage.YET_TO_MEET

    # Meeting tracking
    first_meeting_date: Optional[date] = None
    panch_meeting_date: Optional[date] = None
    follow_up_date: Optional[date] = None
    follow_up_reason: Optional[str] = None

    # Document status
    email_sent_date: Optional[date] = None
    noc_sent_date: Optional[date] = None
    noc_received_date: Optional[date] = None
    noc_file_url: Optional[str] = None
    service_agreement_sent_date: Optional[date] = None
    service_agreement_signed_date: Optional[date] = None
    service_agreement_url: Optional[str] = None

    # Deployment
    device_deployed_date: Optional[date] = None
    device_installed_date: Optional[date] = None
    device_serial_number: Optional[str] = None

    # Notes and metadata
    meeting_notes: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class MeetingUpdate(BaseModel):
    """Model for recording meeting updates via voice/text"""
    village_panchayat_id: Optional[int] = None
    village_panchayat_name: Optional[str] = None
    block_name: Optional[str] = None

    # Raw input
    raw_input: str
    input_language: Optional[str] = None  # detected language

    # Extracted data points
    secretary_name: Optional[str] = None
    secretary_phone: Optional[str] = None
    sarpanch_name: Optional[str] = None
    sarpanch_phone: Optional[str] = None
    email_id: Optional[str] = None

    # Meeting outcome
    meeting_outcome: Optional[str] = None
    location_identified: bool = False
    location_description: Optional[str] = None

    # Next steps
    follow_up_required: bool = False
    follow_up_date: Optional[date] = None
    follow_up_reason: Optional[str] = None
    panch_meeting_required: bool = False

    # Suggested stage update
    suggested_stage: Optional[DeploymentStage] = None

    # Metadata
    recorded_at: datetime = Field(default_factory=datetime.now)
    recorded_by: Optional[str] = None


class CalendarEvent(BaseModel):
    """Model for Google Calendar event creation"""
    title: str
    description: str
    start_datetime: datetime
    end_datetime: datetime
    attendees: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    village_panchayat_id: Optional[int] = None


class BlockSummary(BaseModel):
    """Summary statistics for a block"""
    block_id: int
    block_name: str
    district: str
    bdo_meeting_done: bool

    total_vps: int
    yet_to_meet: int
    meetings_done: int
    location_finalized: int
    noc_received: int
    agreements_signed: int
    devices_installed: int

    completion_percentage: float


class OverallSummary(BaseModel):
    """Overall deployment summary"""
    total_blocks: int = 12
    blocks_touched: int
    total_vps: int

    # Stage-wise counts
    stage_counts: dict

    # Infrastructure readiness
    electricity_ready: int
    internet_ready: int
    infra_complete: int

    # Document status
    emails_sent: int
    nocs_received: int
    agreements_signed: int

    # Deployment status
    devices_deployed: int
    devices_installed: int

    overall_completion_percentage: float
