"""
Configuration settings for Goa DRS VP CP Mapping system
"""
from enum import Enum
from typing import List
from pydantic_settings import BaseSettings


class DeploymentStage(str, Enum):
    """
    Stages (Milestones) in the RVM deployment pipeline.
    Note: Follow-ups are tracked separately via Meetings, not as a stage.
    Total: 15 milestones
    """
    YET_TO_MEET = "yet_to_meet"                           # 1
    FIRST_MEETING_SCHEDULED = "first_meeting_scheduled"   # 2 (renamed from meeting_scheduled)
    FIRST_MEETING_DONE = "first_meeting_done"             # 3
    PANCH_MEETING_SCHEDULED = "panch_meeting_scheduled"   # 4
    PANCH_MEETING_DONE = "panch_meeting_done"             # 5
    LOCATION_FINALIZED = "location_finalized"             # 6
    EMAIL_SENT = "email_sent"                             # 7
    NOC_PENDING = "noc_pending"                           # 8
    NOC_RECEIVED = "noc_received"                         # 9
    SERVICE_AGREEMENT_SENT = "service_agreement_sent"     # 10
    SERVICE_AGREEMENT_SIGNED = "service_agreement_signed" # 11
    INFRA_PENDING = "infra_pending"                       # 12
    INFRA_COMPLETE = "infra_complete"                     # 13
    DEVICE_DEPLOYED = "device_deployed"                   # 14
    DEVICE_INSTALLED = "device_installed"                 # 15


class InfraStatus(str, Enum):
    """Infrastructure readiness status"""
    NOT_AVAILABLE = "not_available"
    PENDING = "pending"
    AVAILABLE = "available"


# Stage progression order (15 milestones)
STAGE_ORDER = [
    DeploymentStage.YET_TO_MEET,              # 1
    DeploymentStage.FIRST_MEETING_SCHEDULED,  # 2
    DeploymentStage.FIRST_MEETING_DONE,       # 3
    DeploymentStage.PANCH_MEETING_SCHEDULED,  # 4
    DeploymentStage.PANCH_MEETING_DONE,       # 5
    DeploymentStage.LOCATION_FINALIZED,       # 6
    DeploymentStage.EMAIL_SENT,               # 7
    DeploymentStage.NOC_PENDING,              # 8
    DeploymentStage.NOC_RECEIVED,             # 9
    DeploymentStage.SERVICE_AGREEMENT_SENT,   # 10
    DeploymentStage.SERVICE_AGREEMENT_SIGNED, # 11
    DeploymentStage.INFRA_PENDING,            # 12
    DeploymentStage.INFRA_COMPLETE,           # 13
    DeploymentStage.DEVICE_DEPLOYED,          # 14
    DeploymentStage.DEVICE_INSTALLED,         # 15
]

# Human-readable stage labels
STAGE_LABELS = {
    DeploymentStage.YET_TO_MEET: "Yet to Meet",
    DeploymentStage.FIRST_MEETING_SCHEDULED: "First Meeting Scheduled",
    DeploymentStage.FIRST_MEETING_DONE: "First Meeting Done",
    DeploymentStage.PANCH_MEETING_SCHEDULED: "Panch Meeting Scheduled",
    DeploymentStage.PANCH_MEETING_DONE: "Panch Meeting Done",
    DeploymentStage.LOCATION_FINALIZED: "Location Finalized",
    DeploymentStage.EMAIL_SENT: "Email Sent",
    DeploymentStage.NOC_PENDING: "NOC Pending",
    DeploymentStage.NOC_RECEIVED: "NOC Received",
    DeploymentStage.SERVICE_AGREEMENT_SENT: "Service Agreement Sent",
    DeploymentStage.SERVICE_AGREEMENT_SIGNED: "Service Agreement Signed",
    DeploymentStage.INFRA_PENDING: "Infrastructure Pending",
    DeploymentStage.INFRA_COMPLETE: "Infrastructure Complete",
    DeploymentStage.DEVICE_DEPLOYED: "Device Deployed",
    DeploymentStage.DEVICE_INSTALLED: "Device Installed",
}

# Legacy stage mapping for migration (old value -> new value)
STAGE_MIGRATION = {
    "meeting_scheduled": "first_meeting_scheduled",  # Renamed
    "follow_up_required": "first_meeting_done",      # Removed - migrate to first_meeting_done
}


class Settings(BaseSettings):
    """Application settings loaded from environment"""

    # Google API credentials
    google_credentials_file: str = "credentials.json"
    google_refresh_token: str = ""
    google_sheets_id: str = ""
    google_calendar_id: str = "primary"
    google_client_id: str = ""
    google_client_secret: str = ""

    # AI API keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    sarvam_api_key: str = ""  # Sarvam AI for Indian language processing

    # Notification settings
    notification_emails: List[str] = []

    # Database
    database_url: str = "sqlite:///./goa_drs.db"

    # App settings
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Goa blocks configuration
GOA_BLOCKS = [
    {"id": 1, "name": "Tiswadi", "district": "North Goa"},
    {"id": 2, "name": "Bardez", "district": "North Goa"},
    {"id": 3, "name": "Pernem", "district": "North Goa"},
    {"id": 4, "name": "Bicholim", "district": "North Goa"},
    {"id": 5, "name": "Satari", "district": "North Goa"},
    {"id": 6, "name": "Ponda", "district": "North Goa"},
    {"id": 7, "name": "Salcete", "district": "South Goa"},
    {"id": 8, "name": "Mormugao", "district": "South Goa"},
    {"id": 9, "name": "Quepem", "district": "South Goa"},
    {"id": 10, "name": "Sanguem", "district": "South Goa"},
    {"id": 11, "name": "Canacona", "district": "South Goa"},
    {"id": 12, "name": "Dharbandora", "district": "South Goa"},
]

# Data points to capture
REQUIRED_DATA_POINTS = [
    "block_id",
    "village_panchayat_name",
    "secretary_name",
    "secretary_phone",
    "current_stage",
]

OPTIONAL_DATA_POINTS = [
    "village_panchayat_code",
    "sarpanch_name",
    "sarpanch_phone",
    "email_id",
    "location_address",
    "location_gps_lat",
    "location_gps_lng",
    "electricity_status",
    "internet_status",
    "shed_available",
    "flat_surface_available",
    "meeting_notes",
    "follow_up_date",
    "noc_file_url",
    "service_agreement_url",
]
