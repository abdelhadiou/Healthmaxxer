from flask import Blueprint, request, jsonify, session
import whisper
import tempfile
import os
from datetime import datetime

speech_bp = Blueprint('speech', __name__)

# Load Whisper model once when starting the app
model = whisper.load_model("base")


@speech_bp.route('/api/upload-audio', methods=['POST'])
def upload_audio():
    # Verify user is logged in
    if 'user_ID' not in session:
        return jsonify({"error": "Please login first"}), 401

    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    try:
        audio_file = request.files['audio']

        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_file.save(tmp)
            tmp_path = tmp.name

        # Transcribe audio
        result = model.transcribe(tmp_path)
        os.unlink(tmp_path)  # Delete temp file

        # Add to conversation history
        if 'conversation_history' not in session:
            session['conversation_history'] = []

        session['conversation_history'].append({
            'role': 'user',
            'content': result['text'],
            'timestamp': datetime.now().isoformat(),
            'from_speech': True  # Flag to indicate speech input
        })

        return jsonify({
            "text": result["text"],
            "language": result["language"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500