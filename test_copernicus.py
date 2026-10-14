
import openeo

# Ne conectam la serviciul Copernicus Data Space
connection = openeo.connect(
    "https://openeo.dataspace.copernicus.eu"
)

# Ne autentificam prin browser
connection.authenticate_oidc()

print("Autentificare reusita!")

# Verificam daca exista colectia Sentinel-2
collections = connection.list_collection_ids()

print(
    "Sentinel-2 disponibil:",
    "SENTINEL2_L2A" in collections
)

