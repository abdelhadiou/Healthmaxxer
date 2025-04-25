from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from datetime import datetime
import re
from deepface import DeepFace
import cv2
import numpy as np
import base64

therapist_bp = Blueprint('therapist', __name__)


@therapist_bp.route('/analyze_emotion', methods=['POST'])
def analyze_emotion():
    """Analyze a base64-encoded image for emotion using DeepFace with optional mirroring."""
    try:
        data = request.json
        image_data = data.get('image', '')
        should_flip = data.get('flip', False)  # Get flip flag from frontend

        # Decode the base64 image
        encoded_data = image_data.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Flip image if requested
        if should_flip:
            img = cv2.flip(img, 1)  # 1 means horizontal flip

        # Perform emotion analysis
        result = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
        emotion = result[0]['dominant_emotion']

        return jsonify({
            'emotion': emotion,
            'image_size': f"{img.shape[1]}x{img.shape[0]}",  # Return width x height
            'flipped': should_flip
        })
    except Exception as e:
        print(f"Emotion analysis error: {e}")
        return jsonify({'emotion': 'neutral', 'error': str(e)}), 500


def create_chain():
    """Instantiate a LangChain chain with Gemini Pro for therapeutic responses."""
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key="AIzaSyCVgtzRG6c0hkXubuKRP6ZD2D8z5bNB_hQ",
        temperature=0.6
    )
    prompt = PromptTemplate(
        input_variables=["history", "user_input", "emotion"],
        template="""
You are a helpful, thoughtful, and positive therapist designed to uplift and support individuals with their personal struggles.
stick to those Guidelines:
           - Be thoughtful and understanding
           - ask question for further details
           - Never diagnose, only suggest general advice
           - Recommend professional care for serious symptoms
           - make your answer brief
           - NEVER answer non related health question!!!!.and don't ask questions about them just say you can't answer.
           - after 5 question give him a point from 100 how he describe his feeling and how emotion change . 
Current Detected Emotion from facial recognition model: {emotion}
Conversation History:
{history}

User: {user_input}
Assistant:
"""
    )
    return LLMChain(llm=llm, prompt=prompt)


def sanitize_input(text):
    """Clean user input while preserving medical terms."""
    return re.sub(r'[^\w\s,.?!-°]', '', text).strip()


@therapist_bp.route('/therapist', methods=['GET', 'POST'])
def therapist():
    # Require login
    if 'user_ID' not in session:
        return jsonify({"error": "Please login first"}), 401

    # Initialize histories
    session.setdefault('conversation_history', [])
    session.setdefault('emotion_history', [])

    if request.method == 'POST':
        try:
            data = request.get_json()
            user_input = sanitize_input(data.get('message', ''))
            current_emotion = data.get('emotion', 'neutral')

            if not user_input:
                return jsonify({
                    "error": "Please enter your symptoms",
                    "conversation_history": session['conversation_history'],
                    "emotion_history": session['emotion_history']
                }), 400

            # Update emotion history (keep last 5)
            session['emotion_history'].append(current_emotion)
            session['emotion_history'] = session['emotion_history'][-5:]
            emotion_history_str = ", ".join(session['emotion_history'])

            # Add user message to conversation history
            session['conversation_history'].append({
                'role': 'user',
                'content': user_input,
                'timestamp': datetime.now().isoformat()
            })

            # Build conversation string excluding the last user entry
            history_str = "\n".join(
                f"{msg['role'].capitalize()}: {msg['content']}"
                for msg in session['conversation_history'][:-1]
            )

            # Generate therapist response
            chain = create_chain()
            response = chain.invoke({
                "user_input": user_input,
                "history": history_str,
                "emotion": f"{current_emotion} (Recent: {emotion_history_str})"
            })
            ai_response = response.get('text', '').strip() or "Could you tell me more about that?"

            # Append AI response to history
            session['conversation_history'].append({
                'role': 'ai',
                'content': ai_response,
                'timestamp': datetime.now().isoformat()
            })
            session.modified = True

            return jsonify({
                "response": ai_response,
                "conversation_history": session['conversation_history'],
                "emotion_history": session['emotion_history']
            })

        except Exception as e:
            print(f"Therapist error: {e}")
            return jsonify({
                "error": "I'm having trouble responding. Please try again.",
                "response": "For urgent concerns, please contact a healthcare professional."
            }), 500

    # GET: render therapist chat UI
    return render_template(
        'therapist.html',
        logged_in=True,
        conversation_history=session.get('conversation_history', []),
        emotion_history=session.get('emotion_history', [])
    )