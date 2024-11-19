import os
import urllib
import requests
import io

# Read API key from environment variable
GOOGLE_MAPS_API_KEY = os.environ.get('GMAPS_API_KEY')
if not GOOGLE_MAPS_API_KEY:
    raise ValueError("GMAPS_API_KEY environment variable is not set")

STATIC_MAP_API_URL = "https://maps.googleapis.com/maps/api/staticmap"

def visualize_route(detailed_route):
    """
    Visualize the detailed route using Google Maps Static API.
    """
    if not detailed_route:
        print("No route to visualize.")
        return

    # Prepare the path for the route
    path_points = []
    for step in detailed_route:
        path_points.append(f'{step["start_location"]["lat"]},{step["start_location"]["lon"]}')
        path_points.append(f'{step["end_location"]["lat"]},{step["end_location"]["lon"]}')

    # Deduplicate path points to reduce URL length
    path_points = list(dict.fromkeys(path_points))

    # Prepare markers for start and end points
    #start_marker = f"color:green|label:S|{self.visited_locations[0].coordinates.lat},{self.visited_locations[0].coordinates.lon}"
    #end_marker = f"color:red|label:E|{self.visited_locations[-1].coordinates.lat},{self.visited_locations[-1].coordinates.lon}"

    # Construct the base URL
    base_url = f"{STATIC_MAP_API_URL}?size=1280x720&scale=2&maptype=roadmap&key={GOOGLE_MAPS_API_KEY}"

    # Add markers
    #base_url += f"&markers={urllib.parse.quote(start_marker)}&markers={urllib.parse.quote(end_marker)}"

    # Add path
    encoded_path = urllib.parse.quote("|".join(path_points))
    path_url = f"&path=color:0x0000ff|weight:5|{encoded_path}"

    # Check if the URL is too long and simplify if necessary
    if len(base_url + path_url) > 8192:
        print("Warning: URL too long. Simplifying path...")
        # Simplify by reducing the number of path points
        simplified_path = path_points[::len(path_points)//100 + 1]  # Take every nth point
        encoded_path = urllib.parse.quote("|".join(simplified_path))
        path_url = f"&path=color:0x0000ff|weight:5|{encoded_path}"

    final_url = base_url + path_url

    try:
        # Make the request to the Static Map API
        response = requests.get(final_url)
        response.raise_for_status()

        # show image in Jupyter Notebook
        from IPython.display import Image, display
        display(Image(response.content))
        
        from PIL import Image as PILImage
        return PILImage.open(io.BytesIO(response.content))
    except requests.RequestException as e:
        print(f"Failed to generate map. Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
