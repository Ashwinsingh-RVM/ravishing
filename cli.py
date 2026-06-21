#!/usr/bin/env python3
"""
Command-line interface for Goa DRS VP CP Mapping system

Usage:
    python cli.py update --text "Meeting update text..."
    python cli.py update --audio recording.wav
    python cli.py summary
    python cli.py summary --block Bardez
    python cli.py followups
    python cli.py stage --vp "Calangute" --block "Bardez" --stage location_finalized
"""

import argparse
import asyncio
import json
import sys

from src.config.settings import DeploymentStage, GOA_BLOCKS, STAGE_LABELS
from src.services.tracker import VPTracker


def print_json(data):
    """Pretty print JSON data"""
    print(json.dumps(data, indent=2, default=str))


async def process_update(args):
    """Process a field update"""
    tracker = VPTracker()

    context = {
        "village_panchayat_name": args.vp,
        "block_name": args.block,
        "recorded_by": args.user,
    }

    if args.text:
        result = await tracker.process_field_update(input_text=args.text, context=context)
    elif args.audio:
        result = await tracker.process_field_update(audio_file=args.audio, context=context)
    else:
        print("Error: Either --text or --audio is required")
        sys.exit(1)

    print_json(result)


def show_summary(args):
    """Show deployment summary"""
    tracker = VPTracker()

    if args.block:
        summary = tracker.get_block_summary(args.block)
    else:
        summary = tracker.get_overall_summary()

    print_json(summary.model_dump())


def show_followups(args):
    """Show pending follow-ups"""
    tracker = VPTracker()
    followups = tracker.get_pending_followups()

    if followups:
        print(f"\n{'='*60}")
        print(f"PENDING FOLLOW-UPS ({len(followups)} total)")
        print(f"{'='*60}\n")

        for i, fu in enumerate(followups, 1):
            print(f"{i}. {fu['vp_name']} ({fu['block']})")
            print(f"   Date: {fu['follow_up_date']}")
            print(f"   Reason: {fu.get('reason', 'N/A')}")
            print(f"   Phone: {fu.get('secretary_phone', 'N/A')}")
            print()
    else:
        print("No pending follow-ups!")


def update_stage(args):
    """Update stage for a VP"""
    tracker = VPTracker()

    try:
        stage = DeploymentStage(args.stage)
    except ValueError:
        print(f"Invalid stage: {args.stage}")
        print(f"Valid stages: {[s.value for s in DeploymentStage]}")
        sys.exit(1)

    tracker.update_stage(
        vp_name=args.vp,
        block_name=args.block,
        new_stage=stage,
        notes=args.notes
    )

    print(f"Stage updated to: {STAGE_LABELS[stage]}")


def show_stages(args):
    """List all stages"""
    print("\nDeployment Stages:")
    print("-" * 40)
    for i, stage in enumerate(DeploymentStage, 1):
        print(f"{i:2}. {stage.value:30} - {STAGE_LABELS[stage]}")


def show_blocks(args):
    """List all blocks"""
    print("\nGoa Blocks:")
    print("-" * 50)
    print(f"{'ID':<4} {'Block':<15} {'District':<12}")
    print("-" * 50)
    for block in GOA_BLOCKS:
        print(f"{block['id']:<4} {block['name']:<15} {block['district']:<12}")


def main():
    parser = argparse.ArgumentParser(
        description="Goa DRS Village Panchayat Collection Point Mapping CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Update command
    update_parser = subparsers.add_parser("update", help="Process a field update")
    update_parser.add_argument("--text", "-t", help="Text input")
    update_parser.add_argument("--audio", "-a", help="Audio file path")
    update_parser.add_argument("--vp", help="Village Panchayat name")
    update_parser.add_argument("--block", "-b", help="Block name")
    update_parser.add_argument("--user", "-u", help="User/recorder name")

    # Summary command
    summary_parser = subparsers.add_parser("summary", help="Show deployment summary")
    summary_parser.add_argument("--block", "-b", help="Block name (for block-specific summary)")

    # Follow-ups command
    subparsers.add_parser("followups", help="Show pending follow-ups")

    # Stage command
    stage_parser = subparsers.add_parser("stage", help="Update VP stage")
    stage_parser.add_argument("--vp", required=True, help="Village Panchayat name")
    stage_parser.add_argument("--block", "-b", required=True, help="Block name")
    stage_parser.add_argument("--stage", "-s", required=True, help="New stage")
    stage_parser.add_argument("--notes", "-n", help="Notes for stage change")

    # List stages
    subparsers.add_parser("stages", help="List all deployment stages")

    # List blocks
    subparsers.add_parser("blocks", help="List all Goa blocks")

    args = parser.parse_args()

    if args.command == "update":
        asyncio.run(process_update(args))
    elif args.command == "summary":
        show_summary(args)
    elif args.command == "followups":
        show_followups(args)
    elif args.command == "stage":
        update_stage(args)
    elif args.command == "stages":
        show_stages(args)
    elif args.command == "blocks":
        show_blocks(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
