"""
llm_assistant.py
Coordinates RAG retrieval and LLM API calls to provide contextual answers.
Supports streaming (SSE) responses and handles <think> reasoning tags.
"""

import os
import json
import sqlite3
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

LLM_API_URL = os.getenv("LLM_API_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")

# Import project modules
import db_manager
from rag_engine import get_context_for_query


def _get_realtime_status():
    """
    Fetch the current real-time status from the database.
    Returns a plain-text summary for the LLM system prompt.
    """
    with sqlite3.connect(db_manager.DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Currently occupied toilets
        cursor.execute("""
            SELECT tl.patient_id, tl.entry_time
            FROM Toilet_Logs tl
            WHERE tl.exit_time IS NULL
            ORDER BY tl.entry_time DESC
        """)
        occupied = cursor.fetchall()

        # Recent accidents
        cursor.execute("""
            SELECT tl.patient_id, tl.entry_time, tl.duration_seconds
            FROM Toilet_Logs tl
            WHERE tl.is_accident = 1
            ORDER BY tl.log_id DESC
            LIMIT 5
        """)
        recent_accidents = cursor.fetchall()

        # Total patients registered
        cursor.execute("SELECT COUNT(*) FROM Patients")
        total_patients = cursor.fetchone()[0]

    # Build plain-text summary
    lines = ["=== REAL-TIME SYSTEM STATUS ==="]
    lines.append(f"Total registered patients: {total_patients}")

    if occupied:
        lines.append(f"\nCurrently occupied toilets ({len(occupied)}):")
        for row in occupied:
            lines.append(f"  - Room 1-01: Patient {row['patient_id']}, entered at {row['entry_time']}")
    else:
        lines.append("\nAll toilets are currently vacant.")

    if recent_accidents:
        lines.append(f"\nRecent accidents ({len(recent_accidents)}):")
        for row in recent_accidents:
            dur = f"{row['duration_seconds']}s" if row['duration_seconds'] else "N/A"
            lines.append(f"  - Patient {row['patient_id']} at {row['entry_time']} (duration: {dur})")
    else:
        lines.append("\nNo recent accidents recorded.")

    return "\n".join(lines)


def _build_system_prompt(user_message):
    """Build the full system prompt with RAG context and real-time status."""
    manual_context = get_context_for_query(user_message, top_k=3)
    realtime_status = _get_realtime_status()

    return f"""You are the Smart Ward AI Assistant for a hospital toilet safety monitoring system.
Your role is to help medical staff understand the system and answer their questions accurately.

Use the following reference material to answer the user's question.
If the answer is not in the provided context, say you don't have that information.
Be concise and professional. Use bullet points when listing multiple items.

=== SYSTEM MANUAL (Retrieved via RAG) ===
{manual_context}

{realtime_status}
"""


def stream_reply(user_message):
    """
    Generator that yields streaming tokens from the LLM API.
    Each yield is a string chunk of the response.

    Args:
        user_message (str): The user's question.

    Yields:
        str: Token chunks from the LLM response.
    """
    if not LLM_API_URL:
        yield "[ERROR]LLM API is not configured. Please contact the administrator."
        return

    system_prompt = _build_system_prompt(user_message)

    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    payload = {
        "model": "Qwopus3.5-9B-v3",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
        "stream": True,
    }

    try:
        print(f"LLM Assistant: Sending streaming request...")
        response = requests.post(
            LLM_API_URL,
            headers=headers,
            json=payload,
            timeout=120,
            stream=True,
        )
        response.raise_for_status()

        # Parse SSE stream from the LLM API
        first_token = True
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]  # Remove "data: " prefix
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        if first_token:
                            first_token = False
                            if "Qwopus" in payload["model"] and not content.lstrip().startswith("<think>"):
                                yield "<think>\n" + content
                            else:
                                yield content
                        else:
                            yield content
                except json.JSONDecodeError:
                    continue

        print("LLM Assistant: Streaming completed.")

    except requests.exceptions.Timeout:
        print("LLM Assistant: Request timed out.")
        yield "[ERROR]The AI service took too long to respond. Please try again."
    except requests.exceptions.ConnectionError:
        print("LLM Assistant: Connection error.")
        yield "[ERROR]Could not connect to the AI service. Please check if the server is running."
    except Exception as e:
        print(f"LLM Assistant: Error - {e}")
        yield "[ERROR]The AI service encountered an internal error. Please try again later."


def get_reply(user_message):
    """
    Non-streaming fallback: collect all streamed tokens into a single string.

    Args:
        user_message (str): The user's question.

    Returns:
        str: The full LLM response text.
    """
    return "".join(stream_reply(user_message))
