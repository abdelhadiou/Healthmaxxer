from flask import Blueprint, render_template, request
import subprocess
import re
import requests
from functools import lru_cache

map_bp = Blueprint('map', __name__)
DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
PLACES_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
GEOLOCATION_URL = "https://www.googleapis.com/geolocation/v1/geolocate"

# Move this to config.py or environment variables in production
API_KEY = "AIzaSyChswIpHXtx3fxAwHxlay4w3w8KlAxb5K0"
VALID_TYPES = {"doctor", "hospital", "pharmacy"}


def validate_doc_type(doc_type):
    """Ensure doc_type is one of our expected values"""
    return doc_type if doc_type in VALID_TYPES else "doctor"


def get_directions_to_place(lat, lng, dest_lat, dest_lng):
    """Get distance and duration to destination"""
    try:
        params = {
            'origin': f"{lat},{lng}",
            'destination': f"{dest_lat},{dest_lng}",
            'key': API_KEY
        }
        response = requests.get(DIRECTIONS_URL, params=params)
        data = response.json()

        if data['status'] == 'OK':
            leg = data['routes'][0]['legs'][0]
            return leg['distance']['text'], leg['duration']['text']
    except Exception as e:
        print(f"Directions API error: {str(e)}")
    return None, None


def get_user_location():
    """Get user location using WiFi BSSID"""
    try:
        # Get BSSID
        output = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], encoding='utf-8')
        match = re.search(r'BSSID\s*:\s*([0-9a-fA-F:]+)', output)
        if not match:
            return None

        # Get coordinates
        payload = {
            "wifiAccessPoints": [{
                "macAddress": match.group(1),
                "signalStrength": -50,
                "signalToNoiseRatio": 40
            }]
        }
        response = requests.post(f"{GEOLOCATION_URL}?key={API_KEY}", json=payload)
        data = response.json()
        return data['location']['lat'], data['location']['lng']
    except Exception as e:
        print(f"Location error: {str(e)}")
        return None


@lru_cache(maxsize=32)  # Cache results to avoid duplicate API calls
def get_nearby_doctors(lat, lng, doc_type):
    """Find nearby places with caching"""
    try:
        params = {
            'location': f"{lat},{lng}",
            'radius': 20000,
            'keyword': doc_type,
            'key': API_KEY
        }
        response = requests.get(PLACES_URL, params=params)
        data = response.json()

        doctors = []
        if data['status'] == 'OK':
            for place in data['results']:
                distance, duration = get_directions_to_place(
                    lat, lng,
                    place['geometry']['location']['lat'],
                    place['geometry']['location']['lng']
                )

                doctors.append({
                    'name': place['name'],
                    'address': place.get('vicinity', 'Address not available'),
                    'latitude': place['geometry']['location']['lat'],
                    'longitude': place['geometry']['location']['lng'],
                    'rating': place.get('rating', 'No rating'),
                    'distance': distance,
                    'duration': duration
                })
        return doctors
    except Exception as e:
        print(f"Places API error: {str(e)}")
        return []


@map_bp.route('/find-doctors', methods=['GET', 'POST'])
def find_doctors():
    location = get_user_location()
    if not location:
        return render_template('nearest_doctor.html',
                               message="Could not determine your location",
                               doctors=[])

    lat, lng = location

    # Get and validate doc_type
    doc_type = request.form.get('type', "doctor") if request.method == 'POST' else "doctor"
    doc_type = validate_doc_type(doc_type)

    doctors = get_nearby_doctors(lat, lng, doc_type)
    doctors_sorted = sorted(
        doctors,
        key=lambda x: float(x['distance'].split()[0])  # Extracts the numeric part
    )

    return render_template('nearest_doctor.html',
                           user_latitude=lat,
                           user_longitude=lng,
                           doctors=doctors_sorted[:10],
                           selected_type=doc_type)