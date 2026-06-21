"""
Sarvam AI integration for Indian language voice/text processing
Supports Hindi, Marathi, English and other Indian languages
"""
import json
import base64
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, List
from datetime import datetime, date
import os

from ..models.entities import MeetingUpdate
from ..config.settings import Settings, DeploymentStage

settings = Settings()


class SarvamAIProcessor:
    """
    Process voice/text input using Sarvam AI APIs
    - Saarika: Speech-to-Text
    - Mayura: Translation
    - Sarvam LLM: Text understanding and extraction
    """

    BASE_URL = "https://api.sarvam.ai"

    # Language codes for Sarvam AI
    LANGUAGE_CODES = {
        "hindi": "hi-IN",
        "marathi": "mr-IN",
        "english": "en-IN",
        "konkani": "kok-IN",
        "gujarati": "gu-IN",
        "kannada": "kn-IN",
    }

    EXTRACTION_PROMPT = """You are an assistant helping to extract structured data from meeting notes about Village Panchayat visits for the Goa DRS (Deposit Return Scheme) RVM deployment project.

The input may be in Marathi, Hindi, Konkani, or English. Extract the following data points if mentioned:

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
    "suggested_stage": "first_meeting_done" | "panch_meeting_scheduled" | "location_finalized" | null
}

Meeting notes to process:
"""

    def __init__(self, api_key: str = None):
        """Initialize Sarvam AI processor"""
        self.api_key = api_key or settings.sarvam_api_key or os.getenv("SARVAM_API_KEY")
        if not self.api_key:
            raise ValueError("Sarvam AI API key not configured. Set SARVAM_API_KEY environment variable.")

    def _make_request(self, endpoint: str, data: Dict, method: str = "POST") -> Dict:
        """Make API request to Sarvam AI (JSON endpoint)"""
        url = f"{self.BASE_URL}/{endpoint}"

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }

        json_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=json_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            raise RuntimeError(f"Sarvam AI API error ({e.code}): {error_body}")
        except Exception as e:
            raise RuntimeError(f"Sarvam AI request failed: {e}")

    def _make_multipart_request(self, endpoint: str, file_path: str, form_fields: Dict) -> Dict:
        """Make multipart/form-data request to Sarvam AI (for file uploads)"""
        import mimetypes
        import uuid

        url = f"{self.BASE_URL}/{endpoint}"
        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"

        # Build multipart body
        body_parts = []

        # Add form fields
        for key, value in form_fields.items():
            if value is not None:
                body_parts.append(f'--{boundary}\r\n'.encode())
                body_parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
                body_parts.append(f'{value}\r\n'.encode())

        # Add file
        filename = os.path.basename(file_path)
        mime_type = mimetypes.guess_type(file_path)[0] or 'audio/webm'

        body_parts.append(f'--{boundary}\r\n'.encode())
        body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
        body_parts.append(f'Content-Type: {mime_type}\r\n\r\n'.encode())

        with open(file_path, 'rb') as f:
            body_parts.append(f.read())

        body_parts.append(f'\r\n--{boundary}--\r\n'.encode())

        body = b''.join(body_parts)

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            raise RuntimeError(f"Sarvam AI API error ({e.code}): {error_body}")
        except Exception as e:
            raise RuntimeError(f"Sarvam AI request failed: {e}")

    def transcribe_audio(self, audio_file_path: str, language: str = "hi-IN") -> Dict:
        """
        Transcribe audio file using Sarvam Saarika (Speech-to-Text)

        Args:
            audio_file_path: Path to audio file (WAV, MP3, WebM, etc.)
            language: Language code (hi-IN, mr-IN, en-IN, etc.)

        Returns:
            Dict with 'transcript' and 'language_code'
        """
        # Use multipart form-data upload (Sarvam API requirement)
        form_fields = {
            "model": "saarika:v2",
            "language_code": language,
        }

        response = self._make_multipart_request("speech-to-text", audio_file_path, form_fields)

        # Extract transcript from response
        transcript = response.get("transcript", "")
        detected_language = response.get("language_code", language)

        return {
            "transcript": transcript,
            "language_code": detected_language
        }

    def transcribe_audio_with_translation(self, audio_file_path: str,
                                          source_language: str = "hi-IN",
                                          target_language: str = "en-IN") -> Dict:
        """
        Transcribe audio and optionally translate to English

        Args:
            audio_file_path: Path to audio file
            source_language: Source language code
            target_language: Target language code for translation

        Returns:
            Dict with 'original_transcript', 'translated_transcript', 'language_code'
        """
        # First transcribe
        transcription = self.transcribe_audio(audio_file_path, source_language)
        original_text = transcription.get("transcript", "")

        if not original_text:
            return {
                "original_transcript": "",
                "translated_transcript": "",
                "language_code": source_language
            }

        # Translate if not already English
        if source_language != "en-IN":
            translated = self.translate_text(original_text, source_language, target_language)
            translated_text = translated.get("translated_text", original_text)
        else:
            translated_text = original_text

        return {
            "original_transcript": original_text,
            "translated_transcript": translated_text,
            "language_code": source_language
        }

    def translate_text(self, text: str, source_lang: str = "hi-IN", target_lang: str = "en-IN") -> Dict:
        """
        Translate text using Sarvam Mayura (Translation)

        Args:
            text: Text to translate
            source_lang: Source language code (BCP-47 format: hi-IN, mr-IN, en-IN)
            target_lang: Target language code (BCP-47 format)

        Returns:
            Dict with 'translated_text'
        """
        data = {
            "input": text,
            "source_language_code": source_lang,  # Full BCP-47 code (hi-IN)
            "target_language_code": target_lang,  # Full BCP-47 code (en-IN)
            "model": "mayura:v1",
            "mode": "formal",
            "enable_preprocessing": True
        }

        response = self._make_request("translate", data)
        return {"translated_text": response.get("translated_text", text)}

    def extract_meeting_data(self, text: str, context: Dict = None) -> Dict:
        """
        Extract structured data from meeting notes using Sarvam-M LLM

        Args:
            text: Meeting notes text
            context: Optional context (VP name, block name, etc.)

        Returns:
            Extracted data as dictionary
        """
        context = context or {}

        # Build context string
        context_str = ""
        if context.get("village_panchayat_name"):
            context_str = f"\nContext: Village Panchayat: {context['village_panchayat_name']}"
        if context.get("block_name"):
            context_str += f", Block: {context['block_name']}"

        user_prompt = f"{context_str}\n\nMeeting notes:\n{text}\n\nReturn only the JSON object, no explanation."

        # Use OpenAI-compatible chat completions endpoint
        data = {
            "model": "sarvam-m",
            "messages": [
                {"role": "system", "content": self.EXTRACTION_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.2,
        }

        try:
            response = self._make_request("v1/chat/completions", data)

            # Extract content from chat completion response
            choices = response.get("choices", [])
            if choices:
                result_text = choices[0].get("message", {}).get("content", "{}")
            else:
                result_text = "{}"

            # Clean up JSON
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

            return json.loads(result_text.strip())

        except json.JSONDecodeError:
            # Return basic extraction if JSON parsing fails
            return self._basic_extraction(text)
        except Exception as e:
            print(f"LLM extraction failed: {e}, falling back to basic extraction")
            return self._basic_extraction(text)

    def _basic_extraction(self, text: str) -> Dict:
        """Basic regex-based extraction as fallback"""
        import re

        # Phone number extraction
        phone_pattern = r'(?:\+91[\s-]?)?[6-9]\d{9}'
        phones = re.findall(phone_pattern, text)

        # Email extraction
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, text)

        return {
            "secretary_phone": phones[0] if phones else None,
            "sarpanch_phone": phones[1] if len(phones) > 1 else None,
            "email_id": emails[0] if emails else None,
            "additional_notes": text[:500],
        }

    async def process_voice_input(self, audio_file_path: str,
                                   language: str = "hi-IN",
                                   context: Dict = None) -> MeetingUpdate:
        """
        Full pipeline: Audio → Transcription → Extraction → MeetingUpdate

        Args:
            audio_file_path: Path to audio file
            language: Language code for transcription
            context: Optional context dictionary

        Returns:
            MeetingUpdate object with extracted data
        """
        context = context or {}

        # Step 1: Transcribe audio
        transcription = self.transcribe_audio_with_translation(
            audio_file_path,
            source_language=language,
            target_language="en-IN"
        )

        original_text = transcription.get("original_transcript", "")
        translated_text = transcription.get("translated_transcript", original_text)

        if not original_text:
            raise ValueError("Could not transcribe audio - no speech detected")

        # Step 2: Extract structured data from translated text
        extracted = self.extract_meeting_data(translated_text, context)

        # Step 3: Build MeetingUpdate
        return self._build_meeting_update(extracted, original_text, context)

    async def process_text_input(self, text: str, context: Dict = None) -> MeetingUpdate:
        """
        Process text input and extract meeting data

        Args:
            text: Meeting notes text
            context: Optional context dictionary

        Returns:
            MeetingUpdate object with extracted data
        """
        context = context or {}

        # Detect if translation needed (simple heuristic)
        has_devanagari = any('\u0900' <= c <= '\u097F' for c in text)

        if has_devanagari:
            # Translate to English first
            translation = self.translate_text(text, "hi-IN", "en-IN")
            english_text = translation.get("translated_text", text)
        else:
            english_text = text

        # Extract structured data
        extracted = self.extract_meeting_data(english_text, context)

        return self._build_meeting_update(extracted, text, context)

    def _build_meeting_update(self, extracted: Dict, raw_input: str, context: Dict) -> MeetingUpdate:
        """Build MeetingUpdate from extracted data"""
        # Parse follow-up date
        follow_up_date = None
        if extracted.get("follow_up_date"):
            try:
                follow_up_date = datetime.strptime(
                    extracted["follow_up_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                pass

        # Map suggested stage (follow_up_required removed - it's now tracked via Meetings)
        stage_map = {
            "first_meeting_done": DeploymentStage.FIRST_MEETING_DONE,
            "follow_up_required": DeploymentStage.FIRST_MEETING_DONE,  # Legacy: map to first_meeting_done
            "panch_meeting_scheduled": DeploymentStage.PANCH_MEETING_SCHEDULED,
            "location_finalized": DeploymentStage.LOCATION_FINALIZED,
        }
        suggested_stage = stage_map.get(extracted.get("suggested_stage"))

        return MeetingUpdate(
            village_panchayat_id=context.get("village_panchayat_id"),
            village_panchayat_name=extracted.get("village_panchayat_name") or context.get("village_panchayat_name"),
            block_name=context.get("block_name"),
            raw_input=raw_input,
            input_language="hi-IN",  # Default
            secretary_name=extracted.get("secretary_name"),
            secretary_phone=extracted.get("secretary_phone"),
            sarpanch_name=extracted.get("sarpanch_name"),
            sarpanch_phone=extracted.get("sarpanch_phone"),
            email_id=extracted.get("email_id"),
            meeting_outcome=extracted.get("meeting_outcome"),
            location_identified=extracted.get("location_identified", False),
            location_description=extracted.get("location_description"),
            follow_up_required=extracted.get("follow_up_required", False),
            follow_up_date=follow_up_date,
            follow_up_reason=extracted.get("follow_up_reason"),
            panch_meeting_required=extracted.get("panch_meeting_required", False),
            suggested_stage=suggested_stage,
            recorded_by=context.get("recorded_by"),
        )


# Convenience function
def create_sarvam_processor(api_key: str = None) -> SarvamAIProcessor:
    """Create a Sarvam AI processor instance"""
    return SarvamAIProcessor(api_key=api_key)
