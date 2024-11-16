import os
from typing import List, Dict, Any, Optional
import requests
from pydantic import BaseModel

# Read API key from environment variable
GOOGLE_MAPS_API_KEY = os.environ.get('GMAPS_API_KEY')
if not GOOGLE_MAPS_API_KEY:
    raise ValueError("GMAPS_API_KEY environment variable is not set")

# Define constants
GEOCODING_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
STATIC_MAP_API_URL = "https://maps.googleapis.com/maps/api/staticmap"
REQUESTS_TIMEOUT = 5

class Coordinates(BaseModel):
    """
    A pair of latitude and longitude coordinates.
    """
    lat: float
    lon: float

class Location(BaseModel):
    """
    A location with a name, coordinates, address, and types.
    """
    id: str
    name: str
    coordinates: Coordinates
    address: str
    types: List[str]


class RouteStep(BaseModel):
    """
    A step in a route with start and end locations, distance, duration, and instructions
    """
    start_location: Coordinates
    end_location: Coordinates
    distance: float  # in meters
    duration: float  # in seconds
    instructions: str


class StreetNavigator:
    """
    A simple street navigation system that uses the Google Maps API to provide
    basic route planning and navigation functionality.
    """

    def __init__(self, location_search_radius: Optional[int] = 500):
        self.location_search_radius = location_search_radius

    def start_route(self, address: str) -> Dict[str, Any]:
        """
        Start a new route from the given address.
        """
        coords, formatted_address = self._geocode(address)
        current_location = Location(
            id="",
            name="Start Location",
            coordinates=coords,
            address=formatted_address,
            types=["route_start"]
        )
        return {
            "status": "success",
            "message": "Route started",
            "current_location": current_location.dict(),
            "locations_visited": 1
        }

    def get_next_possible_destinations(self, lat, lon) -> Dict[str, Any]:
        """
        Get a list of possible next destinations from the current location.
        """

        nearby_places = self._get_nearby_places(lat, lon)

        destinations = []
        for place in nearby_places:
            destinations.append({
                "id": place.id,
                "name": place.name,
                "address": place.address,
                "types": place.types,
                "coordinates": place.coordinates.dict()
            })

        return {
            "status": "success",
            "destinations": destinations,
        }

    def navigate(self, from_lat, from_lon, location_id: str) -> Dict[str, Any]:
        """
        Navigate to the specified location, including walking directions.
        """

        # Get details for the chosen destinationc
        chosen_destination = self._get_place_details(location_id)
        if 'error' in chosen_destination:
            return {
                "status": "error",
                "message": f"Failed to get details for location: {chosen_destination['error']}"
            }

        # Get walking directions
        to_lat = chosen_destination["coordinates"]["latitude"]
        to_lon = chosen_destination["coordinates"]["longitude"]
        walking_directions = self._get_walking_directions(
            from_lat, from_lon, to_lat, to_lon)

        return {
            "status": "success",
            "message": f"Navigated to location: {chosen_destination['name']}",
            "current_location": chosen_destination,
            "walking_directions": walking_directions,
        }

    def _get_place_details(self, place_id):
        """
        Get coordinates and metadata for a specific place ID using direct HTTP request
        to Google Maps Places API

        Args:
            place_id (str): The Google Place ID for the location
            api_key (str): Your Google Maps API key

        Returns:
            dict: Place details including coordinates and metadata
        """
        # Construct the Places API URL
        base_url = "https://maps.googleapis.com/maps/api/place/details/json"

        # Define the parameters
        params = {
            'place_id': place_id,
            'key': GOOGLE_MAPS_API_KEY,
            'fields': 'name,formatted_address,geometry,rating,formatted_phone_number,website,types,opening_hours,business_status'
        }

        try:
            # Make the HTTP request
            response = requests.get(base_url, params=params, timeout=REQUESTS_TIMEOUT)
            response.raise_for_status()  # Raise exception for bad status codes

            # Parse the JSON response
            place_details = response.json()

            if place_details.get('status') == 'OK':
                result = place_details['result']

                # Extract coordinates
                location = result['geometry']['location']
                lat = location['lat']
                lng = location['lng']

                # Create formatted response
                place_info = {
                    'name': result.get('name'),
                    'coordinates': {
                        'latitude': lat,
                        'longitude': lng
                    },
                    'address': result.get('formatted_address'),
                    'rating': result.get('rating'),
                    'types': result.get('types'),
                    'opening_hours': result.get('opening_hours'),
                    'business_status': result.get('business_status')
                }

                return place_info

            else:
                error_message = place_details.get(
                    'error_message', 'Place not found')
                return {
                    'error': error_message,
                    'status': place_details.get('status')
                }

        except requests.exceptions.RequestException as e:
            return {
                'error': f'Request failed: {str(e)}',
                'status': 'REQUEST_FAILED'
            }

    def _geocode(self, address: str) -> tuple[Coordinates, str]:
        """
        Convert an address to coordinates and formatted address.
        """
        params = {
            'address': address,
            'key': GOOGLE_MAPS_API_KEY
        }
        response = requests.get(GEOCODING_API_URL, params=params, timeout=REQUESTS_TIMEOUT)
        data = response.json()
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            formatted_address = data['results'][0]['formatted_address']
            return Coordinates(lat=location['lat'], lon=location['lng']), formatted_address
        else:
            raise ValueError(f"Geocoding failed: {data['status']}")

    def _get_nearby_places(self, lat, lon) -> List[Location]:
        """
        Get nearby places from the current location.
        """
        params = {
            'location': f"{lat},{lon}",
            'radius': self.location_search_radius,
            'type': 'point_of_interest',
            'key': GOOGLE_MAPS_API_KEY
        }
        response = requests.get(PLACES_API_URL, params=params, timeout=REQUESTS_TIMEOUT)
        data = response.json()

        places = []
        if data['status'] == 'OK':
            for place in data['results']:
                place_location = place['geometry']['location']
                places.append(Location(
                    id=place['place_id'],
                    name=place['name'],
                    coordinates=Coordinates(
                        lat=place_location['lat'], lon=place_location['lng']),
                    address=place.get('vicinity', 'Address not available'),
                    types=place['types']
                ))
        return places

    def _get_walking_directions(self, start_lat, start_lon, end_lat, end_lon) -> List[RouteStep]:
        """
        Get walking directions between two points.
        """
        params = {
            'origin': f"{start_lat},{start_lon}",
            'destination': f"{end_lat},{end_lon}",
            'mode': 'walking',
            'key': GOOGLE_MAPS_API_KEY
        }
        response = requests.get(DIRECTIONS_API_URL, params=params, timeout=REQUESTS_TIMEOUT)
        data = response.json()

        route_steps = []
        if data['status'] == 'OK':
            for step in data['routes'][0]['legs'][0]['steps']:
                route_steps.append(RouteStep(
                    start_location=Coordinates(
                        lat=step['start_location']['lat'], lon=step['start_location']['lng']),
                    end_location=Coordinates(
                        lat=step['end_location']['lat'], lon=step['end_location']['lng']),
                    distance=step['distance']['value'],
                    duration=step['duration']['value'],
                    instructions=step['html_instructions']
                ).dict())
        return route_steps
