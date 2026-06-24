"""
Main tracker service that orchestrates the VP tracking workflow
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from ..config.settings import (
    Settings, DeploymentStage, STAGE_ORDER, STAGE_LABELS, GOA_BLOCKS
)
from ..models.entities import (
    VillagePanchayat, MeetingUpdate, BlockSummary, OverallSummary
)
from .ai_processor import AIProcessor, VoiceTranscriber
from .google_services import GoogleSheetsService, GmailService

settings = Settings()


class VPTracker:
    """
    Main tracker service for Village Panchayat collection point mapping.

    This service:
    1. Processes voice/text input from field team
    2. Extracts structured data using AI
    3. Updates Google Sheets tracker
    4. Creates calendar events for follow-ups
    5. Sends emails and notifications
    6. Provides analytics and summaries
    """

    def __init__(self):
        """Initialize tracker with all required services"""
        # AI services are optional - only needed for voice/AI processing
        try:
            self.ai_processor = AIProcessor()
            self.voice_transcriber = VoiceTranscriber()
        except ValueError:
            # AI API keys not configured - basic tracking still works
            self.ai_processor = None
            self.voice_transcriber = None

        try:
            self.sheets_service = GoogleSheetsService()
        except Exception:
            self.sheets_service = None

        try:
            self.gmail_service = GmailService()
        except Exception:
            self.gmail_service = None

    async def process_field_update(
        self,
        input_text: str = None,
        audio_file: str = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process a field update from voice or text input.

        This is the main entry point for field team to submit updates.

        Args:
            input_text: Direct text input from the field
            audio_file: Path to audio file for transcription
            context: Optional context (vp_name, block_name, user_id, etc.)

        Returns:
            Dictionary with processed data and actions taken
        """
        context = context or {}
        result = {
            'success': False,
            'message': '',
            'extracted_data': None,
            'actions_taken': [],
            'follow_up_created': False,
        }

        try:
            # Step 1: Get text input (transcribe if audio)
            if audio_file:
                if not self.voice_transcriber:
                    raise ValueError("Voice transcription requires AI API key. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")
                text = self.voice_transcriber.transcribe_file(audio_file)
                result['actions_taken'].append(f"Transcribed audio: {text[:100]}...")
            elif input_text:
                text = input_text
            else:
                raise ValueError("Either input_text or audio_file is required")

            # Step 2: Process with AI to extract data points
            if not self.ai_processor:
                raise ValueError("AI processing requires API key. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")
            meeting_update = await self.ai_processor.process_input(text, context)
            result['extracted_data'] = meeting_update.model_dump()

            # Step 3: Update Google Sheets
            block_name = meeting_update.block_name or context.get('block_name')
            if meeting_update.village_panchayat_name and block_name:
                self.sheets_service.apply_meeting_update(meeting_update, block_name)
                result['actions_taken'].append(
                    f"Updated sheet for {meeting_update.village_panchayat_name}"
                )

            # Calendar integration removed — follow-ups tracked in Meetings tab only

            result['success'] = True
            result['message'] = "Update processed successfully"

        except Exception as e:
            result['message'] = f"Error processing update: {str(e)}"

        return result

    def update_stage(
        self,
        vp_name: str,
        block_name: str,
        new_stage: DeploymentStage,
        notes: str = None
    ):
        """
        Update the stage for a village panchayat.

        Args:
            vp_name: Name of the village panchayat
            block_name: Name of the block
            new_stage: New deployment stage
            notes: Optional notes for this stage change
        """
        worksheet = self.sheets_service.get_worksheet()
        row_num = self.sheets_service.find_vp_row(worksheet, vp_name, block_name)

        if not row_num:
            raise ValueError(f"VP '{vp_name}' not found in block '{block_name}'")

        # Update stage
        stage_label = STAGE_LABELS.get(new_stage, new_stage.value)
        worksheet.update(f'J{row_num}', [[stage_label]])

        # Update timestamp
        worksheet.update(f'AD{row_num}', [[datetime.now().strftime("%Y-%m-%d %H:%M")]])

        # Add to notes if provided
        if notes:
            current_notes = worksheet.acell(f'AC{row_num}').value or ""
            note_entry = f"[{datetime.now().strftime('%Y-%m-%d')}] Stage: {stage_label} - {notes}"
            new_notes = f"{current_notes} | {note_entry}" if current_notes else note_entry
            worksheet.update(f'AC{row_num}', [[new_notes]])

    def send_confirmation_email(self, vp_name: str, block_name: str):
        """Send confirmation email after first meeting"""
        worksheet = self.sheets_service.get_worksheet()
        row_num = self.sheets_service.find_vp_row(worksheet, vp_name, block_name)

        if not row_num:
            raise ValueError(f"VP '{vp_name}' not found")

        # Get VP data from sheet
        row = worksheet.row_values(row_num)

        # Check if email exists
        email_idx = list(self.sheets_service.COLUMNS.keys()).index('I')
        email = row[email_idx] if len(row) > email_idx else None

        if not email:
            raise ValueError(f"Email not available for VP '{vp_name}'")

        # Create VP object for email
        block = next((b for b in GOA_BLOCKS if b['name'].lower() == block_name.lower()), None)

        vp = VillagePanchayat(
            block_id=block['id'] if block else 0,
            name=vp_name,
            email_id=email,
            location_address=row[14] if len(row) > 14 else None,  # Column O
        )

        # Send email
        self.gmail_service.send_confirmation_email(vp, block_name)

        # Update stage and email sent date
        self.update_stage(vp_name, block_name, DeploymentStage.EMAIL_SENT)
        worksheet.update(f'T{row_num}', [[date.today().strftime("%Y-%m-%d")]])

    def get_block_summary(self, block_name: str) -> BlockSummary:
        """Get summary statistics for a specific block"""
        worksheet = self.sheets_service.get_worksheet()
        all_data = worksheet.get_all_records()

        block = next((b for b in GOA_BLOCKS if b['name'].lower() == block_name.lower()), None)
        if not block:
            raise ValueError(f"Block '{block_name}' not found")

        # Filter for this block
        block_vps = [r for r in all_data if r.get('block_name', '').lower() == block_name.lower()]

        # Calculate stage counts
        stage_counts = {}
        for stage in DeploymentStage:
            label = STAGE_LABELS.get(stage, stage.value)
            stage_counts[stage.value] = sum(
                1 for r in block_vps if r.get('current_stage') == label
            )

        total = len(block_vps)

        return BlockSummary(
            block_id=block['id'],
            block_name=block['name'],
            district=block['district'],
            bdo_meeting_done=True,  # Would need separate tracking

            total_vps=total,
            yet_to_meet=stage_counts.get(DeploymentStage.YET_TO_MEET.value, 0),
            meetings_done=sum(
                stage_counts.get(s.value, 0)
                for s in STAGE_ORDER[STAGE_ORDER.index(DeploymentStage.FIRST_MEETING_DONE):]
            ),
            location_finalized=sum(
                stage_counts.get(s.value, 0)
                for s in STAGE_ORDER[STAGE_ORDER.index(DeploymentStage.LOCATION_FINALIZED):]
            ),
            noc_received=sum(
                stage_counts.get(s.value, 0)
                for s in STAGE_ORDER[STAGE_ORDER.index(DeploymentStage.NOC_RECEIVED):]
            ),
            agreements_signed=sum(
                stage_counts.get(s.value, 0)
                for s in STAGE_ORDER[STAGE_ORDER.index(DeploymentStage.SERVICE_AGREEMENT_SIGNED):]
            ),
            devices_installed=stage_counts.get(DeploymentStage.DEVICE_INSTALLED.value, 0),

            completion_percentage=(
                stage_counts.get(DeploymentStage.DEVICE_INSTALLED.value, 0) / total * 100
                if total > 0 else 0
            ),
        )

    def get_overall_summary(self) -> OverallSummary:
        """Get overall deployment summary across all blocks"""
        worksheet = self.sheets_service.get_worksheet()
        all_data = worksheet.get_all_records()

        total = len(all_data)

        # Count by stage
        stage_counts = {}
        for stage in DeploymentStage:
            label = STAGE_LABELS.get(stage, stage.value)
            stage_counts[stage.value] = sum(
                1 for r in all_data if r.get('current_stage') == label
            )

        # Count blocks touched
        blocks_with_data = set(r.get('block_name') for r in all_data if r.get('block_name'))

        # Infrastructure counts
        electricity_ready = sum(
            1 for r in all_data if r.get('electricity_status') == 'available'
        )
        internet_ready = sum(
            1 for r in all_data if r.get('internet_status') == 'available'
        )
        infra_complete = sum(
            1 for r in all_data
            if r.get('electricity_status') == 'available'
            and r.get('internet_status') == 'available'
        )

        # Document counts
        emails_sent = sum(
            1 for r in all_data if r.get('email_sent_date')
        )
        nocs_received = sum(
            1 for r in all_data if r.get('noc_received_date')
        )
        agreements_signed = sum(
            1 for r in all_data if r.get('sa_signed_date')
        )

        # Deployment counts
        devices_deployed = stage_counts.get(DeploymentStage.DEVICE_DEPLOYED.value, 0)
        devices_installed = stage_counts.get(DeploymentStage.DEVICE_INSTALLED.value, 0)

        return OverallSummary(
            total_blocks=12,
            blocks_touched=len(blocks_with_data),
            total_vps=total,
            stage_counts=stage_counts,
            electricity_ready=electricity_ready,
            internet_ready=internet_ready,
            infra_complete=infra_complete,
            emails_sent=emails_sent,
            nocs_received=nocs_received,
            agreements_signed=agreements_signed,
            devices_deployed=devices_deployed,
            devices_installed=devices_installed,
            overall_completion_percentage=(
                devices_installed / total * 100 if total > 0 else 0
            ),
        )

    def get_pending_followups(self) -> List[Dict]:
        """Get list of VPs with pending follow-ups"""
        worksheet = self.sheets_service.get_worksheet()
        all_data = worksheet.get_all_records()

        today = date.today()
        pending = []

        for row in all_data:
            follow_up_date = row.get('follow_up_date')
            if follow_up_date:
                try:
                    fu_date = datetime.strptime(follow_up_date, "%Y-%m-%d").date()
                    if fu_date <= today:
                        pending.append({
                            'block': row.get('block_name'),
                            'vp_name': row.get('village_panchayat_name'),
                            'follow_up_date': follow_up_date,
                            'reason': row.get('follow_up_reason'),
                            'current_stage': row.get('current_stage'),
                            'secretary_phone': row.get('secretary_phone'),
                        })
                except ValueError:
                    pass

        # Sort by date
        pending.sort(key=lambda x: x['follow_up_date'])
        return pending

    def get_vps_by_stage(self, stage: DeploymentStage) -> List[Dict]:
        """Get all VPs at a specific stage"""
        worksheet = self.sheets_service.get_worksheet()
        all_data = worksheet.get_all_records()

        stage_label = STAGE_LABELS.get(stage, stage.value)

        return [
            {
                'block': row.get('block_name'),
                'vp_name': row.get('village_panchayat_name'),
                'secretary_phone': row.get('secretary_phone'),
                'email': row.get('email_id'),
                'updated_at': row.get('updated_at'),
            }
            for row in all_data
            if row.get('current_stage') == stage_label
        ]
