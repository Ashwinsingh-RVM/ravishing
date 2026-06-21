"""
Tests for data models
"""
import pytest
from datetime import date, datetime

import sys
sys.path.insert(0, '..')

from src.config.settings import DeploymentStage, InfraStatus, GOA_BLOCKS
from src.models.entities import VillagePanchayat, MeetingUpdate, BlockSummary


class TestDeploymentStage:
    """Tests for DeploymentStage enum"""

    def test_all_stages_exist(self):
        """Verify all expected stages are defined"""
        expected_stages = [
            'yet_to_meet', 'meeting_scheduled', 'first_meeting_done',
            'follow_up_required', 'panch_meeting_scheduled', 'panch_meeting_done',
            'location_finalized', 'email_sent', 'noc_pending', 'noc_received',
            'service_agreement_sent', 'service_agreement_signed',
            'infra_pending', 'infra_complete', 'device_deployed', 'device_installed'
        ]

        actual_stages = [s.value for s in DeploymentStage]
        assert set(expected_stages) == set(actual_stages)

    def test_stage_count(self):
        """Verify we have 16 stages"""
        assert len(DeploymentStage) == 16


class TestGoaBlocks:
    """Tests for Goa blocks configuration"""

    def test_twelve_blocks(self):
        """Verify we have 12 blocks"""
        assert len(GOA_BLOCKS) == 12

    def test_block_structure(self):
        """Verify each block has required fields"""
        for block in GOA_BLOCKS:
            assert 'id' in block
            assert 'name' in block
            assert 'district' in block

    def test_districts(self):
        """Verify blocks are divided into North and South Goa"""
        districts = set(b['district'] for b in GOA_BLOCKS)
        assert districts == {'North Goa', 'South Goa'}

    def test_north_goa_blocks(self):
        """Verify North Goa has 6 blocks"""
        north_blocks = [b for b in GOA_BLOCKS if b['district'] == 'North Goa']
        assert len(north_blocks) == 6

    def test_south_goa_blocks(self):
        """Verify South Goa has 6 blocks"""
        south_blocks = [b for b in GOA_BLOCKS if b['district'] == 'South Goa']
        assert len(south_blocks) == 6


class TestVillagePanchayat:
    """Tests for VillagePanchayat model"""

    def test_create_basic_vp(self):
        """Test creating a VP with minimal data"""
        vp = VillagePanchayat(
            block_id=1,
            name="Test Panchayat"
        )
        assert vp.name == "Test Panchayat"
        assert vp.block_id == 1
        assert vp.current_stage == DeploymentStage.YET_TO_MEET

    def test_vp_with_contact_details(self):
        """Test creating a VP with contact information"""
        vp = VillagePanchayat(
            block_id=2,
            name="Calangute",
            secretary_name="John Doe",
            secretary_phone="9876543210",
            sarpanch_name="Jane Doe",
            sarpanch_phone="9123456789",
            email_id="calangute.vp@gov.in"
        )

        assert vp.secretary_name == "John Doe"
        assert vp.secretary_phone == "9876543210"
        assert vp.sarpanch_name == "Jane Doe"
        assert vp.email_id == "calangute.vp@gov.in"

    def test_vp_stage_transition(self):
        """Test updating VP stage"""
        vp = VillagePanchayat(block_id=1, name="Test")
        vp.current_stage = DeploymentStage.FIRST_MEETING_DONE

        assert vp.current_stage == DeploymentStage.FIRST_MEETING_DONE

    def test_vp_infrastructure_status(self):
        """Test infrastructure status fields"""
        vp = VillagePanchayat(
            block_id=1,
            name="Test",
            electricity_status=InfraStatus.AVAILABLE,
            internet_status=InfraStatus.PENDING,
            shed_available=True,
            flat_surface_available=True
        )

        assert vp.electricity_status == InfraStatus.AVAILABLE
        assert vp.internet_status == InfraStatus.PENDING
        assert vp.shed_available is True


class TestMeetingUpdate:
    """Tests for MeetingUpdate model"""

    def test_create_meeting_update(self):
        """Test creating a meeting update"""
        update = MeetingUpdate(
            raw_input="Met secretary today. Location identified near market.",
            village_panchayat_name="Test VP",
            block_name="Bardez"
        )

        assert update.raw_input is not None
        assert update.village_panchayat_name == "Test VP"

    def test_meeting_update_with_extracted_data(self):
        """Test meeting update with extracted fields"""
        update = MeetingUpdate(
            raw_input="Secretary name is Ramesh, phone 9876543210",
            secretary_name="Ramesh",
            secretary_phone="9876543210",
            location_identified=True,
            suggested_stage=DeploymentStage.LOCATION_FINALIZED
        )

        assert update.secretary_name == "Ramesh"
        assert update.secretary_phone == "9876543210"
        assert update.location_identified is True


class TestBlockSummary:
    """Tests for BlockSummary model"""

    def test_create_block_summary(self):
        """Test creating a block summary"""
        summary = BlockSummary(
            block_id=1,
            block_name="Tiswadi",
            district="North Goa",
            bdo_meeting_done=True,
            total_vps=15,
            yet_to_meet=5,
            meetings_done=10,
            location_finalized=6,
            noc_received=4,
            agreements_signed=3,
            devices_installed=2,
            completion_percentage=13.33
        )

        assert summary.total_vps == 15
        assert summary.devices_installed == 2
        assert summary.completion_percentage == 13.33


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
