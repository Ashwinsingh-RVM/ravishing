"""
AI-powered text/voice processing service for extracting meeting data points
Supports input in Marathi, Hindi, and English
"""
import json
import re
from typing import Optional, Dict, Any
from datetime import datetime, date
from langdetect import detect

from ..models.entities import MeetingUpdate, DeploymentStage
from ..config.settings import Settings

# Initialize settings
settings = Settings()


class AIProcessor:
    """Process voice/text input to extract structured data points"""

    SYSTEM_PROMPT = """You are an assistant helping to extract structured data from meeting notes
about Village Panchayat visits for the Goa DRS (Deposit Return Scheme) RVM deployment project.

The input may be in Marathi, Hindi, or English. Extract the following data points if mentioned:

1. Secretary details (name, phone number)
2. Sarpanch details (name, phone number)
3. Email ID of the panchayat
4. Location details (if a collection point location was identified)
5. Meeting outcome (positive, needs follow-up, panch meeting required)
6. Follow-up date if mentioned
7. Any infrastructure notes (electricity, internet, shed availability)

Return a JSON object with the extracted fields. Use null for fields not mentioned.
Translate any non-English text to English for the extracted values.

JSON structure:
{
    "village_panchayat_name": string or null,
    "block_name": string or null,
    "secretary_name": string or null,
    "secretary_phone": string or null,
    "sarpanch_name": string or null,
    "sarpanch_phone": string or null,
    "email_id": string or null,
    "meeting_outcome": "positive" | "follow_up_needed" | "panch_meeting_required" | "negative" | null,
    "location_identified": boolean,
    "location_description": string or null,
    "follow_up_required": boolean,
    "follow_up_date": "YYYY-MM-DD" or null,
    "follow_up_reason": string or null,
    "panch_meeting_required": boolean,
    "electricity_available": boolean or null,
    "internet_available": boolean or null,
    "shed_available": boolean or null,
    "additional_notes": string or null,
    "suggested_stage": string or null
}

Suggested stages can be:
- "first_meeting_done" - if this was an initial meeting
- "panch_meeting_scheduled" - if panch (ward member) meeting is needed
- "location_finalized" - if location was confirmed

Note: Follow-ups are tracked separately via Meetings, not as a stage.
"""

    def __init__(self, use_anthropic: bool = True):
        """Initialize AI processor with preferred API"""
        self.use_anthropic = use_anthropic

        if use_anthropic and settings.anthropic_api_key:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=settings.anthropic_api_key)
        elif settings.openai_api_key:
            from openai import OpenAI
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.use_anthropic = False
        else:
            raise ValueError("No AI API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")

    def detect_language(self, text: str) -> str:
        """Detect the language of input text"""
        try:
            lang = detect(text)
            lang_map = {
                'hi': 'Hindi',
                'mr': 'Marathi',
                'en': 'English',
            }
            return lang_map.get(lang, lang)
        except Exception:
            return 'Unknown'

    def extract_phone_numbers(self, text: str) -> list:
        """Extract phone numbers from text"""
        # Indian phone number patterns
        patterns = [
            r'\+91[\s-]?\d{10}',
            r'\d{10}',
            r'\d{5}[\s-]?\d{5}',
        ]
        numbers = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            numbers.extend(matches)
        return list(set(numbers))

    def extract_email(self, text: str) -> Optional[str]:
        """Extract email address from text"""
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        match = re.search(pattern, text)
        return match.group(0) if match else None

    async def process_input(self, raw_input: str, context: Dict[str, Any] = None) -> MeetingUpdate:
        """
        Process raw voice/text input and extract structured data

        Args:
            raw_input: The raw text from voice transcription or direct text input
            context: Optional context like village_panchayat_id, block_name, etc.

        Returns:
            MeetingUpdate object with extracted data points
        """
        context = context or {}

        # Detect language
        detected_language = self.detect_language(raw_input)

        # Pre-extract phone numbers and email
        phone_numbers = self.extract_phone_numbers(raw_input)
        email = self.extract_email(raw_input)

        # Build context prompt
        context_str = ""
        if context:
            context_str = f"\n\nContext: This update is for Village Panchayat: {context.get('village_panchayat_name', 'Unknown')}, Block: {context.get('block_name', 'Unknown')}"

        # Call AI for structured extraction
        user_prompt = f"""Extract data points from the following meeting update.
The input is in {detected_language}.{context_str}

Meeting Update:
{raw_input}

Pre-extracted phone numbers found: {phone_numbers}
Pre-extracted email found: {email}

Return only the JSON object, no additional text."""

        try:
            if self.use_anthropic:
                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1024,
                    system=self.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                result_text = response.content[0].text
            else:
                response = self.client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                result_text = response.choices[0].message.content

            # Parse JSON response
            # Clean up response if needed
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

            extracted_data = json.loads(result_text)

        except Exception as e:
            # Fallback to basic extraction
            extracted_data = {
                "secretary_phone": phone_numbers[0] if phone_numbers else None,
                "email_id": email,
                "additional_notes": raw_input,
            }

        # Map suggested stage to enum
        suggested_stage = None
        stage_str = extracted_data.get("suggested_stage")
        if stage_str:
            stage_map = {
                "first_meeting_done": DeploymentStage.FIRST_MEETING_DONE,
                "follow_up_required": DeploymentStage.FIRST_MEETING_DONE,  # Legacy: map to first_meeting_done
                "panch_meeting_scheduled": DeploymentStage.PANCH_MEETING_SCHEDULED,
                "location_finalized": DeploymentStage.LOCATION_FINALIZED,
            }
            suggested_stage = stage_map.get(stage_str)

        # Parse follow-up date
        follow_up_date = None
        if extracted_data.get("follow_up_date"):
            try:
                follow_up_date = datetime.strptime(
                    extracted_data["follow_up_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                pass

        # Create MeetingUpdate object
        meeting_update = MeetingUpdate(
            village_panchayat_id=context.get("village_panchayat_id"),
            village_panchayat_name=extracted_data.get("village_panchayat_name") or context.get("village_panchayat_name"),
            block_name=extracted_data.get("block_name") or context.get("block_name"),
            raw_input=raw_input,
            input_language=detected_language,
            secretary_name=extracted_data.get("secretary_name"),
            secretary_phone=extracted_data.get("secretary_phone"),
            sarpanch_name=extracted_data.get("sarpanch_name"),
            sarpanch_phone=extracted_data.get("sarpanch_phone"),
            email_id=extracted_data.get("email_id"),
            meeting_outcome=extracted_data.get("meeting_outcome"),
            location_identified=extracted_data.get("location_identified", False),
            location_description=extracted_data.get("location_description"),
            follow_up_required=extracted_data.get("follow_up_required", False),
            follow_up_date=follow_up_date,
            follow_up_reason=extracted_data.get("follow_up_reason"),
            panch_meeting_required=extracted_data.get("panch_meeting_required", False),
            suggested_stage=suggested_stage,
            recorded_by=context.get("recorded_by"),
        )

        return meeting_update


class VoiceTranscriber:
    """Transcribe voice input to text"""

    def __init__(self):
        import speech_recognition as sr
        self.recognizer = sr.Recognizer()

    def transcribe_file(self, audio_file_path: str, language: str = "hi-IN") -> str:
        """
        Transcribe an audio file to text

        Args:
            audio_file_path: Path to the audio file
            language: Language code (hi-IN for Hindi, mr-IN for Marathi, en-IN for English)

        Returns:
            Transcribed text
        """
        import speech_recognition as sr

        with sr.AudioFile(audio_file_path) as source:
            audio = self.recognizer.record(source)

        try:
            # Try Google Speech Recognition
            text = self.recognizer.recognize_google(audio, language=language)
            return text
        except sr.UnknownValueError:
            raise ValueError("Could not understand audio")
        except sr.RequestError as e:
            raise RuntimeError(f"Speech recognition service error: {e}")

    def transcribe_from_microphone(self, duration: int = 30, language: str = "hi-IN") -> str:
        """
        Record and transcribe from microphone

        Args:
            duration: Maximum recording duration in seconds
            language: Language code

        Returns:
            Transcribed text
        """
        import speech_recognition as sr

        with sr.Microphone() as source:
            print(f"Recording for up to {duration} seconds...")
            self.recognizer.adjust_for_ambient_noise(source)
            audio = self.recognizer.listen(source, timeout=duration)

        try:
            text = self.recognizer.recognize_google(audio, language=language)
            return text
        except sr.UnknownValueError:
            raise ValueError("Could not understand audio")
        except sr.RequestError as e:
            raise RuntimeError(f"Speech recognition service error: {e}")
